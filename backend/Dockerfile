FROM python:3.12-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV SENTENCE_TRANSFORMERS_HOME=/app/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "gunicorn>=22.0.0" \
    "langchain>=0.3.0" \
    "langchain-anthropic>=0.3.0" \
    "langchain-openai>=0.3.0" \
    "langchain-text-splitters>=0.3.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.30.0" \
    "pgvector>=0.3.0" \
    "alembic>=1.14.0" \
    "tenacity>=9.0.0" \
    "json-repair>=0.30.0" \
    "slowapi>=0.1.9" \
    "redis>=5.0.0" \
    "python-json-logger>=2.0.0" \
    "sentry-sdk[fastapi]>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "bcrypt>=4.2.0" \
    "pybreaker>=1.2.0" \
    "python-Levenshtein>=0.26.0" \
    "metaphone>=0.6" \
    "httpx>=0.27.0" \
    "sentence-transformers>=3.0.0" \
    "pdfplumber>=0.11.0" \
    "python-multipart>=0.0.9" \
    "lxml>=5.0.0" \
    "cryptography>=43.0.0" \
    "email-validator>=2.0.0" \
    "boto3>=1.34.0" \
    "aiofiles>=23.0.0" \
    "dspy-ai>=2.5.0"

COPY app/ app/
COPY alembic.ini .
COPY migrations/ migrations/
COPY entrypoint.sh .
COPY data/ data/

RUN chmod +x entrypoint.sh && mkdir -p /app/logs /app/models

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
