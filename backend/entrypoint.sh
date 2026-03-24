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

echo "Starting backend server..."
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --keepalive 5 \
  --access-logfile - \
  --error-logfile -
