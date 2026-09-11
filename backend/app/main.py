import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.core.database import init_db
from app.core.dependencies import limiter
from app.api.v1.router import api_router
from app.rag.retrieval.qdrant_client import qdrant_store

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown procedures."""
    logger.info("Starting up Inquira API...")
    import asyncio
    
    async def safe_init_db():
        try:
            logger.info("Initializing database schema asynchronously...")
            await init_db()
            logger.info("Database schema ready.")
        except Exception as e:
            logger.warning(f"Database initialization warning: {e}")

    asyncio.create_task(safe_init_db())
    yield
    logger.info("Shutting down Inquira API...")



def create_application() -> FastAPI:
    """FastAPI Application factory."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Inquira - Production Agentic RAG Platform with 5-Technique Hybrid Retrieval and Citation Verification",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # 1. Attach Rate Limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 2. Add CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Register API Routers
    app.include_router(api_router, prefix="/api")

    # 4. Root & Health Check Endpoints
    @app.get("/", tags=["Health"])
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "online",
            "docs": "/docs"
        }

    @app.get('/health', tags=['Health'])
    async def health_check():
        checks = {'api': 'ok'}
        overall = 'healthy'
        
        # Check database
        try:
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                await session.execute(text('SELECT 1'))
            checks['database'] = 'ok'
        except Exception as e:
            checks['database'] = f'error: {str(e)[:100]}'
            overall = 'degraded'
        
        # Check Redis
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            if r:
                await r.ping()
                checks['redis'] = 'ok'
            else:
                checks['redis'] = 'unavailable'
                if settings.ENVIRONMENT == 'production':
                    overall = 'degraded'
        except Exception as e:
            checks['redis'] = f'error: {str(e)[:100]}'
            overall = 'degraded'
        
        # Check Qdrant
        try:
            from app.rag.retrieval.qdrant_client import qdrant_store
            info = qdrant_store.client.get_collections()
            checks['qdrant'] = 'ok'
        except Exception as e:
            checks['qdrant'] = f'error: {str(e)[:100]}'
            overall = 'degraded'
        
        status_code = 200 if overall == 'healthy' else 503
        return JSONResponse(
            content={'status': overall, 'environment': settings.ENVIRONMENT, 'version': settings.VERSION, 'checks': checks},
            status_code=status_code
        )

    return app


app = create_application()
