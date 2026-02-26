"""
Resume Engine MVP - FastAPI Backend
Handles upload, parsing, search of resumes.
"""
import io
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db, insert_resume,
    get_all_resumes, get_resume_by_id, delete_resume,
    count_resumes, search_resumes,
    autocomplete_titles, autocomplete_locations, autocomplete_skills,
    list_saved_searches, create_saved_search, delete_saved_search,
    log_download, get_download_history,
)
from tasks import parse_resume_task
from events import sse_endpoint
import download_tokens

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Resume Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Will restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE_MB = 5
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


@app.on_event("startup")
async def startup():
    init_db()
    print("✅ Resume Engine API started")


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Resume Engine API"}


# ─── SSE Event Stream ──────────────────────────────────────────────────────────

@app.get("/api/events")
async def events(request: Request):
    return await sse_endpoint(request)


# ─── Upload Resume ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_resume(file: UploadFile = File(...)):
    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{suffix}'. Allowed: PDF, DOCX"
        )

    # Read file content and check size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f}MB). Maximum size is {MAX_FILE_SIZE_MB}MB."
        )

    # Save file to uploads directory
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(contents)

    # Insert DB record
    resume_id = insert_resume(file.filename, str(file_path))

    # Enqueue parse job — persisted in Redis, survives server restarts
    parse_resume_task.delay(resume_id, str(file_path))

    return {
        "id": resume_id,
        "filename": file.filename,
        "status": "pending",
        "message": "Resume uploaded. Parsing in progress..."
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
def remove_resume(resume_id: int):
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
        sort          = sort,
        limit         = limit,
        offset        = offset,
    )


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

    buf = io.BytesIO()
    added = 0
    ip        = request.client.host if request.client else ""
    ua        = request.headers.get("user-agent", "")

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}

        for resume_id in body.ids:
            resume = get_resume_by_id(resume_id)
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
def download_history(limit: int = 50, offset: int = 0):
    """Return paginated download history log."""
    return get_download_history(limit=limit, offset=offset)
