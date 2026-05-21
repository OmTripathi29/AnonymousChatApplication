import random
import hashlib
import jwt
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from backend.app.config import settings

ADJECTIVES = [
    "Quantum", "Cosmic", "Neon", "Cyber", "Aero", "Hyper", "Vortex", 
    "Stellar", "Spectral", "Solar", "Astro", "Lunar", "Glitch", "Vector"
]

NOUNS = [
    "Fox", "Panda", "Phoenix", "Nova", "Pulse", "Falcon", "Ghost", 
    "Spectre", "Ranger", "Titan", "Helix", "Echo", "Drifter", "Seeker"
]

def generate_guest_credentials() -> Tuple[str, str]:
    """Generates a random safe tech/space pseudonym and unique avatar hash"""
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    number = random.randint(100, 999)
    username = f"{adj}{noun}-{number}"
    
    # Generate stable avatar hash from name
    avatar_hash = hashlib.md5(username.encode("utf-8")).hexdigest()
    return username, avatar_hash

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token for anonymous guests"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict]:
    """Decodes JWT access token, returning payload if valid or None if expired/corrupted"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
