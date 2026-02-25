import json
import os
import shlex
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://resume_user:resume_pass@localhost:5432/resume_engine",
)

_pool: Optional[ThreadedConnectionPool] = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn=2, maxconn=10, dsn=DATABASE_URL)
    return _pool


@contextmanager
def _get_conn():
    """Yield a pooled connection; commit on success, rollback on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    with _get_conn() as conn:
        with conn.cursor() as c:
            # Main resumes table — parsed_data stored as native JSONB
            c.execute("""
                CREATE TABLE IF NOT EXISTS resumes (
                    id           SERIAL PRIMARY KEY,
                    filename     TEXT NOT NULL,
                    file_path    TEXT NOT NULL,
                    raw_text     TEXT,
                    parsed_data  JSONB,
                    parse_status TEXT NOT NULL DEFAULT 'pending',
                    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # GIN index for full-text search on raw_text
            c.execute("""
                CREATE INDEX IF NOT EXISTS resumes_fts_idx
                ON resumes USING GIN (
                    to_tsvector('english', COALESCE(raw_text, ''))
                )
            """)

            # B-tree index for fast listing ordered by upload date
            c.execute("""
                CREATE INDEX IF NOT EXISTS resumes_uploaded_at_idx
                ON resumes (uploaded_at DESC)
            """)

    print("✅ Database initialized")


# ── Write operations ──────────────────────────────────────────────────────────

def insert_resume(filename: str, file_path: str) -> int:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO resumes (filename, file_path, parse_status)
                VALUES (%s, %s, 'pending') RETURNING id
                """,
                (filename, file_path),
            )
            return c.fetchone()[0]


def update_resume_parsed(resume_id: int, raw_text: str, parsed_data: dict):
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                UPDATE resumes
                SET raw_text     = %s,
                    parsed_data  = %s,
                    parse_status = 'success'
                WHERE id = %s
                """,
                (raw_text, psycopg2.extras.Json(parsed_data), resume_id),
            )


def update_resume_failed(resume_id: int):
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE resumes SET parse_status = 'failed' WHERE id = %s",
                (resume_id,),
            )


def delete_resume(resume_id: int) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM resumes WHERE id = %s", (resume_id,))
            if not c.fetchone():
                return False
            c.execute("DELETE FROM resumes WHERE id = %s", (resume_id,))
    return True


# ── Read operations ───────────────────────────────────────────────────────────

def count_resumes() -> int:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM resumes")
            return c.fetchone()[0]


def get_all_resumes(limit: int = 20, offset: int = 0) -> list:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                SELECT
                    id, filename, parse_status,
                    uploaded_at,
                    parsed_data->>'name'  AS candidate_name,
                    parsed_data->>'email' AS email,
                    parsed_data->'skills' AS skills_json
                FROM resumes
                ORDER BY uploaded_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = c.fetchall()

    results = []
    for row in rows:
        results.append({
            "id":             row["id"],
            "filename":       row["filename"],
            "parse_status":   row["parse_status"],
            "uploaded_at":    row["uploaded_at"].isoformat() if row["uploaded_at"] else None,
            "candidate_name": row["candidate_name"],
            "email":          row["email"],
            "skills":         _extract_skills(row["skills_json"], limit=6),
        })
    return results


def get_resume_by_id(resume_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("SELECT * FROM resumes WHERE id = %s", (resume_id,))
            row = c.fetchone()

    if not row:
        return None

    # psycopg2 auto-deserialises JSONB → Python dict; handle edge cases
    parsed = row["parsed_data"] or {}
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except Exception:
            parsed = {}

    return {
        "id":           row["id"],
        "filename":     row["filename"],
        "file_path":    row["file_path"],
        "raw_text":     row["raw_text"],
        "parsed_data":  parsed,
        "parse_status": row["parse_status"],
        "uploaded_at":  row["uploaded_at"].isoformat() if row["uploaded_at"] else None,
    }


# ── Search ────────────────────────────────────────────────────────────────────

def _build_websearch_query(raw: str, mode: str = "or") -> str:
    """
    Format a user query for websearch_to_tsquery.

    mode='or'  → tokens joined with OR  ("python react" → "python OR react")
    mode='and' → tokens joined by space  ("python react" → "python react")

    Quoted phrases are preserved: '"senior engineer"' stays as a phrase.
    """
    raw = raw.strip()
    if not raw:
        return raw

    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()

    tokens = [t.strip() for t in tokens if t.strip()]
    if not tokens:
        return raw

    if mode.lower() == "or":
        return " OR ".join(tokens)
    return " ".join(tokens)  # websearch_to_tsquery default is AND


def search_resumes(query: str, limit: int = 20, mode: str = "or") -> list:
    search_str = _build_websearch_query(query, mode)

    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT
                        id, filename, parse_status,
                        uploaded_at,
                        parsed_data->>'name'  AS candidate_name,
                        parsed_data->>'email' AS email,
                        parsed_data->'skills' AS skills_json,
                        ts_headline(
                            'english', raw_text,
                            websearch_to_tsquery('english', %s),
                            'StartSel=<mark>, StopSel=</mark>, MaxWords=30, MinWords=10'
                        ) AS snippet,
                        ts_rank(
                            to_tsvector('english', COALESCE(raw_text, '')),
                            websearch_to_tsquery('english', %s)
                        ) AS score
                    FROM resumes
                    WHERE parse_status = 'success'
                      AND to_tsvector('english', COALESCE(raw_text, ''))
                          @@ websearch_to_tsquery('english', %s)
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (search_str, search_str, search_str, limit),
                )
                rows = c.fetchall()
    except Exception as e:
        print(f"Search error: {e}")
        return []

    results = []
    for row in rows:
        results.append({
            "id":             row["id"],
            "filename":       row["filename"],
            "parse_status":   row["parse_status"],
            "uploaded_at":    row["uploaded_at"].isoformat() if row["uploaded_at"] else None,
            "candidate_name": row["candidate_name"],
            "email":          row["email"],
            "skills":         _extract_skills(row["skills_json"], limit=8),
            "snippet":        row["snippet"] or "",
        })
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_skills(skills_json, limit: int = 6) -> list:
    """Safely extract skills from a JSONB value (psycopg2 returns it as a Python list)."""
    if not skills_json:
        return []
    try:
        if isinstance(skills_json, list):
            return skills_json[:limit]
        return json.loads(skills_json)[:limit]
    except Exception:
        return []
