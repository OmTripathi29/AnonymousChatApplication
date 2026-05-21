import json
import time
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from backend.app.auth import decode_access_token
from backend.app.rate_limiter import is_rate_limited
from backend.app.redis_client import get_redis_client
from backend.app.websockets.matchmaker import poll_matchmaking_queue, clear_match

logger = logging.getLogger("ws_router")
router = APIRouter()

async def pubsub_listener(websocket: WebSocket, user_id: str):
    """
    Subscribes to the user's private channel in Redis Pub/Sub
    and routes all received messages directly to the active WebSocket.
    """
    redis = await get_redis_client()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"user:{user_id}:pubsub")
    
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                data_str = msg["data"]
                if isinstance(data_str, bytes):
                    data_str = data_str.decode("utf-8")
                await websocket.send_text(data_str)
            await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in pubsub listener for user {user_id}: {e}")
    finally:
        await pubsub.unsubscribe(f"user:{user_id}:pubsub")

@router.websocket("/ws/match")
@router.websocket("/ws/{room_id}")  # Retain legacy route for backwards compatibility
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    # 1. Authenticate guest token
    payload = decode_access_token(token)
    if not payload:
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = payload.get("user_id")
    username = payload.get("username")
    avatar_hash = payload.get("avatar_hash")

    if not user_id or not username:
        await websocket.accept()
        await websocket.close(code=4001, reason="Malformed token credentials")
        return

    await websocket.accept()
    redis = await get_redis_client()

    # 2. Store profile cache so matchmaking queries can look up username/avatar
    await redis.hset(f"user:profile:{user_id}", mapping={
        "username": username,
        "avatar_hash": avatar_hash
    })
    # Set presence key to maintain telemetry compatibility
    await redis.set(f"user:presence:{user_id}", "active")

    # 3. Start Pub/Sub subscription task
    listener_task = asyncio.create_task(pubsub_listener(websocket, user_id))

    try:
        # 4. Trigger initial matchmaking search
        partner_id = await poll_matchmaking_queue(user_id)
        if partner_id:
            # Query partner's profile
            partner_profile = await redis.hgetall(f"user:profile:{partner_id}")
            partner_name = partner_profile.get("username", "Anonymous Guest")
            partner_avatar = partner_profile.get("avatar_hash", "")
            
            # Notify partner via Pub/Sub
            await redis.publish(f"user:{partner_id}:pubsub", json.dumps({
                "type": "matched",
                "partnerName": username,
                "avatarHash": avatar_hash
            }))
            
            # Notify self directly
            await websocket.send_json({
                "type": "matched",
                "partnerName": partner_name,
                "avatarHash": partner_avatar
            })
        else:
            await websocket.send_json({"type": "searching"})

        # 5. Main WebSocket Event Loop
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})
                continue

            event_type = data.get("type")

            # A. Heartbeat Keep-Alive
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # B. Search/Pair Request (used when re-entering after ad countdown)
            elif event_type == "find_match":
                # Clear any existing match first just in case
                partner_id = await clear_match(user_id)
                if partner_id:
                    await redis.publish(f"user:{partner_id}:pubsub", json.dumps({"type": "partner_skipped"}))
                
                partner_id = await poll_matchmaking_queue(user_id)
                if partner_id:
                    partner_profile = await redis.hgetall(f"user:profile:{partner_id}")
                    partner_name = partner_profile.get("username", "Anonymous Guest")
                    partner_avatar = partner_profile.get("avatar_hash", "")
                    
                    await redis.publish(f"user:{partner_id}:pubsub", json.dumps({
                        "type": "matched",
                        "partnerName": username,
                        "avatarHash": avatar_hash
                    }))
                    
                    await websocket.send_json({
                        "type": "matched",
                        "partnerName": partner_name,
                        "avatarHash": partner_avatar
                    })
                else:
                    await websocket.send_json({"type": "searching"})

            # C. Send Message / Image Base64 Frame
            elif event_type == "chat_message":
                msg_text = data.get("message", "").strip()
                image_data = data.get("image")  # Base64 compressed image string

                if not msg_text and not image_data:
                    continue

                # Rate Limiting
                if await is_rate_limited(user_id):
                    await websocket.send_json({
                        "type": "rate_limit_error",
                        "message": "Spam protection active! Maximum 5 messages per 2 seconds."
                    })
                    continue

                partner_id = await redis.get(f"user:partner:{user_id}")
                if partner_id:
                    chat_event = {
                        "type": "chat_message",
                        "userId": user_id,
                        "username": username,
                        "message": msg_text[:500] if msg_text else "",
                        "image": image_data,
                        "timestamp": time.time()
                    }
                    await redis.publish(f"user:{partner_id}:pubsub", json.dumps(chat_event))

            # D. Skip Partner Request
            elif event_type == "skip":
                partner_id = await clear_match(user_id)
                if partner_id:
                    await redis.publish(f"user:{partner_id}:pubsub", json.dumps({"type": "partner_skipped"}))
                await websocket.send_json({"type": "skipped"})

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown event type: {event_type}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {username} ({user_id})")
    finally:
        # 6. Cleanup active matching states
        listener_task.cancel()
        partner_id = await clear_match(user_id)
        await redis.delete(f"user:profile:{user_id}")
        await redis.delete(f"user:presence:{user_id}")
        if partner_id:
            await redis.publish(f"user:{partner_id}:pubsub", json.dumps({"type": "partner_skipped"}))
