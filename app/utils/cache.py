import json
import hashlib
import redis.asyncio as redis
from typing import Any, Optional
from ..core.config import settings
from ..core.logging_config import log

# Global Redis client
redis_client: Optional[redis.Redis] = None

async def init_redis():
    """Initialize the async Redis client."""
    global redis_client
    if not settings.CACHE_ENABLED:
        return

    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0
        )
        await redis_client.ping()
        log.info("Redis connected (Async).")
    except Exception as e:
        log.warning(f"Redis connection failed ({e}), falling back to in-memory cache.")
        redis_client = None

# In-memory fallback
MEM_CACHE: dict = {}

def cache_key(*args) -> str:
    """Generate a stable MD5 hash for cache keys."""
    raw = "|".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()

async def get_cache(bucket: str, key: str) -> Optional[Any]:
    """Retrieve value from Redis or in-memory fallback (Async)."""
    if not settings.CACHE_ENABLED:
        return None

    full_key = f"{settings.PROJECT_NAME}:{bucket}:{key}"
    
    try:
        if redis_client:
            raw = await redis_client.get(full_key)
            return json.loads(raw) if raw else None
        
        # In-memory fallback
        if full_key in MEM_CACHE:
            return MEM_CACHE[full_key]
    except Exception as e:
        log.error(f"Cache GET failed for {bucket}:{key} -> {e}")
    
    return None

async def set_cache(bucket: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Store value in Redis or in-memory fallback (Async)."""
    if not settings.CACHE_ENABLED:
        return

    full_key = f"{settings.PROJECT_NAME}:{bucket}:{key}"
    expiry = ttl or settings.CACHE_TTL

    try:
        if redis_client:
            await redis_client.set(full_key, json.dumps(value), ex=expiry)
        else:
            # Simple in-memory storage
            MEM_CACHE[full_key] = value
    except Exception as e:
        log.error(f"Cache SET failed for {bucket}:{key} -> {e}")

async def close_redis():
    """Gracefully close the Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        log.info("Redis connection closed.")
