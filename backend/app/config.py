from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str = "CHANGE_ME"
    openrouter_api_key: str = "CHANGE_ME"
    iatronix_api_key: str = "CHANGE_ME"

    # Database
    database_url: str = "postgresql+asyncpg://medadmin:CHANGE_ME@iatronix-db:5432/medvectordb"

    # Redis
    redis_url: str = "redis://iatronix-redis:6379/0"

    # Embedding
    embedding_dim: int = 1536

    # CORS
    allowed_origins: str = "http://localhost:3100"

    # Sentry
    sentry_dsn: Optional[str] = None

    # Prompt versioning
    prompt_version: int = 1

    # Logging
    log_level: str = "INFO"

    # --- Limits (single source of truth) ---

    # Payload
    max_request_body_bytes: int = 65536  # 64KB
    max_query_length: int = 2000

    # Rate limiting
    rate_limit_ip_per_minute: int = 30
    rate_limit_key_per_minute: int = 10

    # LLM
    llm_timeout_seconds: int = 45
    llm_max_tokens: int = 4096
    llm_retry_max_attempts: int = 1
    llm_retry_backoff_seconds: float = 2.0

    # Pipeline
    pipeline_timeout_seconds: int = 120
    proxy_timeout_seconds: int = 130

    # Cache TTL (seconds)
    cache_ttl_structured: int = 2592000   # 30 days
    cache_ttl_general: int = 86400        # 24 hours

    # Circuit breaker
    cb_fail_max: int = 5
    cb_reset_timeout: int = 30

    # Async log queue
    log_queue_max_size: int = 1000
    log_db_retry_max: int = 2
    log_db_retry_backoff: float = 1.0

    # Response storage
    max_response_jsonb_bytes: int = 1048576  # 1MB
    truncated_response_bytes: int = 512000   # 500KB

    # Frontend display
    truncation_display_limit: int = 20

    # Drug linker
    drug_link_min_score: float = 0.90
    fuzzy_max_distance_short: int = 1   # words 5-8 chars
    fuzzy_max_distance_long: int = 2    # words >8 chars

    # Classifier
    classifier_confidence_threshold: float = 0.7

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
