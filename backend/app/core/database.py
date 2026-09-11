from typing import AsyncGenerator
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

logger = logging.getLogger(__name__)

db_url = settings.DATABASE_URL

# asyncpg doesn't support query params like sslmode, channel_binding, etc.
# Strip them from the URL and configure SSL via connect_args instead.
_needs_ssl = False
if "asyncpg" in db_url:
    # Auto-enable SSL for Neon or any non-localhost database
    if "sslmode=require" in db_url or "ssl=require" in db_url or "neon.tech" in db_url or "localhost" not in db_url:
        _needs_ssl = True
    if "?" in db_url:
        db_url = db_url.split("?")[0]

# Check if asyncpg is missing and fallback to aiosqlite for local development/testing
if "asyncpg" in db_url:
    try:
        import asyncpg  # noqa
    except ImportError:
        if settings.ENVIRONMENT == "development":
            logger.warning("asyncpg driver not installed. Falling back to sqlite+aiosqlite for local execution.")
            db_url = "sqlite+aiosqlite:///./inquira_dev.db"
        else:
            raise RuntimeError("asyncpg driver not installed, but required in non-development environments.")

# Construct async engine with appropriate pool arguments and timeouts
engine_kwargs = {"echo": False, "future": True}
if "sqlite" in db_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_timeout"] = 10.0
    connect_args = {"timeout": 10.0}
    if _needs_ssl:
        import ssl as _ssl
        ssl_ctx = _ssl.create_default_context()
        connect_args["ssl"] = ssl_ctx
    engine_kwargs["connect_args"] = connect_args

async_engine = create_async_engine(db_url, **engine_kwargs)



AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async SQLAlchemy session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database schema tables if not existing."""
    async with async_engine.begin() as conn:
        from app.models import user, knowledge_base, document, chunk, chat, log  # noqa
        # WARNING: Base.metadata.create_all is for development/testing only.
        # In production, replace this with Alembic migrations (e.g., `alembic upgrade head`).
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully.")
