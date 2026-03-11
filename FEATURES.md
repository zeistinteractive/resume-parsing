# Resume Engine — Feature Documentation

## Overview

Resume Engine is an AI-powered resume management platform. Recruiters can upload resumes in bulk, let Gemini AI parse them into structured data, then search and filter candidates using rich criteria.

**Tech stack:** FastAPI · PostgreSQL · Celery · Redis · Gemini 2.0 Flash · React · Tailwind CSS · Docker Compose

---

## 1. Resume Upload

### Multi-file Drag-and-Drop
- Upload up to **100 resumes per batch** via drag-and-drop or file picker
- Supported formats: **.pdf, .docx, .doc** (max 5 MB each)
- Files are queued instantly in the UI and uploaded 3 at a time (concurrency limiter)

### Upload Queue UI
Each file in the queue shows a real-time status badge:

| Status | Meaning |
|---|---|
| 🕐 Queued | Waiting for an upload slot |
| ⬆️ Uploading | File is being sent to the server |
| 🤖 Processing | Celery worker is extracting text and running AI parse |
| ✅ Parsed | AI parsing complete; candidate data saved |
| ❌ Failed | Upload or parse error (reason shown inline) |
| 🔁 Duplicate | Byte-identical file already exists (links to original) |

- Overall **progress bar** shows `done / total` with percentage
- **"Clear all"** button appears when every file is finished
- Scrollable queue panel with per-file filename, size, and candidate name (after parse)

### Duplicate Detection (File Hash)
- SHA-256 hash computed at upload time
- If the same file was uploaded before, it is instantly flagged as a duplicate — no redundant parse job is created
- The duplicate badge shows a link to the original resume (e.g. "same file as #42")

### Duplicate Candidate Warning
- After AI parsing, the system checks whether another resume already exists with the **same candidate name + email** combination
- If a match is found, a yellow "⚠️ possible duplicate of #ID" warning appears on that queue item

### Background Parsing Pipeline
- Uploads return immediately (HTTP 200) with a `queued` status
- A **Celery worker** picks up the task asynchronously, runs text extraction and AI parsing, then writes structured data to PostgreSQL
- Parse jobs survive server restarts (persisted in Redis)
- Retries up to 3 times with exponential backoff (30 s → 60 s → 120 s)
- Hard timeout of 3 minutes per job prevents Gemini API hangs

---

## 2. Real-time Status Updates (SSE)

- The browser opens a persistent **Server-Sent Events** connection to `/api/events`
- As Celery workers process resumes, they publish events to a Redis channel (`resume_events`)
- The SSE endpoint relays those events to every connected browser tab in real time
- Heartbeat sent every 15 seconds to keep the connection alive
- Events carry: `resume_id`, `status`, `candidate_name`, `is_duplicate_candidate`, `duplicate_of`, `error`

---

## 3. AI Parsing (Gemini 2.0 Flash)

Each resume is parsed by Gemini and returns structured JSON with the following fields:

| Field | Type | Description |
|---|---|---|
| `name` | string | Candidate's full name |
| `email` | string | Email address |
| `phone` | string | Phone number |
| `summary` | string | Professional summary |
| `current_title` | string | Most recent job title |
| `location` | string | City / country |
| `experience_years` | int | Total years of experience |
| `notice_period` | string | One of: Immediate / 15 days / 30 days / 60 days / 90 days / >90 days / Not mentioned |
| `education_level` | string | One of: High School / Diploma / Bachelor's / Master's / MBA / PhD / Other |
| `skills` | string[] | List of technical and soft skills |
| `experience` | object[] | Work history with company, title, dates |
| `education` | object[] | Education history |

Structured filter columns (`current_title`, `location`, `experience_years`, `notice_period`, `education_level`) are also stored as indexed columns in PostgreSQL for fast filtering without JSONB scans.

---

## 4. Candidate Search

### Keyword Search
- Full-text search across raw resume text using PostgreSQL `tsvector` / `websearch_to_tsquery`
- **AND mode** — all keywords must appear
- **OR mode** — any keyword matches (default)
- **Synonym expansion** — e.g. searching "JS" also matches "JavaScript"
- Matching keywords are **highlighted** in the snippet shown on each result card

### Structured Filters
All filters can be combined with the keyword search:

| Filter | Behavior |
|---|---|
| Job Title | Case-insensitive substring match on `current_title` |
| Skills | One or more skills (JSONB `@>` containment with synonym expansion) |
| Experience (min/max) | Range filter on `experience_years` |
| Location | Case-insensitive substring match |
| Education Level | Exact match (Bachelor's, Master's, MBA, PhD, etc.) |
| Notice Period | Exact match (Immediate, 15 days, 30 days, etc.) |
| Upload Date range | `date_from` / `date_to` |

### Sort Options
- **Relevance** — FTS score descending (default when a keyword query is present)
- **Experience ↓ / ↑** — most/least experienced first
- **Date Added ↓** — most recently uploaded first

### Autocomplete
Type-ahead suggestions for:
- **Job titles** — prefix match from parsed resumes
- **Locations** — substring match from parsed resumes
- **Skills** — prefix match across all skills in the JSONB array

### Pagination
- Results per page: 25 / 50 / 100 (selectable)
- Previous / Next navigation with "showing X–Y of Z" count

### Saved Searches
- Save any combination of keyword + filters as a named search
- Saved searches appear as clickable chips — one click restores the full search state
- Delete saved searches individually

### Search State Persistence
- The current keyword, filters, sort order, page, and results-per-page are saved to `sessionStorage`
- Navigating to a candidate detail page and pressing "← Back to results" restores the exact search state

---

## 5. Candidate Detail View

Clicking a search result or a resume in the upload list opens the full detail page:

- Candidate name, email, phone, location
- Current title, experience years, education level, notice period
- Professional summary
- Skills list (badge pills)
- Full work experience timeline
- Education history
- **Download** button (original file)
- **← Back to results** button (restores search state)

---

## 6. Resume Download

### Single Download
- Download the original PDF/DOCX file directly from the candidate detail page or search results
- Every download is logged to `download_history`

### Secure Token Download
- Generate a **one-time token** valid for 15 minutes (`GET /api/download/token/{id}`)
- Token is consumed on first use — a second request with the same token returns 404
- Tokens stored in Redis with TTL; atomic GET+DELETE prevents double-redemption

### Bulk Download (ZIP)
- Select up to **100 resumes** using checkboxes in search results
- Download all selected files as a single **ZIP archive**
- Duplicate filenames inside the ZIP are automatically renamed (e.g. `john_cv_2.pdf`)
- A **sticky bottom bar** (BulkBar) shows selection count, "Select all on page", "Clear", and "Download ZIP" buttons

### Download History
- Every file served (single, token, or bulk) is recorded in `download_history`
- Stores: resume ID, IP address, user agent, download type, timestamp
- Accessible via `GET /api/download/history`

---

## 7. Resume Management

- **List view** on the Upload page shows all resumes with parse status, candidate name, and top skills
- **Delete** any resume (removes DB record + file from disk)
- **Pagination** on the resume list (20 per page)

---

## 8. API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/events` | SSE stream (real-time parse events) |
| POST | `/api/upload` | Upload a resume file |
| GET | `/api/resumes` | List all resumes (paginated) |
| GET | `/api/resumes/{id}` | Get a single resume |
| DELETE | `/api/resumes/{id}` | Delete a resume |
| GET | `/api/resumes/{id}/download` | Download the original file |
| GET | `/api/search` | Search resumes with filters |
| GET | `/api/autocomplete/titles` | Job title suggestions |
| GET | `/api/autocomplete/locations` | Location suggestions |
| GET | `/api/autocomplete/skills` | Skill suggestions |
| GET | `/api/saved-searches` | List saved searches |
| POST | `/api/saved-searches` | Create a saved search |
| DELETE | `/api/saved-searches/{id}` | Delete a saved search |
| GET | `/api/download/token/{id}` | Issue a one-time download token |
| GET | `/api/download/file/{token}` | Redeem a token for a file |
| POST | `/api/download/bulk` | Download multiple resumes as ZIP |
| GET | `/api/download/history` | Paginated download history |

---

## 9. Infrastructure

| Service | Container | Role |
|---|---|---|
| PostgreSQL | `resume-engine-postgres` | Primary database |
| Redis | `resume-engine-redis` | Celery broker + SSE pub/sub + download tokens |
| FastAPI | `resume-engine-backend` | REST API server |
| Celery worker | `resume-engine-celery` | Background parse jobs |
| nginx + React | `resume-engine-frontend` | Static frontend serving |
