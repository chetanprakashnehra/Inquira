from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ========================================================
    # APPLICATION
    # ========================================================

    environment: str = "development"
    log_level: str = "INFO"

    # ========================================================
    # DATABASE
    # ========================================================

    database_url: str
    database_url_sync: str

    # ========================================================
    # REDIS
    # ========================================================

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = "redis://localhost:6379/0"

    celery_broker_url: str = (
        "redis://localhost:6379/0"
    )

    celery_result_backend: str = (
        "redis://localhost:6379/0"
    )

    # ========================================================
    # QDRANT
    # ========================================================

    qdrant_host: str = "localhost"
    qdrant_http_port: int = 6333
    qdrant_grpc_port: int = 6334

    qdrant_url: str = (
        "http://localhost:6333"
    )

    qdrant_api_key: str | None = None

    qdrant_collection_name: str = (
        "inquira_chunks"
    )

    # ========================================================
    # JWT
    # ========================================================

    jwt_secret_key: str

    jwt_algorithm: str = "HS256"

    access_token_expire_minutes: int = 60

    refresh_token_expire_days: int = 7

    # ========================================================
    # AI
    # ========================================================

    # Gemini is still used for embeddings
    gemini_api_key: str

    dense_embedding_model: str = (
        "gemini-embedding-001"
    )

    dense_embedding_dim: int = 1536

    # Groq is used for LLM generation
    groq_api_key: str

    llm_model: str = (
        "openai/gpt-oss-120b"
    )

    fast_llm_model: str = (
        "openai/gpt-oss-20b"
    )

    # Cross encoder
    enable_reranker: bool = False

    reranker_model: str = (
        "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )

    # ========================================================
    # UPLOAD
    # ========================================================

    max_upload_size_mb: int = 50

    max_files_per_request: int = 10

    # ========================================================
    # CHUNKING
    # ========================================================

    chunk_size: int = 800

    chunk_overlap: int = 150

    # ========================================================
    # CORS
    # ========================================================

    cors_origins: list[str] = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ========================================================
    # RATE LIMIT
    # ========================================================

    rate_limit_per_minute: int = 60

    # ========================================================
    # ENVIRONMENT FILE
    # ========================================================

    model_config = SettingsConfigDict(
    env_file="../.env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
    )


settings = Settings()