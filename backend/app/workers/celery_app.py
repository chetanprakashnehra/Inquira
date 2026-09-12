import logging
from app.config import settings

logger = logging.getLogger(__name__)

class MockTask:
    def __init__(self, func):
        self.func = func

    def delay(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


class MockCelery:
    conf = {}

    def task(self, *args, **kwargs):
        def decorator(f):
            return MockTask(f)
        if len(args) == 1 and callable(args[0]):
            return MockTask(args[0])
        return decorator


if getattr(settings, "USE_CELERY", False):
    try:
        from celery import Celery
        celery = Celery(
            "inquira_workers",
            broker=settings.CELERY_BROKER_URL,
            backend=settings.CELERY_RESULT_BACKEND,
        )

        celery.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
            task_time_limit=300,
            task_soft_time_limit=240,
            worker_prefetch_multiplier=1,
            broker_connection_retry_on_startup=False,
            broker_connection_max_retries=1,
            broker_connection_timeout=2.0,
        )
        logger.info("Celery distributed task queue initialized.")
    except Exception as e:
        logger.warning(f"Could not initialize Celery ({e}). Using mock task runner.")
        celery = MockCelery()
else:
    logger.info("USE_CELERY is disabled. Running background tasks natively via FastAPI.")
    celery = MockCelery()
