from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings


# ==========================================
# Database Engine
# ==========================================

db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    db_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


# ==========================================
# Session Factory
# ==========================================

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ==========================================
# Base Model
# ==========================================

class Base(DeclarativeBase):
    pass


# ==========================================
# FastAPI Database Dependency
# ==========================================

async def get_db():
    async with SessionLocal() as session:
        yield session