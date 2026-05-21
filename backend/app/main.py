import json
import uuid
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Response, Cookie, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.app.config import settings
from backend.app.database import engine, Base, get_db
from backend.app.models import RoomModel, SystemMetricModel
from backend.app.auth import generate_guest_credentials, create_access_token, decode_access_token
from backend.app.redis_client import get_redis_client
from backend.app.websockets.router import router as ws_router

# Lifespan context to handle DB schemas creation and public rooms seeding
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create DB Tables (PostgreSQL / SQLite)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Seed Default Public Rooms if they do not exist
    async with AsyncSession(engine) as session:
        async with session.begin():
            result = await session.execute(select(RoomModel).filter_by(is_private=False))
            rooms = result.scalars().all()
            if not rooms:
                default_rooms = [
                    RoomModel(id="general-chat", name="General Chat", topic="Discuss anything and everything with anyone!", is_private=False),
                    RoomModel(id="tech-lounge", name="Tech Lounge", topic="AI, Coding, Systems Architecture, and gadgets.", is_private=False),
                    RoomModel(id="movie-club", name="Movie Club", topic="Reviews, recommendations, and cinema talk.", is_private=False),
                    RoomModel(id="gaming-hub", name="Gaming Hub", topic="Multiplayer matching, e-sports, and new releases.", is_private=False)
                ]
                session.add_all(default_rooms)
                await session.commit()
    
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url="/docs"
)

# Configure production-ready allowed origins for CORS (Vercel + local development)
allowed_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",  # Vite local server
    "http://localhost:3000",
]
if settings.FRONTEND_URL:
    allowed_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include real-time routing layer
app.include_router(ws_router)

# 1. Guest Authentication Endpoint
@app.post("/api/v1/auth/guest")
async def enter_as_guest(response: Response):
    # A. Generate creative credentials
    username, avatar_hash = generate_guest_credentials()
    user_id = str(uuid.uuid4())
    
    # B. Mint access token
    payload = {
        "user_id": user_id,
        "username": username,
        "avatar_hash": avatar_hash
    }
    token = create_access_token(payload)
    
    # C. Store guest details in Redis
    redis = await get_redis_client()
    session_key = f"guest:session:{token[:30]}"  # Truncate signature part for safety
    await redis.hset(session_key, mapping=payload)
    await redis.expire(session_key, 24 * 3600)  # Session expires after 24 hours of inactivity
    
    # D. Attach httpOnly cookie
    response.set_cookie(
        key="guest_token",
        value=token,
        httponly=True,
        max_age=24 * 3600,
        samesite="lax",
        secure=False  # Set to True in production with TLS/HTTPS
    )
    
    return {
        "userId": user_id,
        "username": username,
        "avatarHash": avatar_hash,
        "token": token
    }

# 2. Get Public Rooms List
@app.get("/api/v1/rooms")
async def get_public_rooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RoomModel).filter_by(is_private=False))
    rooms = result.scalars().all()
    
    redis = await get_redis_client()
    output = []
    
    for r in rooms:
        active_cnt = await redis.scard(f"room:{r.id}:active_users")
        output.append({
            "id": r.id,
            "name": r.name,
            "topic": r.topic,
            "activeUsersCount": active_cnt
        })
    return output

# 3. Create Private Chat Room (1-on-1 Temporary Invite Token)
@app.post("/api/v1/rooms/private")
async def create_private_room(db: AsyncSession = Depends(get_db)):
    room_id = f"private-{uuid.uuid4().hex[:12]}"
    new_room = RoomModel(
        id=room_id,
        name="Private Room",
        topic="Temporary invite-only chat room.",
        is_private=True
    )
    db.add(new_room)
    await db.commit()
    
    return {
        "roomId": room_id,
        "inviteLink": f"/chat.html?room={room_id}"
    }

# 4. Fetch Ephemeral Room Messages History
@app.get("/api/v1/rooms/{room_id}/history")
async def get_room_history(room_id: str):
    redis = await get_redis_client()
    msg_key = f"room:{room_id}:messages"
    
    # Retrieve all ephemeral sliding window messages from the sorted set
    # Sorted by timestamp (ascending)
    records = await redis.zrangebyscore(msg_key, 0, time.time())
    
    messages = []
    for rec in records:
        if isinstance(rec, bytes):
            rec = rec.decode("utf-8")
        try:
            messages.append(json.loads(rec))
        except Exception:
            pass
            
    return messages

# 5. Fetch Telemetry Analytics (Database-Backed)
@app.get("/api/v1/analytics")
async def get_system_analytics(db: AsyncSession = Depends(get_db)):
    redis = await get_redis_client()
    
    # Fetch database count of active public rooms
    db_rooms_count = await db.scalar(select(func.count()).select_from(RoomModel))
    
    # Estimate global active sessions based on user presence keys
    # Let's count matching keys
    # For MockRedis, we can scan our internal dict, for real redis we scan keys.
    # To keep it performant and simple:
    active_users = 0
    if hasattr(redis, "data"):
        # MockRedis
        active_users = sum(1 for k in redis.data.keys() if k.startswith("user:presence:"))
    else:
        # Real Redis
        keys = await redis.keys("user:presence:*")
        active_users = len(keys)

    # Fetch total historical metrics logged in db
    db_metrics = await db.execute(select(SystemMetricModel).order_by(SystemMetricModel.timestamp.desc()).limit(10))
    metrics_history = db_metrics.scalars().all()
    
    # Log current tick inside DB
    metric_tick = SystemMetricModel(
        active_rooms=int(db_rooms_count),
        active_users=active_users,
        total_messages_sent=0 # Filled incrementally in production
    )
    db.add(metric_tick)
    await db.commit()

    return {
        "currentActiveUsers": active_users,
        "registeredPublicRooms": db_rooms_count,
        "metricsHistory": [
            {
                "timestamp": m.timestamp.isoformat(),
                "activeRooms": m.active_rooms,
                "activeUsers": m.active_users
            } for m in metrics_history
        ]
    }

# Serve static frontend application
# We mount "/" static directory at the very end
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("frontend/index.html")
