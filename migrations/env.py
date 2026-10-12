from logging.config import fileConfig

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine


# =========================================
# Paths
# =========================================

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"

sys.path.insert(0, str(BACKEND_DIR))


# =========================================
# Imports
# =========================================

from config import settings
from database import Base
import models


# =========================================
# Alembic config
# =========================================

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# =========================================
# Migration functions
# =========================================

def run_migrations_offline():

    url = settings.database_url_sync

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():

    url = settings.database_url_sync

    print("ALEMBIC DATABASE URL:")
    print(url)

    engine = create_engine(
        url,
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


if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()