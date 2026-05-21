import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Scalable Anonymous Chat App"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "supersecretkeychangeinproduction1234567890"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 Hours

    # Database URLs
    # By default, use SQLite in-memory fallback if POSTGRES_URL is not provided
    DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"
    
    # Redis configuration
    # By default, use redis://localhost:6379/0. If unavailable, we will have a clean mock fallback.
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    
    # Production Frontend URL for CORS configuration (e.g. Vercel deployment)
    FRONTEND_URL: Optional[str] = "https://vortexchat.vercel.app"
    
    # Rate Limiting
    RATE_LIMIT_TOKENS: int = 5
    RATE_LIMIT_REFILL_RATE: float = 2.5  # 2.5 tokens per second (fully refills 5 tokens in 2 seconds)

    # Disconnect Cleanup Grace Period (in seconds)
    CLEANUP_GRACE_PERIOD: int = 60

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()
