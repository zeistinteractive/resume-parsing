"""
Phase B tests — User Management API + Forgot/Reset Password.
Run inside the backend container:
  docker exec resume-engine-backend python test_users.py
"""

import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"

PASS = "\033[32m✅ PASS\033[0m"
FAIL = "\033[31m❌ FAIL\033[0m"
results = []


def req(method, path, body=None, token=None):
    url  = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, condition, detail=""):
    icon = PASS if condition else FAIL
    results.append(condition)
    print(f"  {icon}  {name}" + (f" — {detail}" if detail else ""))
    return condition


print("\n=== Phase B — User Management API Tests ===\n")

# ── Get admin token ───────────────────────────────────────────────────────────
code, body = req("POST", "/auth/login", {"email": "admin@example.com", "password": "Admin@1234"})
assert code == 200, f"Admin login failed: {body}"
admin_token = body["access_token"]
print(f"Admin logged in. Token: {admin_token[:20]}…\n")


# ── US-007: List users ────────────────────────────────────────────────────────
print("── List users (US-007) ──")
code, body = req("GET", "/users", token=admin_token)
check("T01 GET /users → 200 for admin", code == 200)
check("T01 returns total + items", "total" in body and "items" in body)
initial_count = body["total"]

# Recruiter cannot list users
from users_db import create_user, get_user_by_email
from auth_utils import hash_password
try:
    create_user("Rec User", "recruiter_b@test.com", hash_password("Recpass@1"), "recruiter")
except Exception:
    pass
code2, b2 = req("POST", "/auth/login", {"email": "recruiter_b@test.com", "password": "Recpass@1"})
rec_token = b2.get("access_token", "")
code, body = req("GET", "/users", token=rec_token)
check("T02 GET /users → 403 for recruiter", code == 403)

# Search filter
code, body = req("GET", "/users?search=admin", token=admin_token)
check("T03 search param works", code == 200)


# ── US-006: Create user ───────────────────────────────────────────────────────
print("\n── Create user (US-006) ──")
new_user_email = "newrecruiter@test.com"

code, body = req("POST", "/users",
                 {"full_name": "New Recruiter", "email": new_user_email, "role": "recruiter"},
                 token=admin_token)
check("T04 create user → 201", code == 201)
check("T04 user has id", bool(body.get("id")))
check("T04 must_change_password = True", body.get("must_change_password") is True)
new_user_id = body.get("id", "")

# Duplicate email
code, body = req("POST", "/users",
                 {"full_name": "Dup", "email": new_user_email, "role": "recruiter"},
                 token=admin_token)
check("T05 duplicate email → 409", code == 409)

# Invalid role
code, body = req("POST", "/users",
                 {"full_name": "Bad", "email": "bad@test.com", "role": "superuser"},
                 token=admin_token)
check("T06 invalid role → 422", code == 422)

# Non-admin cannot create user
code, body = req("POST", "/users",
                 {"full_name": "X", "email": "x@x.com", "role": "recruiter"},
                 token=rec_token)
check("T07 recruiter cannot create user → 403", code == 403)


# ── US-007: Get single user ───────────────────────────────────────────────────
print("\n── Get user by ID (US-007) ──")
code, body = req("GET", f"/users/{new_user_id}", token=admin_token)
check("T08 GET /users/{id} → 200", code == 200)
check("T08 email matches", body.get("email") == new_user_email)
check("T08 no password_hash in response", "password_hash" not in body)

code, body = req("GET", "/users/00000000-0000-0000-0000-000000000000", token=admin_token)
check("T09 unknown id → 404", code == 404)


# ── US-008: Edit user ─────────────────────────────────────────────────────────
print("\n── Edit user (US-008) ──")
code, body = req("PATCH", f"/users/{new_user_id}",
                 {"full_name": "Updated Name", "email": new_user_email, "role": "recruiter"},
                 token=admin_token)
check("T10 PATCH /users/{id} → 200", code == 200)
check("T10 full_name updated", body.get("full_name") == "Updated Name")

# Steal another user's email → 409
admin_user = get_user_by_email("admin@example.com")
code, body = req("PATCH", f"/users/{new_user_id}",
                 {"full_name": "X", "email": "admin@example.com", "role": "recruiter"},
                 token=admin_token)
check("T11 email already in use → 409", code == 409)


# ── US-009: Deactivate / reactivate ──────────────────────────────────────────
print("\n── Activate / Deactivate (US-009) ──")
code, body = req("PATCH", f"/users/{new_user_id}/status",
                 {"status": "inactive"}, token=admin_token)
check("T12 deactivate → 200", code == 200)
check("T12 status = inactive", body.get("status") == "inactive")

# Deactivated user can no longer login
# (get_current_user checks status on every request)
code, body = req("POST", "/auth/login",
                 {"email": new_user_email, "password": "anything"})
check("T13 deactivated user login → 401 or 403", code in (401, 403))

# Reactivate
code, body = req("PATCH", f"/users/{new_user_id}/status",
                 {"status": "active"}, token=admin_token)
check("T14 reactivate → 200", code == 200)
check("T14 status = active", body.get("status") == "active")

# Cannot deactivate self
admin_id = get_user_by_email("admin@example.com")["id"]
code, body = req("PATCH", f"/users/{admin_id}/status",
                 {"status": "inactive"}, token=admin_token)
check("T15 cannot deactivate own account → 400", code == 400)


# ── US-010: Admin password reset ──────────────────────────────────────────────
print("\n── Admin reset password (US-010) ──")
code, body = req("POST", f"/users/{new_user_id}/reset-password",
                 token=admin_token)
check("T16 admin reset password → 200", code == 200)
check("T16 success message present", "reset" in body.get("message","").lower())

# must_change_password should now be True for the target user
code, body = req("GET", f"/users/{new_user_id}", token=admin_token)
check("T17 must_change_password = True after admin reset", body.get("must_change_password") is True)


# ── US-004: Forgot / reset password ──────────────────────────────────────────
print("\n── Forgot / Reset password (US-004) ──")

# Forgot password always returns 200 (no enumeration)
code, body = req("POST", "/auth/forgot-password", {"email": "nobody@nowhere.com"})
check("T18 unknown email → 200 (no enumeration)", code == 200)

code, body = req("POST", "/auth/forgot-password", {"email": "admin@example.com"})
check("T19 known email → 200", code == 200)
check("T19 message present", bool(body.get("message")))

# Simulate reset: fetch token directly from DB
import psycopg2, psycopg2.extras, hashlib, secrets, os
from database import _get_conn

# Generate + store a fresh token directly so we can test the reset endpoint
raw_token  = secrets.token_hex(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
from datetime import datetime, timedelta, timezone
expiry = datetime.now(timezone.utc) + timedelta(hours=1)
admin_u = get_user_by_email("admin@example.com")
from users_db import set_reset_token
set_reset_token(admin_u["id"], token_hash, expiry)

# Reset with invalid token
code, body = req("POST", "/auth/reset-password",
                 {"token": "badtoken", "new_password": "Newpass@9999"})
check("T20 invalid token → 400", code == 400)

# Reset with short password
code, body = req("POST", "/auth/reset-password",
                 {"token": raw_token, "new_password": "short"})
check("T21 short password → 422", code == 422)

# Valid reset
code, body = req("POST", "/auth/reset-password",
                 {"token": raw_token, "new_password": "Admin@1234"})
check("T22 valid reset → 200", code == 200)

# Token is single-use
code, body = req("POST", "/auth/reset-password",
                 {"token": raw_token, "new_password": "Admin@1234"})
check("T23 token already used → 400", code == 400)

# Can login with new password
code, body = req("POST", "/auth/login",
                 {"email": "admin@example.com", "password": "Admin@1234"})
check("T24 login after reset → 200", code == 200)


# ── Audit log endpoint (US-016) ───────────────────────────────────────────────
print("\n── Audit log (US-016) ──")
new_token = body.get("access_token", admin_token)
code, body = req("GET", "/audit-logs", token=new_token)
check("T25 GET /audit-logs → 200 for admin", code == 200)
check("T25 has items", len(body.get("items", [])) > 0)
check("T25 has total", body.get("total", 0) > 0)

code, body = req("GET", "/audit-logs", token=rec_token)
check("T26 GET /audit-logs → 403 for recruiter", code == 403)

# Filter by action
code, body = req("GET", "/audit-logs?action=USER_LOGIN", token=new_token)
check("T27 filter by action works", code == 200)


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'─'*40}")
passed = sum(results)
total  = len(results)
print(f"{'✅ ALL PASSED' if passed == total else '❌ SOME FAILED'}  {passed}/{total}\n")
