from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine
import models

from auth import router as auth_router
from ingestion import router as ingestion_router
from chat import router as chat_router
from sessions import router as sessions_router



# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("Starting Inquira...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        from ingestion import ensure_qdrant_collection
        ensure_qdrant_collection()
    except Exception as exc:
        print(f"Qdrant collection initialization deferred: {exc}")

    yield

    print("Shutting down Inquira...")

    await engine.dispose()


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Inquira",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(
    auth_router
)

app.include_router(
    ingestion_router
)

app.include_router(
    chat_router
)

app.include_router(
    sessions_router
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():

    return {
        "name": "Inquira",
        "status": "running",
    }