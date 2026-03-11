import json
import os
import shlex
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from synonyms import build_fts_conditions, expand_skills, get_skill_synonyms

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://resume_user:resume_pass@postgres:5432/resume_engine",
)

# Pool size configurable via env — default 2/20 for production workloads
_DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
_DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))

# Long-running query guard — kills queries that take more than this many ms
_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000"))

_pool: Optional[ThreadedConnectionPool] = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=_DB_POOL_MIN, maxconn=_DB_POOL_MAX, dsn=DATABASE_URL
        )
    return _pool


@contextmanager
def _get_conn():
    """Yield a pooled connection; commit on success, rollback on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        # Prevent runaway queries from holding connections
        with conn.cursor() as c:
            c.execute(f"SET statement_timeout = {_STATEMENT_TIMEOUT_MS}")
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
            # Main resumes table — parsed_data stored as native JSONB.
            # Structured filter columns are populated at parse time so filters
            # can hit B-tree / GIN indexes instead of scanning JSONB at query time.
            c.execute("""
                CREATE TABLE IF NOT EXISTS resumes (
                    id               SERIAL PRIMARY KEY,
                    filename         TEXT NOT NULL,
                    file_path        TEXT NOT NULL,
                    raw_text         TEXT,
                    parsed_data      JSONB,
                    parse_status     TEXT NOT NULL DEFAULT 'pending',
                    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    experience_years SMALLINT,
                    current_title    TEXT,
                    location         TEXT,
                    notice_period    TEXT,
                    education_level  TEXT
                )
            """)

            # Add filter columns when upgrading from an older schema
            # ADD COLUMN IF NOT EXISTS is safe to run repeatedly.
            for col, col_type in [
                ("experience_years",  "SMALLINT"),
                ("current_title",     "TEXT"),
                ("location",          "TEXT"),
                ("notice_period",     "TEXT"),
                ("education_level",   "TEXT"),
                ("file_hash",         "TEXT"),   # SHA-256 hex of the uploaded file
                ("uploaded_by_id",    "TEXT"),   # UUID of the user who uploaded
                ("uploaded_by_name",  "TEXT"),   # Full name snapshot at upload time
            ]:
                c.execute(
                    f"ALTER TABLE resumes ADD COLUMN IF NOT EXISTS {col} {col_type}"
                )

            # Saved searches — stores a name + the full filter state as JSONB.
            c.execute("""
                CREATE TABLE IF NOT EXISTS saved_searches (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT NOT NULL,
                    query      TEXT,
                    filters    JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # ── Indexes ───────────────────────────────────────────────────────

            # GIN index for full-text search on raw resume text
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

            # B-tree indexes for structured filter columns
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_exp_years_idx "
                "ON resumes (experience_years)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_notice_idx "
                "ON resumes (notice_period) WHERE notice_period IS NOT NULL"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_education_idx "
                "ON resumes (education_level) WHERE education_level IS NOT NULL"
            )

            # text_pattern_ops indexes allow ILIKE prefix scans on lowercase values.
            # Used by autocomplete queries for titles and locations.
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_title_tpo_idx "
                "ON resumes (lower(current_title) text_pattern_ops) "
                "WHERE current_title IS NOT NULL"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_location_tpo_idx "
                "ON resumes (lower(location) text_pattern_ops) "
                "WHERE location IS NOT NULL"
            )

            # GIN index on the skills JSONB array — enables fast @> containment checks
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_skills_idx "
                "ON resumes USING GIN ((parsed_data->'skills'))"
            )

            # Unique partial index on file_hash — NULL rows excluded so old
            # records without a hash don't conflict with each other.
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS resumes_file_hash_idx "
                "ON resumes (file_hash) WHERE file_hash IS NOT NULL"
            )

            # Partial index on parse_status — almost every query filters by this.
            # Only indexes 'success' rows since those are queried exclusively.
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_parse_status_idx "
                "ON resumes (parse_status) WHERE parse_status = 'success'"
            )

            # pg_trgm for substring ILIKE on location (autocomplete uses %q%)
            c.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            c.execute(
                "CREATE INDEX IF NOT EXISTS resumes_location_trgm_idx "
                "ON resumes USING GIN (lower(location) gin_trgm_ops) "
                "WHERE location IS NOT NULL"
            )

            # Download history — one row per file served (single or bulk).
            # resume_id is nullable so rows survive resume deletion.
            c.execute("""
                CREATE TABLE IF NOT EXISTS download_history (
                    id            SERIAL PRIMARY KEY,
                    resume_id     INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
                    ip_address    TEXT,
                    user_agent    TEXT,
                    download_type TEXT NOT NULL DEFAULT 'single',
                    downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            c.execute(
                "CREATE INDEX IF NOT EXISTS dl_history_resume_idx "
                "ON download_history (resume_id)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS dl_history_at_idx "
                "ON download_history (downloaded_at DESC)"
            )

            # skills_vocabulary — pre-computed distinct skill list for fast autocomplete.
            # Avoids full jsonb_array_elements_text scan on 50k+ resumes.
            c.execute("""
                CREATE TABLE IF NOT EXISTS skills_vocabulary (
                    skill      TEXT PRIMARY KEY,
                    frequency  INTEGER NOT NULL DEFAULT 1,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            c.execute(
                "CREATE INDEX IF NOT EXISTS skills_vocab_skill_idx "
                "ON skills_vocabulary (lower(skill) text_pattern_ops)"
            )

    print("✅ Database initialized")


# ── Write operations ──────────────────────────────────────────────────────────

def insert_resume(
    filename: str,
    file_path: str,
    file_hash: str = None,
    uploaded_by_id: str = None,
    uploaded_by_name: str = None,
) -> int:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO resumes
                    (filename, file_path, file_hash, parse_status,
                     uploaded_by_id, uploaded_by_name)
                VALUES (%s, %s, %s, 'pending', %s, %s)
                RETURNING id
                """,
                (filename, file_path, file_hash, uploaded_by_id, uploaded_by_name),
            )
            return c.fetchone()[0]


def get_resume_by_hash(file_hash: str):
    """
    Return the existing resume row whose file_hash matches, or None.
    Used at upload time to instantly detect byte-identical duplicates.
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                "SELECT id, filename, parse_status, uploaded_at "
                "FROM resumes WHERE file_hash = %s LIMIT 1",
                (file_hash,),
            )
            row = c.fetchone()
            return dict(row) if row else None


def find_duplicate_candidate(name: str, email: str, exclude_id: int):
    """
    After parsing, check whether another successfully-parsed resume already
    has the same candidate name + email.  Returns that resume's id, or None.
    Only meaningful when both name and email are non-empty strings.
    """
    if not name or not email:
        return None
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                SELECT id FROM resumes
                WHERE parse_status = 'success'
                  AND id            != %s
                  AND lower(parsed_data->>'name')  = lower(%s)
                  AND lower(parsed_data->>'email') = lower(%s)
                LIMIT 1
                """,
                (exclude_id, name.strip(), email.strip()),
            )
            row = c.fetchone()
            return row[0] if row else None


def update_resume_parsed(resume_id: int, raw_text: str, parsed_data: dict):
    """
    Persist parsed resume data. The five structured filter columns are written
    alongside JSONB so they can be indexed and queried efficiently.
    """
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                UPDATE resumes
                SET raw_text         = %s,
                    parsed_data      = %s,
                    parse_status     = 'success',
                    experience_years = %s,
                    current_title    = %s,
                    location         = %s,
                    notice_period    = %s,
                    education_level  = %s
                WHERE id = %s
                """,
                (
                    raw_text,
                    psycopg2.extras.Json(parsed_data),
                    parsed_data.get("experience_years") or None,
                    parsed_data.get("current_title") or None,
                    parsed_data.get("location") or None,
                    parsed_data.get("notice_period") or None,
                    parsed_data.get("education_level") or None,
                    resume_id,
                ),
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


# ── Download history ──────────────────────────────────────────────────────────

def log_download(
    resume_id:     int,
    ip_address:    str  = "",
    user_agent:    str  = "",
    download_type: str  = "single",   # 'single' | 'bulk'
) -> None:
    """
    Insert one row into download_history. Non-fatal — a logging failure
    must never block the actual file download.
    """
    try:
        with _get_conn() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO download_history
                        (resume_id, ip_address, user_agent, download_type)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (resume_id, ip_address or "", user_agent or "", download_type),
                )
    except Exception as e:
        print(f"⚠️  Download history log failed for resume {resume_id}: {e}")


def get_download_history(limit: int = 50, offset: int = 0) -> dict:
    """Return paginated download history, most recent first."""
    with _get_conn() as conn:
        with conn.cursor() as cnt:
            cnt.execute("SELECT COUNT(*) FROM download_history")
            total = cnt.fetchone()[0]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                SELECT
                    dh.id,
                    dh.resume_id,
                    r.filename,
                    r.parsed_data->>'name' AS candidate_name,
                    dh.ip_address,
                    dh.download_type,
                    dh.downloaded_at
                FROM download_history dh
                LEFT JOIN resumes r ON r.id = dh.resume_id
                ORDER BY dh.downloaded_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = c.fetchall()

    return {
        "total": total,
        "items": [
            {
                "id":             row["id"],
                "resume_id":      row["resume_id"],
                "filename":       row["filename"],
                "candidate_name": row["candidate_name"],
                "ip_address":     row["ip_address"],
                "download_type":  row["download_type"],
                "downloaded_at":  row["downloaded_at"].isoformat() if row["downloaded_at"] else None,
            }
            for row in rows
        ],
        "limit":  limit,
        "offset": offset,
    }


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


def get_resumes_by_ids(ids: list) -> list:
    """
    Fetch multiple resumes in a single query (used by bulk download).
    Returns only the fields needed for download — avoids N individual lookups.
    """
    if not ids:
        return []
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                "SELECT id, filename, file_path FROM resumes WHERE id = ANY(%s)",
                (list(ids),),
            )
            return [dict(r) for r in c.fetchall()]


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

# Whitelisted ORDER BY clauses — prevents SQL injection from the sort param.
_ORDER_BY = {
    "relevance": "score DESC NULLS LAST, uploaded_at DESC",
    "exp_desc":  "experience_years DESC NULLS LAST, uploaded_at DESC",
    "exp_asc":   "experience_years ASC NULLS LAST, uploaded_at DESC",
    "date_desc": "uploaded_at DESC",
}


def search_resumes(
    query: str = "",
    mode: str = "or",
    title: str = "",
    skills: list = None,
    exp_min: int = None,
    exp_max: int = None,
    location: str = "",
    education: str = "",
    notice_period: str = "",
    date_from: str = None,
    date_to: str = None,
    uploaded_by: str = None,
    sort: str = "relevance",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """
    Flexible search across resumes with optional structured filters.

    Returns { total, results, limit, offset, query } where total is the
    count of all matching rows (ignoring pagination) so the frontend can
    render a pagination bar.
    """
    skills = skills or []
    limit  = min(max(limit, 1), 100)   # clamp: 1–100

    # ── Build WHERE clause dynamically ────────────────────────────────────────
    conditions: list[str] = ["parse_status = 'success'"]
    params:     list      = []

    has_query = bool(query and query.strip())
    search_str = ""

    if has_query:
        # Try synonym-expanded FTS first; fall back to plain websearch_to_tsquery.
        try:
            raw_tokens = shlex.split(query.strip())
        except ValueError:
            raw_tokens = query.strip().split()

        syn_conditions, syn_params = build_fts_conditions(raw_tokens, mode)

        if syn_conditions:
            # Synonym expansion found — use expanded conditions.
            # Build a flat OR string of all synonyms for use in ts_rank / ts_headline.
            all_terms: list[str] = []
            for tok in raw_tokens:
                all_terms.extend(get_skill_synonyms(tok))
            search_str = " OR ".join(all_terms)
            conditions.extend(syn_conditions)
            params.extend(syn_params)
        else:
            # No synonyms — standard path
            search_str = _build_websearch_query(query.strip(), mode)
            conditions.append(
                "to_tsvector('english', COALESCE(raw_text, '')) "
                "@@ websearch_to_tsquery('english', %s)"
            )
            params.append(search_str)

    if title:
        conditions.append("lower(current_title) LIKE lower(%s)")
        params.append(f"%{title}%")

    if skills:
        # Each requested skill expands to its synonyms (OR within group).
        # Groups are ANDed together so multi-skill filters still narrow results.
        for synonym_group in expand_skills(skills):
            group_conditions = [
                "parsed_data->'skills' @> %s::jsonb" for _ in synonym_group
            ]
            conditions.append("(" + " OR ".join(group_conditions) + ")")
            params.extend(json.dumps([s]) for s in synonym_group)

    if exp_min is not None:
        conditions.append("experience_years >= %s")
        params.append(exp_min)

    if exp_max is not None:
        conditions.append("experience_years <= %s")
        params.append(exp_max)

    if location:
        conditions.append("lower(location) LIKE lower(%s)")
        params.append(f"%{location}%")

    if education:
        conditions.append("education_level = %s")
        params.append(education)

    if notice_period:
        conditions.append("notice_period = %s")
        params.append(notice_period)

    if date_from:
        conditions.append("uploaded_at >= %s::date")
        params.append(date_from)

    if date_to:
        conditions.append("uploaded_at < (%s::date + interval '1 day')")
        params.append(date_to)

    if uploaded_by:
        conditions.append("uploaded_by_id = %s")
        params.append(uploaded_by)

    where_sql = " AND ".join(conditions)

    # ── ORDER BY ──────────────────────────────────────────────────────────────
    # When there is no keyword query, "relevance" has no meaning — fall back to date.
    effective_sort  = sort if (has_query or sort != "relevance") else "date_desc"
    order_clause    = _ORDER_BY.get(effective_sort, _ORDER_BY["date_desc"])

    # ── SELECT expressions that depend on whether a keyword query exists ──────
    if has_query:
        score_expr   = (
            "ts_rank(to_tsvector('english', COALESCE(raw_text, '')), "
            "websearch_to_tsquery('english', %s)) AS score"
        )
        snippet_expr = (
            "ts_headline('english', COALESCE(raw_text, ''), "
            "websearch_to_tsquery('english', %s), "
            "'StartSel=<mark>, StopSel=</mark>, MaxWords=30, MinWords=10') AS snippet"
        )
        extra_select_params = [search_str, search_str]
    else:
        score_expr          = "0.0::float AS score"
        snippet_expr        = "NULL::text AS snippet"
        extra_select_params = []

    # ── Count query (same WHERE, no pagination) ───────────────────────────────
    count_sql = f"SELECT COUNT(*) FROM resumes WHERE {where_sql}"

    # ── Main query ────────────────────────────────────────────────────────────
    select_sql = f"""
        SELECT
            id, filename, parse_status, uploaded_at,
            parsed_data->>'name'  AS candidate_name,
            parsed_data->>'email' AS email,
            parsed_data->'skills' AS skills_json,
            current_title, experience_years, location,
            uploaded_by_id, uploaded_by_name,
            {score_expr},
            {snippet_expr}
        FROM resumes
        WHERE {where_sql}
        ORDER BY {order_clause}
        LIMIT %s OFFSET %s
    """

    try:
        with _get_conn() as conn:
            # Count uses a plain cursor — RealDictCursor can't be indexed by [0]
            with conn.cursor() as cnt:
                cnt.execute(count_sql, params)
                total = cnt.fetchone()[0]

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                # SELECT params: extra_select_params (score/snippet) + WHERE params + pagination
                c.execute(select_sql, extra_select_params + params + [limit, offset])
                rows = c.fetchall()

    except Exception as e:
        print(f"Search error: {e}")
        return {"total": 0, "results": [], "limit": limit, "offset": offset, "query": query}

    results = []
    for row in rows:
        results.append({
            "id":              row["id"],
            "filename":        row["filename"],
            "parse_status":    row["parse_status"],
            "uploaded_at":     row["uploaded_at"].isoformat() if row["uploaded_at"] else None,
            "candidate_name":  row["candidate_name"],
            "email":           row["email"],
            "skills":          _extract_skills(row["skills_json"], limit=8),
            "current_title":   row["current_title"],
            "experience_years": row["experience_years"],
            "location":          row["location"],
            "uploaded_by_id":    row["uploaded_by_id"],
            "uploaded_by_name":  row["uploaded_by_name"],
            "snippet":           row["snippet"] or "",
        })

    return {
        "total":   total,
        "results": results,
        "limit":   limit,
        "offset":  offset,
        "query":   query,
    }


# ── Uploaders ─────────────────────────────────────────────────────────────────

def get_uploaders() -> list:
    """
    Return distinct uploaders who have at least one successfully parsed resume.
    Used to populate the "Uploaded by" dropdown on the search page.
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT DISTINCT uploaded_by_id   AS id,
                                uploaded_by_name AS full_name
                FROM   resumes
                WHERE  parse_status    = 'success'
                  AND  uploaded_by_id  IS NOT NULL
                ORDER  BY uploaded_by_name
            """)
            return [dict(r) for r in c.fetchall()]


# ── Autocomplete ──────────────────────────────────────────────────────────────

def autocomplete_titles(q: str, limit: int = 8) -> list:
    """Return distinct current_title values that start with q (prefix match)."""
    if not q:
        return []
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                SELECT DISTINCT current_title
                FROM resumes
                WHERE parse_status = 'success'
                  AND current_title ILIKE %s
                ORDER BY current_title
                LIMIT %s
                """,
                (f"{q}%", limit),
            )
            return [row[0] for row in c.fetchall() if row[0]]


def autocomplete_locations(q: str, limit: int = 8) -> list:
    """Return distinct location values that contain q (substring match)."""
    if not q:
        return []
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                SELECT DISTINCT location
                FROM resumes
                WHERE parse_status = 'success'
                  AND location ILIKE %s
                ORDER BY location
                LIMIT %s
                """,
                (f"%{q}%", limit),
            )
            return [row[0] for row in c.fetchall() if row[0]]


def autocomplete_skills(q: str, limit: int = 10) -> list:
    """
    Return skill suggestions from the pre-computed skills_vocabulary table.
    Falls back to a capped direct scan if the vocabulary is empty.
    """
    if not q:
        return []
    with _get_conn() as conn:
        with conn.cursor() as c:
            # Fast path — vocabulary table (O(log n) prefix scan)
            c.execute(
                """
                SELECT skill FROM skills_vocabulary
                WHERE lower(skill) LIKE lower(%s)
                ORDER BY frequency DESC, skill
                LIMIT %s
                """,
                (f"{q}%", limit),
            )
            rows = c.fetchall()
            if rows:
                return [row[0] for row in rows if row[0]]

            # Fallback — direct scan capped at 5000 most recent resumes
            c.execute(
                """
                SELECT DISTINCT skill
                FROM (
                    SELECT jsonb_array_elements_text(parsed_data->'skills') AS skill
                    FROM resumes
                    WHERE parse_status = 'success'
                    ORDER BY uploaded_at DESC
                    LIMIT 5000
                ) sub
                WHERE skill ILIKE %s
                ORDER BY skill
                LIMIT %s
                """,
                (f"{q}%", limit),
            )
            return [row[0] for row in c.fetchall() if row[0]]


# ── Saved searches ────────────────────────────────────────────────────────────

def list_saved_searches() -> list:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                "SELECT id, name, query, filters, created_at "
                "FROM saved_searches ORDER BY created_at DESC"
            )
            rows = c.fetchall()
    return [
        {
            "id":         row["id"],
            "name":       row["name"],
            "query":      row["query"],
            "filters":    row["filters"] or {},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]


def create_saved_search(name: str, query: str, filters: dict) -> dict:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO saved_searches (name, query, filters)
                VALUES (%s, %s, %s) RETURNING id, created_at
                """,
                (name, query or "", psycopg2.extras.Json(filters or {})),
            )
            row = c.fetchone()
    return {
        "id":         row[0],
        "name":       name,
        "query":      query,
        "filters":    filters or {},
        "created_at": row[1].isoformat(),
    }


def delete_saved_search(search_id: int) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "DELETE FROM saved_searches WHERE id = %s RETURNING id",
                (search_id,),
            )
            return c.fetchone() is not None


# ── Helpers ───────────────────────────────────────────────────────────────────

def upsert_skills(skills: list) -> None:
    """
    Add/increment skills in the vocabulary table after a resume is parsed.
    Called by the Celery parse task — keeps autocomplete fast at scale.
    """
    if not skills:
        return
    # Deduplicate and normalise
    unique = list({s.strip() for s in skills if s and s.strip()})
    if not unique:
        return
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.executemany(
                """
                INSERT INTO skills_vocabulary (skill, frequency)
                VALUES (%s, 1)
                ON CONFLICT (skill) DO UPDATE
                    SET frequency  = skills_vocabulary.frequency + 1,
                        updated_at = NOW()
                """,
                [(s,) for s in unique],
            )


def purge_old_records(
    download_history_days: int = 90,
    audit_log_days: int = 365,
) -> dict:
    """
    Delete old rows from download_history and audit_logs to prevent unbounded growth.
    Safe to run as a scheduled Celery beat task.
    Returns counts of deleted rows.
    """
    deleted = {}
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "DELETE FROM download_history "
                "WHERE downloaded_at < NOW() - INTERVAL '%s days'",
                (download_history_days,),
            )
            deleted["download_history"] = c.rowcount

    # Import here to avoid circular import (users_db uses database pool)
    try:
        from users_db import purge_old_audit_logs
        deleted["audit_logs"] = purge_old_audit_logs(audit_log_days)
    except Exception as e:
        print(f"⚠️  Audit log purge failed: {e}")
        deleted["audit_logs"] = 0

    return deleted


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
