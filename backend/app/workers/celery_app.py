import logging
from app.config import settings

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    celery = Celery(
        "inquira_workers",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["app.workers.tasks"]
    )

    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,  # 5 min hard limit
        task_soft_time_limit=240,
        worker_prefetch_multiplier=1,
    )
except ImportError:
    if settings.ENVIRONMENT == "development":
        logger.warning("Celery is not installed in the local environment. Initializing mock fallback.")
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

        celery = MockCelery()
    else:
        raise RuntimeError("Celery is not installed, but required in non-development environments.")
