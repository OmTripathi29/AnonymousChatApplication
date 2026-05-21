import time
from backend.app.config import settings
from backend.app.redis_client import get_redis_client

async def is_rate_limited(user_id: str) -> bool:
    """
    Evaluates whether a user is rate-limited using a Redis-backed Token Bucket Algorithm.
    Returns True if the user is rate-limited (should block), False if allowed.
    """
    redis = await get_redis_client()
    key = f"rate:{user_id}"
    
    # Standard settings
    capacity = settings.RATE_LIMIT_TOKENS
    refill_rate = settings.RATE_LIMIT_REFILL_RATE
    now = time.time()
    
    # Retrieve current bucket state
    bucket = await redis.hgetall(key)
    
    if not bucket:
        # Initialize bucket
        tokens = float(capacity) - 1.0
        last_updated = now
    else:
        old_tokens = float(bucket.get("tokens", capacity))
        last_updated = float(bucket.get("last_updated", now))
        
        # Calculate refilled tokens
        elapsed = now - last_updated
        refilled = old_tokens + (elapsed * refill_rate)
        tokens = min(float(capacity), refilled)
        
        if tokens >= 1.0:
            tokens -= 1.0
            last_updated = now
        else:
            # Rate limited, don't update last_updated to prevent starvation
            return True
            
    # Save back to Redis with a short expiry to clean up memory
    await redis.hset(key, mapping={
        "tokens": str(tokens),
        "last_updated": str(last_updated)
    })
    await redis.expire(key, 5) # 5s is plenty since it refills in 2s
    
    return False
