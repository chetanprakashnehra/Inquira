from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from config import settings


# ==========================================
# Database Engine
# ==========================================

db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

parsed = urlparse(db_url)
query_params = parse_qs(parsed.query)
ssl_required = "sslmode" in query_params or "ssl" in query_params or "neon.tech" in db_url

# asyncpg does not accept libpq arguments like 'sslmode' or 'channel_binding' in the query string
query_params.pop("sslmode", None)
query_params.pop("channel_binding", None)
new_query = urlencode(query_params, doseq=True)
clean_db_url = urlunparse(parsed._replace(query=new_query))

connect_args = {}
if ssl_required:
    connect_args["ssl"] = True

engine = create_async_engine(
    clean_db_url,
    connect_args=connect_args,
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