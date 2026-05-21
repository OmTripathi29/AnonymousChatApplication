import asyncio
import pytest
from httpx import AsyncClient
from backend.app.config import settings

# 1. Override settings for testing
settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
settings.REDIS_URL = ""  # Force MockRedis usage for reliable local unit tests
settings.CLEANUP_GRACE_PERIOD = 1  # 1 second cleanup window for testing rather than 60 seconds!

from backend.app.database import Base, engine
from backend.app.main import app

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def init_db():
    """Initialize DB schema before running each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

import httpx

@pytest.fixture
async def async_client():
    """Fixture for httpx AsyncClient"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

