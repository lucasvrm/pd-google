#!/usr/bin/env bash
set -euo pipefail

# Default to redis URL from env or config default
REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"

wait_for_redis() {
  echo "Waiting for Redis at ${REDIS_URL}..."
  python - <<PY
import os
import sys
import time
from urllib.parse import urlparse

import redis

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
max_wait = int(os.getenv("REDIS_WAIT_SECONDS", "30"))
sleep_interval = 2

parsed = urlparse(redis_url)
client = redis.Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)

start = time.time()
while True:
    try:
        client.ping()
        print(f"Redis is available at {redis_url}")
        sys.exit(0)
    except Exception as exc:
        elapsed = time.time() - start
        if elapsed > max_wait:
            print(f"Redis not available after {int(elapsed)}s: {exc}. Continuing with cache fallback.")
            sys.exit(0)
        time.sleep(sleep_interval)
PY
}

wait_for_redis

echo "Starting Gunicorn..."
exec "$@"
