import asyncio
import logging
from celery import Celery
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Celery Application
celery_app = Celery(
    "booking_tasks",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sweep-expired-seat-holds-every-30-seconds": {
            "task": "app.workers.celery_worker.sweep_expired_holds_task",
            "schedule": 30.0,
        },
    },
)


@celery_app.task(name="app.workers.celery_worker.sweep_expired_holds_task")
def sweep_expired_holds_task() -> int:
    """Synchronous Celery task wrapper that runs the async DB sweep."""
    from app.core.database import AsyncSessionLocal
    from app.services.booking_service import BookingService

    async def _async_sweep():
        async with AsyncSessionLocal() as session:
            count = await BookingService.release_expired_holds(session)
            logger.info(f"[Celery Worker] Swept and released {count} expired seat holds.")
            return count

    return asyncio.run(_async_sweep())

