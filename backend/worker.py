import asyncio
import sys
from pathlib import Path

from celery import Celery

from config import settings


# ============================================================
# MAKE BACKEND DIRECTORY IMPORTABLE
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ============================================================
# CELERY APP
# ============================================================

celery_app = Celery(
    "inquira",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


# ============================================================
# CELERY CONFIG
# ============================================================

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


# ============================================================
# DOCUMENT PROCESSING TASK
# ============================================================

@celery_app.task
def process_document_task(document_id: str):

    print(
        f"\n[WORKER] Starting document: {document_id}"
    )

    # Windows + SQLAlchemy async compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    # Import only when the task actually runs.
    # This avoids the worker <-> ingestion circular import.
    from ingestion import process_document_by_id

    result = asyncio.run(
        process_document_by_id(document_id)
    )

    print(
        f"[WORKER] Finished document: {document_id}"
    )

    return result