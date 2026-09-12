from typing import List, Union
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    PROJECT_NAME: str = "Inquira API"
    VERSION: str = "1.0.1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://inquira_user:inquira_pass@localhost:5432/inquira_db"
    DATABASE_URL_SYNC: str = "postgresql://inquira_user:inquira_pass@localhost:5432/inquira_db"

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    USE_CELERY: bool = False

    # Qdrant Vector Store
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_HOST: str = "localhost"
    QDRANT_HTTP_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "inquira_chunks"

    # Security & Auth
    JWT_SECRET_KEY: str = "supersecretjwtkeychangeinproduction1234567890abcdef"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM & Embeddings
    OPENAI_API_KEY: str | None = None
    DENSE_EMBEDDING_MODEL: str = "text-embedding-3-small"
    DENSE_EMBEDDING_DIM: int = 1536
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    LLM_MODEL: str = "gpt-4o-mini"
    FAST_LLM_MODEL: str = "gpt-4o-mini"

    # Document Ingestion & Storage
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_FILES_PER_REQUEST: int = 10
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    ]
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    # RAG & Context
    CHAT_HISTORY_WINDOW: int = 10
    RRF_K: int = 60
    TOP_K_DENSE: int = 50
    TOP_K_SPARSE: int = 50
    TOP_K_FUSED: int = 25
    TOP_K_RERANKED: int = 5
    RERANKER_SCORE_THRESHOLD: float = 0.35

    # Rate Limiting & CORS
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except Exception:
                    pass
            return [item.strip() for item in v.split(",") if item.strip()]
        elif isinstance(v, list):
            return [str(item).strip() for item in v]
        return ["*"]

    @model_validator(mode='after')
    def validate_production_security(self) -> 'Settings':
        if self.CELERY_BROKER_URL == "redis://localhost:6379/0" and self.REDIS_URL != "redis://localhost:6379/0":
            self.CELERY_BROKER_URL = self.REDIS_URL
        if self.CELERY_RESULT_BACKEND == "redis://localhost:6379/0" and self.REDIS_URL != "redis://localhost:6379/0":
            self.CELERY_RESULT_BACKEND = self.REDIS_URL

        if self.ENVIRONMENT == 'production':
            if self.JWT_SECRET_KEY == "supersecretjwtkeychangeinproduction1234567890abcdef":
                raise ValueError("JWT_SECRET_KEY must be changed in production")
            if not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY must be set in production")
            if "inquira_pass" in self.DATABASE_URL:
                raise ValueError("DATABASE_URL must not use default password in production")
        return self


settings = Settings()
