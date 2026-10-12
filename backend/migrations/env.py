from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context

import sys
from pathlib import Path


# ==========================================
# Project paths
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"

sys.path.append(str(BACKEND_DIR))


# ==========================================
# Application imports
# ==========================================

from config import settings
from database import Base
import models


# ==========================================
# Alembic configuration
# ==========================================

config = context.config


if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# SQLAlchemy metadata used by Alembic
target_metadata = Base.metadata


# ==========================================
# Offline migrations
# ==========================================

def run_migrations_offline() -> None:

    database_url = (
        settings.database_url_sync
        or settings.database_url.replace("+asyncpg", "")
    )

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
    )

    with context.begin_transaction():
        context.run_migrations()


# ==========================================
# Online migrations
# ==========================================

def run_migrations_online() -> None:

    database_url = (
        settings.database_url_sync
        or settings.database_url.replace("+asyncpg", "")
    )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    with engine.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


# ==========================================
# Run
# ==========================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()