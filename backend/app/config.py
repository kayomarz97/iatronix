from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = (
        "postgresql+asyncpg://medadmin:CHANGE_ME@iatronix-db:5432/medvectordb"
    )

    # Redis
    redis_url: str = "redis://iatronix-redis:6379/0"

    # Embedding & Vector search
    embedding_dim: int = 384
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_search_enabled: bool = True
    vector_top_k: int = 5
    vector_min_similarity: float = 0.3

    # PDF upload
    max_pdf_size_bytes: int = 20_971_520  # 20MB
    chunk_size: int = 2000  # characters (~500 tokens)
    chunk_overlap: int = 400  # characters (~100 tokens)

    # Auto-indexing
    pubmed_vector_cache_enabled: bool = True

    # Semantic query cache (pgvector SWR)
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.95  # cosine similarity minimum for a cache hit
    semantic_cache_swr_ttl_seconds: int = (
        604800  # 7 days — beyond this, revalidate in background
    )

    # BYOK
    byok_enabled: bool = True
    encryption_key: str = "CHANGE_ME"  # Fernet key for encrypting user LLM keys

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
    llm_timeout_seconds: int = 75  # disease format at 4096 tokens needs ~41s on Sonnet
    llm_max_tokens: int = 4096
    llm_retry_max_attempts: int = 1
    llm_retry_backoff_seconds: float = 2.0

    # Pipeline
    pipeline_timeout_seconds: int = 120
    proxy_timeout_seconds: int = 130

    # Cache TTL (seconds)
    cache_ttl_structured: int = 2592000  # 30 days
    cache_ttl_general: int = 86400  # 24 hours

    # Circuit breaker
    cb_fail_max: int = 5
    cb_reset_timeout: int = 30

    # Async log queue
    log_queue_max_size: int = 1000
    log_db_retry_max: int = 2
    log_db_retry_backoff: float = 1.0

    # Response storage
    max_response_jsonb_bytes: int = 1048576  # 1MB
    truncated_response_bytes: int = 512000  # 500KB

    # Frontend display
    truncation_display_limit: int = 20

    # Drug linker
    drug_link_min_score: float = 0.90
    fuzzy_max_distance_short: int = 1  # words 5-8 chars
    fuzzy_max_distance_long: int = 2  # words >8 chars

    # Classifier
    classifier_confidence_threshold: float = 0.7

    # Model routing (RAG optimization)
    model_haiku: str = "claude-haiku-4-5-20251001"
    model_sonnet: str = "claude-sonnet-4-20250514"
    model_routing_enabled: bool = True

    # LLM server-side fallback keys (used when user has no BYOK key set)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # External API fetching
    api_fetch_enabled: bool = True
    api_fetch_timeout_seconds: float = 5.0
    pubmed_api_key: Optional[str] = None
    openfda_api_key: Optional[str] = None
    nice_api_key: Optional[str] = None

    # Token budgets
    llm_max_tokens_format: int = 2048  # format mode — drug/procedure/evidence (Haiku)
    llm_max_tokens_format_disease: int = (
        4096  # format mode — disease (Sonnet, needs more for classifications)
    )
    llm_max_tokens_generate: int = (
        2048  # generate/fallback mode — 2048 is sufficient for summary + key_points
    )

    # Cloudflare R2 Storage (for PDF uploads)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "iatronix-documents"
    r2_public_url: str = ""  # e.g. https://pub-xxx.r2.dev

    # PDF lifecycle (non-approved docs auto-deleted after N hours)
    pdf_non_approved_ttl_hours: int = 48
    pdf_cleanup_interval_minutes: int = 60

    # LLM cost estimates shown to users (USD per million tokens, Anthropic pricing)
    cost_haiku_input_per_m: float = 0.25
    cost_haiku_output_per_m: float = 1.25
    cost_sonnet_input_per_m: float = 3.0
    cost_sonnet_output_per_m: float = 15.0

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
