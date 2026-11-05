import asyncio
import logging
import uuid
from typing import List, Optional
from contextlib import asynccontextmanager
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Atomic release Lua script: only delete the key if the value matches the owner token
LUA_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class LockAcquisitionError(Exception):
    """Raised when a distributed lock cannot be acquired within timeout."""
    pass


class DistributedLock:
    """
    Production-grade Redis Distributed Lock implementing:
    - Atomic acquisition with NX and PX (TTL)
    - Unique token per lock instance to prevent releasing other clients' locks
    - Atomic Lua release script
    - Deadlock prevention via sorted multi-resource acquisition
    """

    def __init__(
        self,
        lock_key: str,
        timeout: int = settings.LOCK_TIMEOUT_SECONDS,
        acquire_timeout: float = settings.LOCK_ACQUIRE_TIMEOUT_SECONDS,
        retry_interval: float = 0.05,
    ):
        self.lock_key = f"lock:{lock_key}"
        self.timeout = timeout
        self.acquire_timeout = acquire_timeout
        self.retry_interval = retry_interval
        self.token = str(uuid.uuid4())
        self.client: Optional[aioredis.Redis] = None
        self._acquired = False

    async def acquire(self) -> bool:
        """Attempt to acquire lock with retry until acquire_timeout expires."""
        try:
            self.client = await get_redis_client()
        except Exception as e:
            logger.warning(f"Redis unavailable for lock {self.lock_key}: {e}. Proceeding with DB transaction lock.")
            return True

        start_time = asyncio.get_event_loop().time()
        timeout_ms = int(self.timeout * 1000)

        while True:
            try:
                # SET key token NX PX timeout_ms
                acquired = await self.client.set(
                    self.lock_key,
                    self.token,
                    nx=True,
                    px=timeout_ms,
                )
                if acquired:
                    self._acquired = True
                    logger.debug(f"Acquired lock: {self.lock_key} with token: {self.token}")
                    return True
            except Exception as e:
                logger.error(f"Error communicating with Redis while acquiring lock: {e}")
                raise LockAcquisitionError(f"Redis lock error: {str(e)}")

            if (asyncio.get_event_loop().time() - start_time) >= self.acquire_timeout:
                logger.warning(f"Timed out acquiring lock for {self.lock_key}")
                return False

            await asyncio.sleep(self.retry_interval)

    async def release(self) -> None:
        """Release lock atomically using Lua script."""
        if not self._acquired or not self.client:
            return

        try:
            res = await self.client.eval(LUA_RELEASE_LOCK, 1, self.lock_key, self.token)
            if res:
                logger.debug(f"Released lock: {self.lock_key}")
            else:
                logger.warning(f"Lock {self.lock_key} was already expired or owned by another worker.")
        except Exception as e:
            logger.error(f"Error releasing lock {self.lock_key}: {e}")
        finally:
            self._acquired = False

    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise LockAcquisitionError(
                f"Resource is temporarily locked by another transaction. Please try again."
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


@asynccontextmanager
async def multi_resource_lock(
    resource_keys: List[str],
    timeout: int = settings.LOCK_TIMEOUT_SECONDS,
    acquire_timeout: float = settings.LOCK_ACQUIRE_TIMEOUT_SECONDS,
):
    """
    Acquire locks for multiple resources in deterministic sorted order
    to prevent deadlock between concurrent transactions.
    """
    # Sort keys deterministically to prevent circular wait deadlocks
    sorted_keys = sorted(list(set(resource_keys)))
    acquired_locks: List[DistributedLock] = []

    try:
        for key in sorted_keys:
            lock = DistributedLock(key, timeout=timeout, acquire_timeout=acquire_timeout)
            acquired = await lock.acquire()
            if not acquired:
                raise LockAcquisitionError(
                    f"Conflict: Resource '{key}' is locked by another booking. Aborting hold."
                )
            acquired_locks.append(lock)
        yield
    finally:
        # Release in reverse order of acquisition
        for lock in reversed(acquired_locks):
            await lock.release()

