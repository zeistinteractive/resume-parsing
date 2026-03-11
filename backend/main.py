"""
Resume Engine MVP - FastAPI Backend
Handles upload, parsing, search of resumes.
"""
import hashlib
import io
import os
import uuid
import zipfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv(override=True)

from database import (
    init_db, insert_resume,
    get_all_resumes, get_resume_by_id, get_resumes_by_ids, delete_resume,
    count_resumes, search_resumes,
    autocomplete_titles, autocomplete_locations, autocomplete_skills,
    list_saved_searches, create_saved_search, delete_saved_search,
    log_download, get_download_history,
    get_resume_by_hash, get_uploaders,
)
from tasks import parse_resume_task
from events import sse_endpoint
import download_tokens
from users_db import (
    init_users_db, get_user_by_email, get_user_by_id as get_user_by_id_db,
    list_users, create_user, update_user, set_user_status,
    increment_failed_logins, reset_login_state,
    update_password, set_must_change_password,
    set_reset_token, clear_reset_token, get_user_by_reset_token,
    log_audit, get_audit_logs, count_users,
)
from email_utils import (
    send_welcome_email, send_password_reset_email, send_admin_reset_email,
)
from auth_utils import (
    hash_password, verify_password,
    create_access_token, decode_token,
    blacklist_token, is_token_blacklisted,
    get_current_user, require_admin,
    get_client_ip,
)

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Resume Engine API", version="1.0.0")

# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ───────────────────────────────────────────────────────────────────────
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE_MB = 5

# ─── Auth Middleware ───────────────────────────────────────────────────────────
# Protects every /api/* route except the explicit public ones below.
# SSE (/api/events) and the one-time token download stay public because
# EventSource cannot set custom headers and the download token is its own credential.

_PUBLIC_PATHS = frozenset([
    "/api/health",
    "/api/events",
    "/api/auth/login",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
])
_PUBLIC_PREFIX = "/api/download/file/"


@app.middleware("http")
async def enforce_auth(request: Request, call_next):
    path = request.url.path

    # Non-API paths (e.g. static assets served by nginx) pass straight through
    if not path.startswith("/api/"):
        return await call_next(request)

    # Explicitly public API routes
    if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIX):
        return await call_next(request)

    # All other /api/* routes require a valid JWT
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(auth[7:])
    if not payload:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_blacklisted(payload.get("jti", "")):
        return JSONResponse(
            status_code=401,
            content={"detail": "Token has been revoked — please log in again"},
        )

    user = get_user_by_id_db(payload["sub"])
    if not user or user["status"] != "active":
        return JSONResponse(
            status_code=401,
            content={"detail": "Account is inactive or not found"},
        )

    # Attach decoded user to request state for use by endpoint Depends
    payload["_user"] = user
    request.state.current_user = payload
    return await call_next(request)
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


@app.on_event("startup")
async def startup():
    init_db()
    init_users_db()
    _bootstrap_admin()
    print("✅ Resume Engine API started")


def _bootstrap_admin():
    """
    Create a default Admin account from env vars if no users exist yet.
    ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env before first run.
    Safe to call on every restart — only acts when the users table is empty.
    """
    if count_users() > 0:
        return

    email    = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    name     = os.getenv("ADMIN_NAME", "Admin")

    if not email or not password:
        raise RuntimeError(
            "No users exist and ADMIN_EMAIL / ADMIN_PASSWORD are not set. "
            "Add them to your .env file and restart."
        )

    create_user(
        full_name     = name,
        email         = email,
        password_hash = hash_password(password),
        role          = "admin",
    )
    print(f"🔑 Bootstrap admin created: {email}")


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Resume Engine API"}


# ─── Auth ──────────────────────────────────────────────────────────────────────

import re as _re
from pydantic import BaseModel as _BM, field_validator

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LoginIn(_BM):
    email:    str
    password: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v):
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email format")
        return v.strip().lower()


class ChangePasswordIn(_BM):
    current_password: str
    new_password:     str

    @field_validator("new_password")
    @classmethod
    def _min_length(cls, v):
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters")
        return v


@app.post("/api/auth/login")
@limiter.limit(os.getenv("LOGIN_RATE_LIMIT", "10/minute"))
def login(body: LoginIn, request: Request):
    """
    US-001 + US-005 — Authenticate with email + password.
    Issues a JWT on success. Enforces brute-force lockout after 5 failures.
    """
    from datetime import datetime, timezone

    ip = get_client_ip(request)
    user = get_user_by_email(body.email)

    # Unknown email — generic error (don't reveal whether account exists)
    if not user:
        log_audit(body.email, "USER_LOGIN_FAILED", ip, "failure")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Account locked?
    locked_until = user.get("locked_until")
    if locked_until:
        # locked_until is already an ISO string from _user_dict()
        from datetime import datetime as _dt
        lu = _dt.fromisoformat(locked_until)
        if lu > _dt.now(timezone.utc):
            log_audit(body.email, "USER_LOGIN_FAILED", ip, "failure",
                      user_id=user["id"])
            raise HTTPException(
                status_code=403,
                detail=f"Account locked due to too many failed attempts. "
                       f"Try again after {lu.strftime('%H:%M UTC')}",
            )

    # Deactivated?
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is inactive")

    # Wrong password
    if not verify_password(body.password, user["password_hash"]):
        count = increment_failed_logins(user["id"])
        log_audit(body.email, "USER_LOGIN_FAILED", ip, "failure",
                  user_id=user["id"])
        remaining = max(0, 5 - count)
        if count >= 5:
            raise HTTPException(status_code=403,
                                detail="Account locked for 15 minutes due to too many failed attempts")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid email or password ({remaining} attempt(s) remaining before lockout)",
        )

    # Success
    reset_login_state(user["id"])
    token = create_access_token(user["id"], user["email"], user["role"], user["full_name"])
    log_audit(user["email"], "USER_LOGIN", ip, "success", user_id=user["id"])

    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":        user["id"],
            "full_name": user["full_name"],
            "email":     user["email"],
            "role":      user["role"],
        },
    }


@app.post("/api/auth/logout")
def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """
    US-002 — Invalidate the current token via Redis blacklist.
    Subsequent requests with the same token receive HTTP 401.
    """
    jti = current_user.get("jti", "")
    exp = current_user.get("exp", 0)
    if jti:
        blacklist_token(jti, exp)

    ip = get_client_ip(request)
    log_audit(current_user["email"], "USER_LOGOUT", ip, "success",
              user_id=current_user["sub"])
    return {"message": "Logged out successfully"}


@app.post("/api/auth/change-password")
def change_password(
    body:         ChangePasswordIn,
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    """
    US-003 — Change own password. Requires current password confirmation.
    Invalidates all existing tokens by blacklisting the current one.
    """
    user = current_user["_user"]

    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    update_password(user["id"], hash_password(body.new_password))

    # Invalidate the current session token
    jti = current_user.get("jti", "")
    exp = current_user.get("exp", 0)
    if jti:
        blacklist_token(jti, exp)

    ip = get_client_ip(request)
    log_audit(user["email"], "PASSWORD_CHANGED", ip, "success",
              user_id=user["id"])

    return {"message": "Password changed successfully. Please log in again."}


@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's public profile."""
    u = current_user["_user"]
    return {
        "id":                   u["id"],
        "full_name":            u["full_name"],
        "email":                u["email"],
        "role":                 u["role"],
        "status":               u["status"],
        "last_login_at":        u.get("last_login_at"),
        "must_change_password": u.get("must_change_password", False),
    }


# ─── SSE Event Stream ──────────────────────────────────────────────────────────

@app.get("/api/events")
async def events(request: Request):
    return await sse_endpoint(request)


# ─── Upload Resume ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_resume(
    file:         UploadFile = File(...),
    current_user: dict       = Depends(get_current_user),
):
    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{suffix}'. Allowed: PDF, DOCX, DOC"
        )

    # Read file content and check size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f}MB). Maximum size is {MAX_FILE_SIZE_MB}MB."
        )

    # ── Duplicate detection (file hash) ───────────────────────────────────────
    file_hash = hashlib.sha256(contents).hexdigest()
    existing  = get_resume_by_hash(file_hash)
    if existing:
        return {
            "id":           existing["id"],
            "filename":     file.filename,
            "status":       existing["parse_status"],
            "duplicate":    True,
            "duplicate_of": existing["id"],
            "message":      f"Duplicate file — already uploaded as resume #{existing['id']}",
        }

    # ── Fresh upload ──────────────────────────────────────────────────────────
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(contents)

    resume_id = insert_resume(
        file.filename, str(file_path),
        file_hash        = file_hash,
        uploaded_by_id   = current_user.get("sub"),
        uploaded_by_name = current_user.get("full_name", current_user.get("email", "")),
    )

    # Enqueue parse job — persisted in Redis, survives server restarts
    parse_resume_task.delay(resume_id, str(file_path))

    return {
        "id":           resume_id,
        "filename":     file.filename,
        "status":       "queued",
        "duplicate":    False,
        "duplicate_of": None,
        "message":      "Resume uploaded. Parsing in progress…",
    }


# ─── List Resumes ──────────────────────────────────────────────────────────────

@app.get("/api/resumes")
def list_resumes(limit: int = 20, offset: int = 0):
    total = count_resumes()
    items = get_all_resumes(limit, offset)
    return {"total": total, "items": items, "limit": limit, "offset": offset}


# ─── Get Single Resume ─────────────────────────────────────────────────────────

@app.get("/api/resumes/{resume_id}")
def get_resume(resume_id: int):
    resume = get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


# ─── Delete Resume ─────────────────────────────────────────────────────────────

@app.delete("/api/resumes/{resume_id}")
def remove_resume(resume_id: int, _: dict = Depends(require_admin)):
    resume = get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    file_path = Path(resume["file_path"])
    if file_path.exists():
        file_path.unlink()

    success = delete_resume(resume_id)
    return {"success": success, "message": f"Resume {resume_id} deleted"}


# ─── Download Original File ────────────────────────────────────────────────────

@app.get("/api/resumes/{resume_id}/download")
def download_resume(resume_id: int, request: Request):
    resume = get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    file_path = Path(resume["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    log_download(
        resume_id    = resume_id,
        ip_address   = request.client.host if request.client else "",
        user_agent   = request.headers.get("user-agent", ""),
        download_type = "single",
    )

    return FileResponse(
        path=str(file_path),
        filename=resume["filename"],
        media_type="application/octet-stream"
    )


# ─── Search Resumes ────────────────────────────────────────────────────────────

@app.get("/api/search")
def search(
    q:             str  = "",
    mode:          str  = "or",
    title:         str  = "",
    skills:        str  = "",       # comma-separated, e.g. "Python,React"
    exp_min:       int  = None,
    exp_max:       int  = None,
    location:      str  = "",
    education:     str  = "",
    notice_period: str  = "",
    date_from:     str  = None,     # ISO date string YYYY-MM-DD
    date_to:       str  = None,
    uploaded_by:   str  = None,     # user UUID — filter by uploader
    sort:          str  = "relevance",
    limit:         int  = 25,
    offset:        int  = 0,
):
    if mode not in ("and", "or"):
        raise HTTPException(status_code=400, detail="mode must be 'and' or 'or'")
    if sort not in ("relevance", "exp_desc", "exp_asc", "date_desc"):
        raise HTTPException(status_code=400, detail="sort must be relevance | exp_desc | exp_asc | date_desc")
    if limit not in (25, 50, 100):
        raise HTTPException(status_code=400, detail="limit must be 25, 50, or 100")

    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []

    return search_resumes(
        query         = q.strip(),
        mode          = mode,
        title         = title.strip(),
        skills        = skills_list,
        exp_min       = exp_min,
        exp_max       = exp_max,
        location      = location.strip(),
        education     = education.strip(),
        notice_period = notice_period.strip(),
        date_from     = date_from,
        date_to       = date_to,
        uploaded_by   = uploaded_by.strip() if uploaded_by else None,
        sort          = sort,
        limit         = limit,
        offset        = offset,
    )


# ─── Uploaders list ────────────────────────────────────────────────────────────

@app.get("/api/uploaders")
def list_uploaders(_: dict = Depends(get_current_user)):
    """Return distinct users who have uploaded at least one parsed resume."""
    return get_uploaders()


# ─── Autocomplete ──────────────────────────────────────────────────────────────

@app.get("/api/autocomplete/titles")
def ac_titles(q: str = "", limit: int = 8):
    return autocomplete_titles(q.strip(), limit)


@app.get("/api/autocomplete/locations")
def ac_locations(q: str = "", limit: int = 8):
    return autocomplete_locations(q.strip(), limit)


@app.get("/api/autocomplete/skills")
def ac_skills(q: str = "", limit: int = 10):
    return autocomplete_skills(q.strip(), limit)


# ─── Saved Searches ────────────────────────────────────────────────────────────

from pydantic import BaseModel

class SavedSearchIn(BaseModel):
    name:    str
    query:   str  = ""
    filters: dict = {}


@app.get("/api/saved-searches")
def get_saved_searches():
    return list_saved_searches()


@app.post("/api/saved-searches", status_code=201)
def save_search(body: SavedSearchIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return create_saved_search(name, body.query, body.filters)


@app.delete("/api/saved-searches/{search_id}")
def remove_saved_search(search_id: int):
    if not delete_saved_search(search_id):
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"success": True}


# ─── Secure Token Download ─────────────────────────────────────────────────────

@app.get("/api/download/token/{resume_id}")
def get_download_token(resume_id: int):
    """
    Issue a one-time download token (valid 15 min).
    Returns the token and a ready-to-use download URL.
    """
    resume = get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    token = download_tokens.create_token(resume_id)
    return {
        "token":      token,
        "url":        f"/api/download/file/{token}",
        "expires_in": 900,   # seconds
    }


@app.get("/api/download/file/{token}")
def download_by_token(token: str, request: Request):
    """
    Exchange a one-time token for the actual file.
    Token is consumed on first use; subsequent requests with the same token get 404.
    """
    resume_id = download_tokens.redeem_token(token)
    if resume_id is None:
        raise HTTPException(status_code=404, detail="Invalid or expired download token")

    resume = get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    file_path = Path(resume["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    log_download(
        resume_id     = resume_id,
        ip_address    = request.client.host if request.client else "",
        user_agent    = request.headers.get("user-agent", ""),
        download_type = "token",
    )

    return FileResponse(
        path=str(file_path),
        filename=resume["filename"],
        media_type="application/octet-stream",
    )


# ─── Bulk Download (ZIP) ───────────────────────────────────────────────────────

class BulkDownloadIn(BaseModel):
    ids: list[int]


@app.post("/api/download/bulk")
def bulk_download(body: BulkDownloadIn, request: Request):
    """
    Download multiple resumes as a single ZIP archive (max 100 IDs).
    """
    if not body.ids:
        raise HTTPException(status_code=400, detail="ids list is required")
    if len(body.ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot bulk-download more than 100 resumes at once")

    buf   = io.BytesIO()
    added = 0
    ip    = request.client.host if request.client else ""
    ua    = request.headers.get("user-agent", "")

    # Single query for all IDs instead of N individual lookups
    resumes_map = {r["id"]: r for r in get_resumes_by_ids(body.ids)}

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}

        for resume_id in body.ids:
            resume = resumes_map.get(resume_id)
            if not resume:
                continue  # skip missing IDs silently

            file_path = Path(resume["file_path"])
            if not file_path.exists():
                continue

            # Deduplicate filenames inside the ZIP
            base_name = resume["filename"]
            if base_name in seen_names:
                seen_names[base_name] += 1
                stem = Path(base_name).stem
                ext  = Path(base_name).suffix
                arc_name = f"{stem}_{seen_names[base_name]}{ext}"
            else:
                seen_names[base_name] = 0
                arc_name = base_name

            zf.write(file_path, arcname=arc_name)
            log_download(resume_id, ip, ua, download_type="bulk")
            added += 1

    if added == 0:
        raise HTTPException(status_code=404, detail="None of the requested resumes were found")

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=resumes.zip"},
    )


# ─── Download History ──────────────────────────────────────────────────────────

@app.get("/api/download/history")
def download_history(limit: int = 50, offset: int = 0, _: dict = Depends(require_admin)):
    """Return paginated download history log."""
    return get_download_history(limit=limit, offset=offset)


# ─── User Management (Admin) ───────────────────────────────────────────────────

import secrets as _secrets
import hashlib as _hashlib
from datetime import datetime as _dt, timedelta as _td, timezone as _tz


class CreateUserIn(BaseModel):
    full_name: str
    email:     str
    role:      str = "recruiter"

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v):
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email format")
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v):
        if v not in ("admin", "recruiter"):
            raise ValueError("role must be 'admin' or 'recruiter'")
        return v


class UpdateUserIn(BaseModel):
    full_name: str
    email:     str
    role:      str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v):
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email format")
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v):
        if v not in ("admin", "recruiter"):
            raise ValueError("role must be 'admin' or 'recruiter'")
        return v


class SetStatusIn(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        if v not in ("active", "inactive"):
            raise ValueError("status must be 'active' or 'inactive'")
        return v


class ForgotPasswordIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v):
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email format")
        return v.strip().lower()


class ResetPasswordIn(BaseModel):
    token:        str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ── List users (US-007) ───────────────────────────────────────────────────────

@app.get("/api/users")
def api_list_users(
    limit:  int = 50,
    offset: int = 0,
    search: str = "",
    _admin: dict = Depends(require_admin),
):
    return list_users(limit=limit, offset=offset, search=search.strip())


# ── Get single user (US-007) ──────────────────────────────────────────────────

@app.get("/api/users/{user_id}")
def api_get_user(user_id: str, _admin: dict = Depends(require_admin)):
    user = get_user_by_id_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Return safe fields (no password_hash)
    return {k: v for k, v in user.items() if k not in ("password_hash", "reset_token")}


# ── Create user (US-006) ──────────────────────────────────────────────────────

@app.post("/api/users", status_code=201)
def api_create_user(
    body:    CreateUserIn,
    request: Request,
    admin:   dict = Depends(require_admin),
):
    # Uniqueness check
    if get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    temp_password = _secrets.token_urlsafe(9)   # ~12 printable chars, satisfies min-8

    new_user = create_user(
        full_name     = body.full_name,
        email         = body.email,
        password_hash = hash_password(temp_password),
        role          = body.role,
        created_by    = admin["sub"],
    )
    set_must_change_password(new_user["id"], True)

    # Send welcome email (best-effort — non-blocking)
    try:
        send_welcome_email(body.email, body.full_name, temp_password)
    except Exception as exc:
        print(f"⚠️  Welcome email failed: {exc}")

    ip = get_client_ip(request)
    log_audit(
        user_email     = admin["email"],
        action         = "USER_CREATED",
        ip_address     = ip,
        outcome        = "success",
        user_id        = admin["sub"],
        target_user_id = new_user["id"],
        new_value      = f"email={body.email} role={body.role}",
    )

    return {**new_user, "must_change_password": True}


# ── Edit user (US-008) ────────────────────────────────────────────────────────

@app.patch("/api/users/{user_id}")
def api_update_user(
    user_id: str,
    body:    UpdateUserIn,
    request: Request,
    admin:   dict = Depends(require_admin),
):
    existing = get_user_by_id_db(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # Email uniqueness: only block if taken by a *different* user
    conflict = get_user_by_email(body.email)
    if conflict and conflict["id"] != user_id:
        raise HTTPException(status_code=409, detail="Email already in use by another account")

    old_snapshot = f"name={existing['full_name']} email={existing['email']} role={existing['role']}"
    updated = update_user(user_id, body.full_name, body.email, body.role)

    ip = get_client_ip(request)
    log_audit(
        user_email     = admin["email"],
        action         = "USER_UPDATED",
        ip_address     = ip,
        outcome        = "success",
        user_id        = admin["sub"],
        target_user_id = user_id,
        old_value      = old_snapshot,
        new_value      = f"name={body.full_name} email={body.email} role={body.role}",
    )

    return updated


# ── Activate / deactivate user (US-009) ───────────────────────────────────────

@app.patch("/api/users/{user_id}/status")
def api_set_user_status(
    user_id: str,
    body:    SetStatusIn,
    request: Request,
    admin:   dict = Depends(require_admin),
):
    if user_id == admin["sub"]:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    existing = get_user_by_id_db(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    if not set_user_status(user_id, body.status):
        raise HTTPException(status_code=404, detail="User not found")

    ip = get_client_ip(request)
    action = "USER_ACTIVATED" if body.status == "active" else "USER_DEACTIVATED"
    log_audit(
        user_email     = admin["email"],
        action         = action,
        ip_address     = ip,
        outcome        = "success",
        user_id        = admin["sub"],
        target_user_id = user_id,
        old_value      = existing["status"],
        new_value      = body.status,
    )

    return {"success": True, "user_id": user_id, "status": body.status}


# ── Admin password reset (US-010) ─────────────────────────────────────────────

@app.post("/api/users/{user_id}/reset-password")
def api_admin_reset_password(
    user_id: str,
    request: Request,
    admin:   dict = Depends(require_admin),
):
    target = get_user_by_id_db(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    temp_password = _secrets.token_urlsafe(9)
    update_password(user_id, hash_password(temp_password))
    set_must_change_password(user_id, True)

    try:
        send_admin_reset_email(target["email"], target["full_name"], temp_password)
    except Exception as exc:
        print(f"⚠️  Admin reset email failed: {exc}")

    ip = get_client_ip(request)
    log_audit(
        user_email     = admin["email"],
        action         = "PASSWORD_RESET_BY_ADMIN",
        ip_address     = ip,
        outcome        = "success",
        user_id        = admin["sub"],
        target_user_id = user_id,
    )

    return {"success": True, "message": f"Password reset and emailed to {target['email']}"}


# ── Admin set password directly (no email) ────────────────────────────────────

class SetPasswordIn(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@app.post("/api/users/{user_id}/set-password")
def api_admin_set_password(
    user_id: str,
    body:    SetPasswordIn,
    request: Request,
    admin:   dict = Depends(require_admin),
):
    """
    Admin sets a specific password for any user directly — no email sent.
    Marks must_change_password = True so the user is prompted to change it on login.
    """
    if user_id == admin["sub"]:
        raise HTTPException(status_code=400,
                            detail="Use /auth/change-password to change your own password")

    target = get_user_by_id_db(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    update_password(user_id, hash_password(body.new_password))
    set_must_change_password(user_id, True)

    ip = get_client_ip(request)
    log_audit(
        user_email     = admin["email"],
        action         = "PASSWORD_SET_BY_ADMIN",
        ip_address     = ip,
        outcome        = "success",
        user_id        = admin["sub"],
        target_user_id = user_id,
    )

    return {"success": True, "message": f"Password updated for {target['email']}"}


# ─── Forgot / Reset Password (US-004) ─────────────────────────────────────────

@app.post("/api/auth/forgot-password")
@limiter.limit(os.getenv("FORGOT_PW_RATE_LIMIT", "5/minute"))
def forgot_password(body: ForgotPasswordIn, request: Request):
    """
    Always returns 200 regardless of whether the email exists —
    prevents account-enumeration attacks.
    """
    ip   = get_client_ip(request)
    user = get_user_by_email(body.email)

    if user and user["status"] == "active":
        raw_token  = _secrets.token_hex(32)                       # 64 hex chars
        token_hash = _hashlib.sha256(raw_token.encode()).hexdigest()
        expiry     = _dt.now(_tz.utc) + _td(hours=1)

        set_reset_token(user["id"], token_hash, expiry)

        try:
            send_password_reset_email(user["email"], user["full_name"], raw_token)
        except Exception as exc:
            print(f"⚠️  Reset email failed: {exc}")

        log_audit(user["email"], "PASSWORD_RESET_REQUESTED", ip, "success",
                  user_id=user["id"])

    return {"message": "If an account with that email exists, a reset link has been sent."}


@app.post("/api/auth/reset-password")
def reset_password(body: ResetPasswordIn, request: Request):
    """
    US-004 — Exchange a valid (non-expired, single-use) reset token for a new password.
    """
    ip         = get_client_ip(request)
    token_hash = _hashlib.sha256(body.token.encode()).hexdigest()
    user       = get_user_by_reset_token(token_hash)

    if not user:
        raise HTTPException(status_code=400,
                            detail="Invalid or expired reset token")

    update_password(user["id"], hash_password(body.new_password))
    clear_reset_token(user["id"])
    set_must_change_password(user["id"], False)

    log_audit(user["email"], "PASSWORD_RESET_COMPLETED", ip, "success",
              user_id=user["id"])

    return {"message": "Password reset successfully. You can now log in with your new password."}


# ─── Audit Log (US-016) ────────────────────────────────────────────────────────

@app.get("/api/audit-logs")
def api_get_audit_logs(
    limit:      int = 50,
    offset:     int = 0,
    user_email: str = "",
    action:     str = "",
    date_from:  str = None,
    date_to:    str = None,
    _admin:     dict = Depends(require_admin),
):
    return get_audit_logs(
        limit=limit, offset=offset,
        user_email=user_email.strip(),
        action=action.strip(),
        date_from=date_from,
        date_to=date_to,
    )
