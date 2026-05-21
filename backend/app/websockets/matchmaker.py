import uuid
import logging
from typing import Optional
from backend.app.redis_client import get_redis_client

logger = logging.getLogger("matchmaker")

async def poll_matchmaking_queue(user_id: str) -> Optional[str]:
    """
    Attempts to pair the user with an existing user in the waitlist.
    Returns partner's user_id or None if no partner found (and user was queued).
    """
    redis = await get_redis_client()
    
    # 1. Get all members currently in the waitlist
    members = await redis.smembers("matchmaker:waitlist")
    
    # 2. Filter out self
    eligible_partners = [m for m in members if m != user_id]
    
    if not eligible_partners:
        # No one else is waiting; put ourselves on the waitlist
        await redis.sadd("matchmaker:waitlist", user_id)
        logger.info(f"User {user_id} added to waitlist (empty queue).")
        return None
        
    # 3. We found eligible partners. Try to claim one via atomic srem
    partner_id = None
    for p in eligible_partners:
        removed = await redis.srem("matchmaker:waitlist", p)
        if removed > 0:
            partner_id = p
            break
            
    if not partner_id:
        # Another worker/process claimed the partners first. Add ourselves
        await redis.sadd("matchmaker:waitlist", user_id)
        logger.info(f"User {user_id} added to waitlist (queue popped concurrently).")
        return None
        
    # 4. Success! Remove ourselves from the waitlist if we were in it
    await redis.srem("matchmaker:waitlist", user_id)
    
    # 5. Create a unique room ID for this 1v1 match
    room_id = f"match:{user_id}_{partner_id}"
    
    # 6. Establish mapping keys in Redis
    await redis.set(f"user:match:{user_id}", room_id)
    await redis.set(f"user:match:{partner_id}", room_id)
    await redis.set(f"user:partner:{user_id}", partner_id)
    await redis.set(f"user:partner:{partner_id}", user_id)
    
    logger.info(f"Matched User {user_id} with User {partner_id} in Room {room_id}")
    return partner_id

async def clear_match(user_id: str) -> Optional[str]:
    """
    Cleans up all active matching states for the user and their partner.
    Returns the partner's user_id if they had an active match.
    """
    redis = await get_redis_client()
    
    # Remove from waitlist
    await redis.srem("matchmaker:waitlist", user_id)
    
    # Retrieve partner ID before deleting mapping
    partner_id = await redis.get(f"user:partner:{user_id}")
    
    # Delete own matching keys
    await redis.delete(f"user:match:{user_id}")
    await redis.delete(f"user:partner:{user_id}")
    await redis.delete(f"user:profile:{user_id}")
    
    if partner_id:
        # Delete partner's matching keys
        await redis.delete(f"user:match:{partner_id}")
        await redis.delete(f"user:partner:{partner_id}")
        await redis.srem("matchmaker:waitlist", partner_id)
        logger.info(f"Cleared match between {user_id} and {partner_id}")
        
    return partner_id
