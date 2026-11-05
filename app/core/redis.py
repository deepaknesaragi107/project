import logging
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Get the active Redis async client instance or initialize one."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.redis_connection_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return redis_client


async def close_redis() -> None:
    """Close active Redis client connections."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection closed.")

