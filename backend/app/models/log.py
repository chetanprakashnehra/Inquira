import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, Uuid
from app.core.database import Base


class ApplicationLog(Base):
    __tablename__ = "application_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(20), nullable=False, index=True)  # INFO, WARNING, ERROR
    source = Column(String(100), nullable=False)  # e.g., celery.tasks.process_document, api.chat
    message = Column(Text, nullable=False)
    metadata_json = Column("metadata", JSON, nullable=True)  # task_id, doc_id, traceback etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
