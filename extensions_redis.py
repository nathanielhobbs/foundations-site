# extensions_redis.py
import os, redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Decode to str, short socket timeouts so we don't hang behind nginx
r = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_timeout=2.0,
    socket_connect_timeout=1.5,
    socket_keepalive=True,
)

