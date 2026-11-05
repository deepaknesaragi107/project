import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import init_db, close_db, AsyncSessionLocal
from app.core.redis import get_redis_client, close_redis
from app.core.locks import LockAcquisitionError
from app.api.v1 import api_v1_router
from app.services.booking_service import BookingService

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ticketing-backend")


async def periodic_hold_sweeper(interval_seconds: int = 20):
    """Background task to release expired seat holds every 20 seconds."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with AsyncSessionLocal() as session:
                released = await BookingService.release_expired_holds(session)
                if released > 0:
                    logger.info(f"[Sweeper] Automatically released {released} expired seat hold(s).")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Sweeper Error] Error sweeping expired holds: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and graceful shutdown."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode...")
    
    # 1. Initialize DB tables
    try:
        await init_db()
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # 2. Ping Redis
    try:
        r = await get_redis_client()
        await r.ping()
        logger.info("Redis connection established.")
    except Exception as e:
        logger.warning(f"Redis is currently unreachable: {e}. Distributed locking will fall back to DB row locks.")

    # 3. Start background hold sweeper
    sweeper_task = asyncio.create_task(periodic_hold_sweeper())

    yield

    # Shutdown
    logger.info("Shutting down application...")
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass

    await close_redis()
    await close_db()
    logger.info("Application cleanup completed.")


# FastAPI Application
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Production-grade Backend & AI Architect service for Online Ticketing & Booking.\n\n"
        "Features:\n"
        "- ⚡ High-throughput asynchronous FastAPI framework\n"
        "- 🐘 PostgreSQL DB schema with SQLAlchemy 2.0 Async ORM\n"
        "- 🔒 Redis Distributed Locks (Anti-Overbooking / Race-Condition Prevention)\n"
        "- 🤖 Conversational AI Agent with Tool Calling (OpenAI & Gemini)\n"
        "- ⏱️ Background worker for automatic expiry of stale seat holds\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers
@app.exception_handler(LockAcquisitionError)
async def handle_lock_error(request: Request, exc: LockAcquisitionError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc), "error_type": "CONCURRENCY_LOCK_CONFLICT"},
    )


# Include API Routers
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["System Health"])
async def health_check():
    """System health check endpoint verifying database and Redis connectivity."""
    db_status = "UNKNOWN"
    redis_status = "UNKNOWN"

    # Test DB
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "HEALTHY"
    except Exception as e:
        db_status = f"UNHEALTHY: {str(e)}"

    # Test Redis
    try:
        r = await get_redis_client()
        await r.ping()
        redis_status = "HEALTHY"
    except Exception as e:
        redis_status = f"UNHEALTHY: {str(e)}"

    overall = "HEALTHY" if db_status == "HEALTHY" and redis_status == "HEALTHY" else "DEGRADED"

    return {
        "status": overall,
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": db_status,
        "redis": redis_status,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

