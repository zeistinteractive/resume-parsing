import sqlite3
import json
import shlex
from pathlib import Path

DB_PATH = Path(__file__).parent / "resumes.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Main resumes table
    c.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            raw_text    TEXT,
            parsed_data TEXT,
            parse_status TEXT DEFAULT 'pending',
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Recreate FTS5 table without content='' so resume_id and snippet() work correctly
    c.execute("DROP TABLE IF EXISTS resumes_fts")
    c.execute("""
        CREATE VIRTUAL TABLE resumes_fts
        USING fts5(
            resume_id UNINDEXED,
            raw_text,
            skills_text
        )
    """)

    # Repopulate FTS index from existing successfully parsed resumes
    c.execute("SELECT id, raw_text, parsed_data FROM resumes WHERE parse_status='success' AND raw_text IS NOT NULL")
    for row in c.fetchall():
        try:
            parsed = json.loads(row[2]) if row[2] else {}
        except Exception:
            parsed = {}
        skills_text = " ".join(parsed.get("skills", []))
        c.execute(
            "INSERT INTO resumes_fts (resume_id, raw_text, skills_text) VALUES (?, ?, ?)",
            (str(row[0]), row[1], skills_text)
        )

    conn.commit()
    conn.close()
    print("✅ Database initialized")


def insert_resume(filename: str, file_path: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO resumes (filename, file_path, parse_status) VALUES (?, ?, 'pending')",
        (filename, file_path)
    )
    resume_id = c.lastrowid
    conn.commit()
    conn.close()
    return resume_id


def update_resume_parsed(resume_id: int, raw_text: str, parsed_data: dict):
    conn = get_conn()
    c = conn.cursor()

    parsed_json = json.dumps(parsed_data)
    skills_text = " ".join(parsed_data.get("skills", []))

    c.execute("""
        UPDATE resumes
        SET raw_text=?, parsed_data=?, parse_status='success'
        WHERE id=?
    """, (raw_text, parsed_json, resume_id))

    # Update FTS index
    c.execute("DELETE FROM resumes_fts WHERE resume_id=?", (str(resume_id),))
    c.execute(
        "INSERT INTO resumes_fts (resume_id, raw_text, skills_text) VALUES (?, ?, ?)",
        (str(resume_id), raw_text, skills_text)
    )

    conn.commit()
    conn.close()


def update_resume_failed(resume_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE resumes SET parse_status='failed' WHERE id=?", (resume_id,))
    conn.commit()
    conn.close()


def get_all_resumes():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, filename, parse_status, uploaded_at,
               json_extract(parsed_data, '$.name') as candidate_name,
               json_extract(parsed_data, '$.email') as email,
               json_extract(parsed_data, '$.skills') as skills_json
        FROM resumes
        ORDER BY uploaded_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    results = []
    for row in rows:
        skills = []
        if row["skills_json"]:
            try:
                skills = json.loads(row["skills_json"])[:6]
            except Exception:
                pass
        results.append({
            "id": row["id"],
            "filename": row["filename"],
            "parse_status": row["parse_status"],
            "uploaded_at": row["uploaded_at"],
            "candidate_name": row["candidate_name"],
            "email": row["email"],
            "skills": skills,
        })
    return results


def get_resume_by_id(resume_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM resumes WHERE id=?", (resume_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    parsed = {}
    if row["parsed_data"]:
        try:
            parsed = json.loads(row["parsed_data"])
        except Exception:
            pass

    return {
        "id": row["id"],
        "filename": row["filename"],
        "file_path": row["file_path"],
        "raw_text": row["raw_text"],
        "parsed_data": parsed,
        "parse_status": row["parse_status"],
        "uploaded_at": row["uploaded_at"],
    }


def delete_resume(resume_id: int) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM resumes WHERE id=?", (resume_id,))
    if not c.fetchone():
        conn.close()
        return False
    c.execute("DELETE FROM resumes WHERE id=?", (resume_id,))
    c.execute("DELETE FROM resumes_fts WHERE resume_id=?", (str(resume_id),))
    conn.commit()
    conn.close()
    return True


def count_resumes() -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM resumes")
    count = c.fetchone()[0]
    conn.close()
    return count


def _build_fts_query(raw: str, mode: str = 'or') -> str:
    """
    Convert a free-text user query into an FTS5 query.

    mode='or'  → any keyword matches  (Python React → "Python" OR "React")
    mode='and' → all keywords required (Python React → "Python" AND "React")

    Quoted phrases are kept intact: "Senior Engineer" → "Senior Engineer"
    Special characters like C++ are preserved inside quotes.
    """
    raw = raw.strip()
    if not raw:
        return raw

    # Respect quoted phrases (e.g. "Senior Engineer")
    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()

    parts = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # Escape inner double-quotes, wrap in quotes so FTS5 treats it as a
        # literal term/phrase rather than syntax
        escaped = token.replace('"', '""')
        parts.append(f'"{escaped}"')

    if not parts:
        return f'"{raw}"'

    joiner = ' AND ' if mode.lower() == 'and' else ' OR '
    return joiner.join(parts)


def search_resumes(query: str, limit: int = 20, mode: str = 'or'):
    conn = get_conn()
    c = conn.cursor()

    fts_query = _build_fts_query(query, mode)

    try:
        c.execute("""
            SELECT
                r.id, r.filename, r.parse_status, r.uploaded_at,
                json_extract(r.parsed_data, '$.name') as candidate_name,
                json_extract(r.parsed_data, '$.email') as email,
                json_extract(r.parsed_data, '$.skills') as skills_json,
                snippet(resumes_fts, 1, '<mark>', '</mark>', '...', 20) as snippet,
                bm25(resumes_fts) as score
            FROM resumes_fts
            JOIN resumes r ON r.id = CAST(resumes_fts.resume_id AS INTEGER)
            WHERE resumes_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (fts_query, limit))
        rows = c.fetchall()
    except Exception as e:
        print(f"Search error: {e}")
        conn.close()
        return []

    conn.close()

    results = []
    for row in rows:
        skills = []
        if row["skills_json"]:
            try:
                skills = json.loads(row["skills_json"])[:8]
            except Exception:
                pass
        results.append({
            "id": row["id"],
            "filename": row["filename"],
            "parse_status": row["parse_status"],
            "uploaded_at": row["uploaded_at"],
            "candidate_name": row["candidate_name"],
            "email": row["email"],
            "skills": skills,
            "snippet": row["snippet"] or "",
        })
    return results
