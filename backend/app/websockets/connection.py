import json
import asyncio
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket
from backend.app.config import settings
from backend.app.redis_client import get_redis_client

logger = logging.getLogger("ws_manager")

class ConnectionManager:
    def __init__(self):
        # Maps room_id -> Set of local WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Maps room_id -> active asyncio.Task for Redis Pub/Sub listening
        self.pubsub_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, username: str):
        """Register a new active WebSocket connection and wire up horizontal PubSub if needed"""
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
            
        self.active_connections[room_id].add(websocket)
        
        # Redis Presence Updates
        redis = await get_redis_client()
        await redis.sadd(f"room:{room_id}:active_users", user_id)
        # Store user details (for looking up names/avatars in room listing)
        await redis.hset(f"user:presence:{user_id}", mapping={
            "username": username,
            "room_id": room_id
        })
        # Set TTL relative to the cleanup grace period
        await redis.expire(f"user:presence:{user_id}", settings.CLEANUP_GRACE_PERIOD + 10)

        # Start Pub/Sub listener task for this room if not already running
        if room_id not in self.pubsub_tasks:
            self.pubsub_tasks[room_id] = asyncio.create_task(self._pubsub_listener(room_id))
            
        # Send room state (active user count, previous messages) to the newly connected user
        users = await redis.smembers(f"room:{room_id}:active_users")
        user_list = []
        for uid in users:
            u_info = await redis.hgetall(f"user:presence:{uid}")
            if u_info:
                user_list.append({"userId": uid, "username": u_info.get("username")})
                
        # Send join notification & list to local user
        await websocket.send_json({
            "type": "room_state",
            "room_id": room_id,
            "users": user_list
        })
        
        # Broadcast presence to the room
        await self.broadcast_to_room(room_id, {
            "type": "user_joined",
            "userId": user_id,
            "username": username
        })

    async def disconnect(self, websocket: WebSocket, room_id: str, user_id: str, username: str):
        """Handle client WebSocket drop and schedule the 60-second grace window cleanup"""
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
                # Cleanup the Pub/Sub task to conserve memory
                if room_id in self.pubsub_tasks:
                    self.pubsub_tasks[room_id].cancel()
                    del self.pubsub_tasks[room_id]

        # Delete the presence key immediately on disconnect.
        # If they reconnect, the new connect() call will recreate it.
        redis = await get_redis_client()
        await redis.delete(f"user:presence:{user_id}")

        # Trigger non-blocking async cleanup task
        asyncio.create_task(self._scheduled_cleanup(room_id, user_id, username))


    async def _scheduled_cleanup(self, room_id: str, user_id: str, username: str):
        """Wait for the grace period to see if user has reconnected. If not, clean up cache."""
        # Use settings cleanup grace period (can be set to 1-2s in tests)
        grace_period = settings.CLEANUP_GRACE_PERIOD
        logger.info(f"Scheduling cleanup for {username} ({user_id}) in {grace_period} seconds.")
        
        await asyncio.sleep(grace_period)
        
        redis = await get_redis_client()
        # Check if user's presence key exists
        presence = await redis.hgetall(f"user:presence:{user_id}")
        
        if not presence:
            # User failed to reconnect. Perform final cleanup
            await redis.srem(f"room:{room_id}:active_users", user_id)
            await redis.delete(f"user:presence:{user_id}")
            # Broadcast the disconnect event to other room members
            await self.broadcast_to_room(room_id, {
                "type": "user_left",
                "userId": user_id,
                "username": username
            })
            logger.info(f"Successfully cleaned up guest handle: {username} ({user_id}) from room {room_id}")
        else:
            logger.info(f"User {username} ({user_id}) reconnected inside grace window. Cleanup cancelled.")

    async def keep_alive_ping(self, user_id: str):
        """Updates user presence TTL (called when ping frame is received)"""
        redis = await get_redis_client()
        await redis.expire(f"user:presence:{user_id}", 60)

    async def broadcast_to_room(self, room_id: str, message: dict):
        """Publishes message to Redis Pub/Sub, automatically distributing to all instances"""
        redis = await get_redis_client()
        await redis.publish(f"room:{room_id}:pubsub", json.dumps(message))

    async def _pubsub_listener(self, room_id: str):
        """Listens to the Redis channel for a room and writes messages to all local sockets"""
        redis = await get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"room:{room_id}:pubsub")
        
        try:
            while True:
                # Poll message with short timeout to allow clean cancellation
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data_str = msg["data"]
                    if isinstance(data_str, bytes):
                        data_str = data_str.decode("utf-8")
                    data = json.loads(data_str)
                    
                    # Distribute to all local WebSocket connections in this room
                    sockets = self.active_connections.get(room_id, set())
                    for ws in list(sockets):
                        try:
                            await ws.send_json(data)
                        except Exception as e:
                            logger.error(f"Error sending message to local WebSocket: {e}")
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"room:{room_id}:pubsub")
            logger.info(f"Pub/Sub listener for room {room_id} has been stopped.")
        except Exception as e:
            logger.error(f"Error in Pub/Sub listener for room {room_id}: {e}")

manager = ConnectionManager()
