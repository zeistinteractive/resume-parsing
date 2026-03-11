"""
One-time secure download tokens backed by Redis.

Workflow:
  1. Call create_token(resume_id) → token stored with 15-min TTL.
  2. Call redeem_token(token) → atomically fetch + delete.
     Returns resume_id (int) if valid, None if expired or already used.
"""
import os
import secrets

import redis

REDIS_URL  = os.getenv("REDIS_URL", "redis://redis:6379/0")
TOKEN_TTL  = int(os.getenv("DOWNLOAD_TOKEN_TTL", str(15 * 60)))   # seconds (default 15 min)
KEY_PREFIX = "dl_token:"

# Connection pool — shared across all requests in this process
_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True, max_connections=10)
_redis = redis.Redis(connection_pool=_pool)


def create_token(resume_id: int) -> str:
    """Generate a cryptographically secure one-time download token. Returns the token string."""
    token = secrets.token_hex(32)   # 256-bit entropy — much stronger than uuid4
    _redis.setex(f"{KEY_PREFIX}{token}", TOKEN_TTL, str(resume_id))
    return token


def redeem_token(token: str) -> int | None:
    """
    Validate and consume a token (one-time use).
    Returns resume_id (int) on success, None if token is invalid or expired.
    """
    # Validate token format — must be exactly 64 hex chars
    if not token or len(token) != 64 or not all(c in "0123456789abcdef" for c in token):
        return None

    key = f"{KEY_PREFIX}{token}"
    # Atomically GET then DEL — concurrent requests cannot double-redeem.
    with _redis.pipeline() as pipe:
        pipe.get(key)
        pipe.delete(key)
        results = pipe.execute()

    value = results[0]
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
