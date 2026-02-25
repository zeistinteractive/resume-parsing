"""
Resume Engine MVP - FastAPI Backend
Handles upload, parsing, search of resumes.
"""
import os
import uuid
import asyncio
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db, insert_resume, update_resume_parsed, update_resume_failed,
    get_all_resumes, get_resume_by_id, delete_resume,
    count_resumes, search_resumes
)
from parser import extract_text
from ai_parser import parse_resume

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

MAX_RESUMES = 50
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


# ─── Upload Resume ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{suffix}'. Allowed: PDF, DOCX"
        )

    # Check resume count limit
    if count_resumes() >= MAX_RESUMES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_RESUMES} resumes reached. Delete some to upload more."
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

    # Kick off background parsing
    background_tasks.add_task(run_parsing, resume_id, str(file_path))

    return {
        "id": resume_id,
        "filename": file.filename,
        "status": "pending",
        "message": "Resume uploaded. Parsing in progress..."
    }


async def run_parsing(resume_id: int, file_path: str):
    """Background task: extract text then AI-parse the resume."""
    try:
        print(f"📄 Extracting text for resume {resume_id}...")
        raw_text = extract_text(file_path)

        if not raw_text:
            print(f"⚠️  No text extracted for resume {resume_id}")
            update_resume_failed(resume_id)
            return

        print(f"🤖 AI parsing resume {resume_id} ({len(raw_text)} chars)...")
        parsed_data = parse_resume(raw_text)

        update_resume_parsed(resume_id, raw_text, parsed_data)
        print(f"✅ Resume {resume_id} parsed successfully: {parsed_data.get('name', 'Unknown')}")

    except Exception as e:
        print(f"❌ Parsing failed for resume {resume_id}: {e}")
        update_resume_failed(resume_id)


# ─── List Resumes ──────────────────────────────────────────────────────────────

@app.get("/api/resumes")
def list_resumes():
    return get_all_resumes()


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

    # Delete the file
    file_path = Path(resume["file_path"])
    if file_path.exists():
        file_path.unlink()

    success = delete_resume(resume_id)
    return {"success": success, "message": f"Resume {resume_id} deleted"}


# ─── Download Original File ────────────────────────────────────────────────────

@app.get("/api/resumes/{resume_id}/download")
def download_resume(resume_id: int):
    resume = get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    file_path = Path(resume["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=resume["filename"],
        media_type="application/octet-stream"
    )


# ─── Search Resumes ────────────────────────────────────────────────────────────

@app.get("/api/search")
def search(q: str = "", limit: int = 20, mode: str = "or"):
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    if mode not in ("and", "or"):
        raise HTTPException(status_code=400, detail="mode must be 'and' or 'or'")

    results = search_resumes(q.strip(), limit, mode)
    return {
        "query": q,
        "mode": mode,
        "count": len(results),
        "results": results
    }
