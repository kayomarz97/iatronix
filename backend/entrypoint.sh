#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

# Clear Redis cache on deployment when FLUSH_REDIS=1
if [ "${FLUSH_REDIS}" = "1" ]; then
    echo "Flushing Redis cache (FLUSH_REDIS=1)..."
    python -c "
import redis, os
r = redis.from_url(os.environ.get('REDIS_URL', 'redis://iatronix-redis:6379/0'))
r.flushdb()
print('Redis cache flushed successfully')
" 2>/dev/null || echo "Redis flush skipped (not available)"
fi

WORKERS="${GUNICORN_WORKERS:-4}"
echo "Starting backend server (workers=${WORKERS})..."
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WORKERS}" \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --keep-alive 30 \
  --worker-connections 200 \
  --access-logfile - \
  --error-logfile -
