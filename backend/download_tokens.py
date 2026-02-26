"""
One-time secure download tokens backed by Redis.

Workflow:
  1. Call create_token(resume_id) → UUID token stored with 15-min TTL.
  2. Call redeem_token(token) → atomically fetch + delete.
     Returns resume_id (int) if valid, None if expired or already used.
"""
import os
import uuid

import redis

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TOKEN_TTL   = 15 * 60   # seconds
KEY_PREFIX  = "dl_token:"

_redis = redis.from_url(REDIS_URL, decode_responses=True)


def create_token(resume_id: int) -> str:
    """Generate a one-time download token for resume_id. Returns the token string."""
    token = uuid.uuid4().hex
    _redis.setex(f"{KEY_PREFIX}{token}", TOKEN_TTL, str(resume_id))
    return token


def redeem_token(token: str) -> int | None:
    """
    Validate and consume a token (one-time use).
    Returns resume_id (int) on success, None if token is invalid or expired.
    """
    key = f"{KEY_PREFIX}{token}"
    # Atomically GET then DEL so concurrent requests can't double-redeem.
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
