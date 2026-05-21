import logging
import json
import asyncio
import random
from typing import Dict, Set, List, Optional, Any
from backend.app.config import settings

logger = logging.getLogger("redis_manager")

# In-Memory Mock Client for testing or fallback when Redis is offline
class MockPubSub:
    def __init__(self, mock_redis):
        self.mock_redis = mock_redis
        self.channels = []
        self.queue = asyncio.Queue()

    async def subscribe(self, *channels):
        for ch in channels:
            self.channels.append(ch)
            if ch not in self.mock_redis.subscribers:
                self.mock_redis.subscribers[ch] = set()
            self.mock_redis.subscribers[ch].add(self)
        logger.info(f"MockPubSub: Subscribed to channels: {channels}")

    async def unsubscribe(self, *channels):
        for ch in channels:
            if ch in self.channels:
                self.channels.remove(ch)
            if ch in self.mock_redis.subscribers:
                self.mock_redis.subscribers[ch].discard(self)
        logger.info(f"MockPubSub: Unsubscribed from channels: {channels}")

    async def get_message(self, ignore_subscribe_messages=True, timeout=0.1):
        try:
            if timeout > 0:
                msg = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            else:
                msg = self.queue.get_nowait()
            return msg
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

class MockRedis:
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.subscribers: Dict[str, Set[MockPubSub]] = {}
        logger.warning("MockRedis: Initialized in-memory fallback cache. Horizontal scaling across processes is disabled.")

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Optional[str]:
        val = self.data.get(key)
        if val is None:
            return None
        if isinstance(val, tuple) and len(val) == 2:
            value, expiry = val
            if expiry and asyncio.get_event_loop().time() > expiry:
                del self.data[key]
                return None
            return value
        return val

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        expiry = asyncio.get_event_loop().time() + ex if ex else None
        self.data[key] = (value, expiry) if expiry else value
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.data:
                del self.data[k]
                count += 1
        return count

    async def sadd(self, key: str, *members: str) -> int:
        if key not in self.data or not isinstance(self.data[key], set):
            self.data[key] = set()
        count = 0
        for m in members:
            if m not in self.data[key]:
                self.data[key].add(m)
                count += 1
        return count

    async def srem(self, key: str, *members: str) -> int:
        if key not in self.data or not isinstance(self.data[key], set):
            return 0
        count = 0
        for m in members:
            if m in self.data[key]:
                self.data[key].remove(m)
                count += 1
        return count

    async def smembers(self, key: str) -> Set[str]:
        val = self.data.get(key, set())
        return val if isinstance(val, set) else set()

    async def sismember(self, key: str, member: str) -> bool:
        val = self.data.get(key, set())
        return member in val if isinstance(val, set) else False

    async def scard(self, key: str) -> int:
        val = self.data.get(key)
        if isinstance(val, set):
            return len(val)
        return 0

    async def spop(self, key: str) -> Optional[str]:
        val = self.data.get(key)
        if isinstance(val, set) and len(val) > 0:
            member = random.choice(list(val))
            val.remove(member)
            return member
        return None

    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        if key not in self.data or not isinstance(self.data[key], dict):
            self.data[key] = {}
        count = 0
        for m, score in mapping.items():
            if m not in self.data[key]:
                count += 1
            self.data[key][m] = score
        return count

    async def zrangebyscore(self, key: str, min_score: float, max_score: float) -> List[str]:
        if key not in self.data or not isinstance(self.data[key], dict):
            return []
        items = []
        for m, score in self.data[key].items():
            if min_score <= score <= max_score:
                items.append((m, score))
        items.sort(key=lambda x: x[1])
        return [x[0] for x in items]

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        if key not in self.data or not isinstance(self.data[key], dict):
            return 0
        to_remove = []
        for m, score in self.data[key].items():
            if min_score <= score <= max_score:
                to_remove.append(m)
        for m in to_remove:
            del self.data[key][m]
        return len(to_remove)

    async def hset(self, key: str, mapping: Optional[Dict[str, Any]] = None, key_name: Optional[str] = None, value: Optional[Any] = None) -> int:
        if key not in self.data or not isinstance(self.data[key], dict):
            self.data[key] = {}
        count = 0
        if mapping:
            for k, v in mapping.items():
                if k not in self.data[key]:
                    count += 1
                self.data[key][k] = str(v)
        elif key_name is not None:
            if key_name not in self.data[key]:
                count += 1
            self.data[key][key_name] = str(value)
        return count

    async def hgetall(self, key: str) -> Dict[str, str]:
        val = self.data.get(key, {})
        return val if isinstance(val, dict) else {}

    async def expire(self, key: str, time: int) -> bool:
        return True

    async def publish(self, channel: str, message: str) -> int:
        subs = self.subscribers.get(channel, set())
        count = 0
        for sub in subs:
            await sub.queue.put({
                "type": "message",
                "channel": channel.encode("utf-8") if isinstance(channel, str) else channel,
                "data": message.encode("utf-8") if isinstance(message, str) else message
            })
            count += 1
        return count

    def pubsub(self):
        return MockPubSub(self)


_redis_client: Optional[Any] = None
_use_mock: bool = False

async def get_redis_client():
    global _redis_client, _use_mock
    if _redis_client is not None:
        return _redis_client

    if not settings.REDIS_URL:
        _redis_client = MockRedis()
        _use_mock = True
        return _redis_client

    import redis.asyncio as aioredis
    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await asyncio.wait_for(client.ping(), timeout=2.0)
        _redis_client = client
        _use_mock = False
        logger.info("Successfully connected to Redis instance.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {settings.REDIS_URL}: {e}. Falling back to in-memory MockRedis.")
        _redis_client = MockRedis()
        _use_mock = True

    return _redis_client
