"""
Authentication utilities — JWT issuance/verification, bcrypt, FastAPI deps.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import redis as sync_redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ── Config ────────────────────────────────────────────────────────────────────

_JWT_SECRET_DEFAULT = "dev-secret-CHANGE-in-production"
JWT_SECRET    = os.getenv("JWT_SECRET", _JWT_SECRET_DEFAULT)
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "8"))

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Startup guard — refuse to run with the default dev secret
if JWT_SECRET == _JWT_SECRET_DEFAULT:
    print(
        "⚠️  WARNING: JWT_SECRET is using the insecure default value. "
        "Set a strong JWT_SECRET in your .env before going to production.",
        file=sys.stderr,
    )

# ── Redis connection pool ─────────────────────────────────────────────────────

_redis_pool: Optional[sync_redis.ConnectionPool] = None

def _get_redis_pool() -> sync_redis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = sync_redis.ConnectionPool.from_url(
            REDIS_URL, decode_responses=True, max_connections=20
        )
    return _redis_pool

def _redis() -> sync_redis.Redis:
    return sync_redis.Redis(connection_pool=_get_redis_pool())


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str, role: str, full_name: str = "") -> str:
    """
    Issue a signed JWT.
    Payload includes a unique `jti` so individual tokens can be blacklisted
    on logout without waiting for natural expiry.
    """
    jti = uuid.uuid4().hex
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS)
    payload = {
        "sub":       str(user_id),
        "email":     email,
        "role":      role,
        "full_name": full_name,
        "jti":       jti,
        "exp":       exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT. Returns payload dict or None on any failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Token blacklist (logout) ──────────────────────────────────────────────────

def blacklist_token(jti: str, exp_timestamp: int) -> None:
    """
    Add a token's jti to Redis until it would naturally have expired.
    Subsequent requests carrying this token will be rejected.
    """
    ttl = int(exp_timestamp - datetime.now(timezone.utc).timestamp())
    if ttl <= 0:
        return  # Already expired — no need to blacklist
    _redis().setex(f"token_blacklist:{jti}", ttl, "1")


def is_token_blacklisted(jti: str) -> bool:
    return bool(_redis().exists(f"token_blacklist:{jti}"))


# ── FastAPI security scheme ───────────────────────────────────────────────────

_http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request:     Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
) -> dict:
    """
    FastAPI dependency — extracts, verifies, and returns the JWT payload.
    Raises HTTP 401 if the token is missing, expired, invalid, or blacklisted.
    Also rejects requests from deactivated users.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_blacklisted(payload.get("jti", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Lazy import to avoid circular dependency (users_db → database → pool)
    from users_db import get_user_by_id
    user = get_user_by_id(payload["sub"])
    if not user or user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive or not found",
        )

    # Attach the DB row to the payload for convenience
    payload["_user"] = user
    return payload


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — requires the 'admin' role; raises HTTP 403 otherwise."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def get_client_ip(request: Request) -> str:
    """Best-effort client IP extraction (handles proxies)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""
