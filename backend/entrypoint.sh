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
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
