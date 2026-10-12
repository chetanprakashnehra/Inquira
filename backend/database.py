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

engine = create_async_engine(
    settings.database_url,
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