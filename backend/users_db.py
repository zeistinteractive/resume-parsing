"""
Users & Audit Logs — database layer.

Tables managed here:
  users       — platform users with roles (admin / recruiter)
  audit_logs  — immutable event log for all auth + admin actions
"""

from typing import Optional
import psycopg2.extras

from database import _get_conn   # reuse the shared connection pool


# ── Schema ────────────────────────────────────────────────────────────────────

def init_users_db():
    with _get_conn() as conn:
        with conn.cursor() as c:

            # Users table — UUID PKs to match the PRD schema.
            # gen_random_uuid() is built into PostgreSQL 13+ (we use 16).
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    full_name          VARCHAR(255) NOT NULL,
                    email              VARCHAR(255) UNIQUE NOT NULL,
                    password_hash      VARCHAR(255) NOT NULL,
                    role               VARCHAR(20)  NOT NULL DEFAULT 'recruiter',
                    status             VARCHAR(20)  NOT NULL DEFAULT 'active',
                    failed_logins      INTEGER      NOT NULL DEFAULT 0,
                    locked_until       TIMESTAMPTZ,
                    reset_token        VARCHAR(255),
                    reset_token_expiry TIMESTAMPTZ,
                    last_login_at      TIMESTAMPTZ,
                    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    created_by         UUID         REFERENCES users(id) ON DELETE SET NULL
                )
            """)

            # Safe migration: add must_change_password if upgrading from Phase A
            c.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "must_change_password BOOLEAN NOT NULL DEFAULT FALSE"
            )

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS users_email_idx  ON users (lower(email))",
                "CREATE INDEX IF NOT EXISTS users_role_idx   ON users (role)",
                "CREATE INDEX IF NOT EXISTS users_status_idx ON users (status)",
            ]:
                c.execute(idx_sql)

            # Audit log — one row per security/admin event.
            # user_id is nullable so rows survive account deletion.
            c.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id        UUID         REFERENCES users(id) ON DELETE SET NULL,
                    user_email     VARCHAR(255) NOT NULL,
                    action         VARCHAR(100) NOT NULL,
                    target_user_id UUID         REFERENCES users(id) ON DELETE SET NULL,
                    old_value      TEXT,
                    new_value      TEXT,
                    ip_address     VARCHAR(45)  NOT NULL DEFAULT '',
                    outcome        VARCHAR(20)  NOT NULL DEFAULT 'success',
                    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                )
            """)

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS audit_user_idx    ON audit_logs (user_id)",
                "CREATE INDEX IF NOT EXISTS audit_action_idx  ON audit_logs (action)",
                "CREATE INDEX IF NOT EXISTS audit_created_idx ON audit_logs (created_at DESC)",
            ]:
                c.execute(idx_sql)

    print("✅ Users DB initialized")


# ── User reads ────────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                "SELECT * FROM users WHERE lower(email) = lower(%s)",
                (email.strip(),),
            )
            row = c.fetchone()
    return _user_dict(row)


def get_user_by_id(user_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = c.fetchone()
    return _user_dict(row)


def list_users(limit: int = 50, offset: int = 0, search: str = "") -> dict:
    """Return paginated user list for the Admin users screen."""
    with _get_conn() as conn:
        with conn.cursor() as cnt:
            if search:
                cnt.execute(
                    "SELECT COUNT(*) FROM users "
                    "WHERE full_name ILIKE %s OR email ILIKE %s",
                    (f"%{search}%", f"%{search}%"),
                )
            else:
                cnt.execute("SELECT COUNT(*) FROM users")
            total = cnt.fetchone()[0]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            if search:
                c.execute(
                    """
                    SELECT id, full_name, email, role, status,
                           last_login_at, created_at
                    FROM users
                    WHERE full_name ILIKE %s OR email ILIKE %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (f"%{search}%", f"%{search}%", limit, offset),
                )
            else:
                c.execute(
                    """
                    SELECT id, full_name, email, role, status,
                           last_login_at, created_at
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
            rows = c.fetchall()

    return {
        "total":  total,
        "items":  [_user_public(r) for r in rows],
        "limit":  limit,
        "offset": offset,
    }


def count_users() -> int:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM users")
            return c.fetchone()[0]


# ── User writes ───────────────────────────────────────────────────────────────

def create_user(
    full_name:     str,
    email:         str,
    password_hash: str,
    role:          str,
    created_by:    Optional[str] = None,
) -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                INSERT INTO users (full_name, email, password_hash, role, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, full_name, email, role, status, created_at
                """,
                (full_name.strip(), email.strip().lower(), password_hash, role, created_by),
            )
            return dict(c.fetchone())


def increment_failed_logins(user_id: str) -> int:
    """
    Bump failed_logins by 1.
    If the new count reaches 5, set locked_until = now + 15 min.
    Returns the updated failed_logins count.
    """
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                UPDATE users
                SET
                    failed_logins = failed_logins + 1,
                    locked_until  = CASE
                        WHEN failed_logins + 1 >= 5
                        THEN NOW() + INTERVAL '15 minutes'
                        ELSE locked_until
                    END
                WHERE id = %s
                RETURNING failed_logins
                """,
                (user_id,),
            )
            row = c.fetchone()
    return row[0] if row else 0


def reset_login_state(user_id: str):
    """On successful login: clear lockout, reset counter, stamp last_login_at."""
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                UPDATE users
                SET failed_logins = 0,
                    locked_until  = NULL,
                    last_login_at = NOW()
                WHERE id = %s
                """,
                (user_id,),
            )


def update_password(user_id: str, password_hash: str):
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (password_hash, user_id),
            )


def set_must_change_password(user_id: str, value: bool) -> None:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET must_change_password = %s WHERE id = %s",
                (value, user_id),
            )


def update_user(user_id: str, full_name: str, email: str, role: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                UPDATE users
                SET full_name = %s, email = lower(%s), role = %s
                WHERE id = %s
                RETURNING id, full_name, email, role, status, created_at
                """,
                (full_name.strip(), email.strip(), role, user_id),
            )
            row = c.fetchone()
    return dict(row) if row else None


def set_user_status(user_id: str, status: str) -> bool:
    """Activate or deactivate a user. Returns True if row was found."""
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET status = %s WHERE id = %s RETURNING id",
                (status, user_id),
            )
            return c.fetchone() is not None


def set_reset_token(user_id: str, token_hash: str, expiry_ts) -> None:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET reset_token = %s, reset_token_expiry = %s WHERE id = %s",
                (token_hash, expiry_ts, user_id),
            )


def clear_reset_token(user_id: str) -> None:
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET reset_token = NULL, reset_token_expiry = NULL WHERE id = %s",
                (user_id,),
            )


def get_user_by_reset_token(token_hash: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                SELECT * FROM users
                WHERE reset_token = %s
                  AND reset_token_expiry > NOW()
                """,
                (token_hash,),
            )
            row = c.fetchone()
    return _user_dict(row)


# ── Audit log ─────────────────────────────────────────────────────────────────

def log_audit(
    user_email:     str,
    action:         str,
    ip_address:     str,
    outcome:        str,                    # 'success' | 'failure'
    user_id:        Optional[str] = None,
    target_user_id: Optional[str] = None,
    old_value:      Optional[str] = None,
    new_value:      Optional[str] = None,
) -> None:
    """Non-fatal — a logging failure must never block the originating request."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    INSERT INTO audit_logs
                        (user_id, user_email, action, target_user_id,
                         old_value, new_value, ip_address, outcome)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id, user_email, action, target_user_id,
                        old_value, new_value, ip_address or "", outcome,
                    ),
                )
    except Exception as e:
        print(f"⚠️  Audit log failed [{action}]: {e}")


def get_audit_logs(
    limit:      int  = 50,
    offset:     int  = 0,
    user_email: str  = "",
    action:     str  = "",
    date_from:  str  = None,
    date_to:    str  = None,
) -> dict:
    conditions = []
    params     = []

    if user_email:
        conditions.append("al.user_email ILIKE %s")
        params.append(f"%{user_email}%")
    if action:
        conditions.append("al.action = %s")
        params.append(action)
    if date_from:
        conditions.append("al.created_at >= %s::date")
        params.append(date_from)
    if date_to:
        conditions.append("al.created_at < (%s::date + interval '1 day')")
        params.append(date_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _get_conn() as conn:
        with conn.cursor() as cnt:
            cnt.execute(f"SELECT COUNT(*) FROM audit_logs al {where}", params)
            total = cnt.fetchone()[0]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                f"""
                SELECT al.id, al.user_id, al.user_email, al.action,
                       al.target_user_id, al.old_value, al.new_value,
                       al.ip_address, al.outcome, al.created_at,
                       u.full_name AS actor_name
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.user_id
                {where}
                ORDER BY al.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = c.fetchall()

    return {
        "total":  total,
        "items":  [
            {
                "id":             str(r["id"]),
                "user_id":        str(r["user_id"]) if r["user_id"] else None,
                "user_email":     r["user_email"],
                "actor_name":     r["actor_name"],
                "action":         r["action"],
                "target_user_id": str(r["target_user_id"]) if r["target_user_id"] else None,
                "old_value":      r["old_value"],
                "new_value":      r["new_value"],
                "ip_address":     r["ip_address"],
                "outcome":        r["outcome"],
                "created_at":     r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "limit":  limit,
        "offset": offset,
    }


def purge_old_audit_logs(days: int = 365) -> int:
    """Delete audit log entries older than `days`. Returns count of deleted rows."""
    with _get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '%s days'",
                (days,),
            )
            return c.rowcount


# ── Internal helpers ──────────────────────────────────────────────────────────

def _user_dict(row) -> Optional[dict]:
    if not row:
        return None
    d = dict(row)
    # Serialize non-JSON-native types
    d["id"]         = str(d["id"])
    d["created_by"] = str(d["created_by"]) if d.get("created_by") else None
    for ts_col in ("last_login_at", "created_at", "locked_until", "reset_token_expiry"):
        if d.get(ts_col):
            d[ts_col] = d[ts_col].isoformat()
    return d


def _user_public(row) -> dict:
    """Safe subset of user fields for list responses (no password_hash etc.)."""
    d = dict(row)
    d["id"] = str(d["id"])
    for ts_col in ("last_login_at", "created_at"):
        if d.get(ts_col):
            d[ts_col] = d[ts_col].isoformat()
    return d
