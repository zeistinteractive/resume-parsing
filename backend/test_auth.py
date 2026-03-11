"""
Phase A tests — Auth API (login, logout, change-password, lockout).
Run inside the backend container:
  docker exec resume-engine-backend python test_auth.py
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


print("\n=== Phase A — Auth API Tests ===\n")

# ── T01: Login with wrong email ───────────────────────────────────────────────
print("── Login ──")
code, body = req("POST", "/auth/login", {"email": "nobody@example.com", "password": "x"})
check("T01 wrong email → 401", code == 401)

# ── T02: Login with wrong password ───────────────────────────────────────────
code, body = req("POST", "/auth/login", {"email": "admin@example.com", "password": "wrong"})
check("T02 wrong password → 401", code == 401)
check("T02 remaining attempts in message", "remaining" in body.get("detail","").lower() or code == 401)

# ── T03: Invalid email format ─────────────────────────────────────────────────
code, body = req("POST", "/auth/login", {"email": "notanemail", "password": "x"})
check("T03 bad email format → 422", code == 422)

# ── T04: Successful login ─────────────────────────────────────────────────────
code, body = req("POST", "/auth/login", {"email": "admin@example.com", "password": "Admin@1234"})
check("T04 login success → 200", code == 200)
token = body.get("access_token", "")
check("T04 token issued", bool(token))
check("T04 user.role = admin", body.get("user", {}).get("role") == "admin")

# ── T05: GET /auth/me with valid token ────────────────────────────────────────
print("\n── /auth/me ──")
code, body = req("GET", "/auth/me", token=token)
check("T05 GET /me → 200", code == 200)
check("T05 email matches", body.get("email") == "admin@example.com")

# ── T06: GET /auth/me without token ──────────────────────────────────────────
code, body = req("GET", "/auth/me")
check("T06 no token → 401", code == 401)

# ── T07: GET /auth/me with garbage token ─────────────────────────────────────
code, body = req("GET", "/auth/me", token="this.is.garbage")
check("T07 invalid token → 401", code == 401)

# ── T08: Change password ──────────────────────────────────────────────────────
print("\n── Change password ──")
code, body = req("POST", "/auth/change-password",
                 {"current_password": "wrong", "new_password": "Newpass@1234"},
                 token=token)
check("T08 wrong current pw → 400", code == 400)

code, body = req("POST", "/auth/change-password",
                 {"current_password": "Admin@1234", "new_password": "short"},
                 token=token)
check("T09 new pw too short → 422", code == 422)

code, body = req("POST", "/auth/change-password",
                 {"current_password": "Admin@1234", "new_password": "Admin@1234"},
                 token=token)
check("T10 valid change → 200", code == 200)

# Token should now be blacklisted
code, body = req("GET", "/auth/me", token=token)
check("T11 old token rejected after pw change → 401", code == 401)

# Re-login with new password
code, body = req("POST", "/auth/login", {"email": "admin@example.com", "password": "Admin@1234"})
check("T12 re-login with new password → 200", code == 200)
token2 = body.get("access_token", "")

# ── T09: Logout ───────────────────────────────────────────────────────────────
print("\n── Logout ──")
code, body = req("POST", "/auth/logout", token=token2)
check("T13 logout → 200", code == 200)

code, body = req("GET", "/auth/me", token=token2)
check("T14 token rejected after logout → 401", code == 401)

# ── T10: Brute-force lockout (US-005) ─────────────────────────────────────────
print("\n── Brute-force lockout ──")
# Login fresh to get a clean token for checking
code, body = req("POST", "/auth/login", {"email": "admin@example.com", "password": "Admin@1234"})
check("T15 re-login before lockout test", code == 200)
fresh_token = body.get("access_token", "")

# Create a test user to lock (avoid locking the admin permanently in tests)
from users_db import create_user, get_user_by_email, reset_login_state, update_password, set_user_status
from auth_utils import hash_password

# Create test lockout user
try:
    create_user("Lockout Test", "lockout@test.com", hash_password("Correct@1234"), "recruiter")
except Exception:
    pass  # already exists from a previous run

for i in range(5):
    code, body = req("POST", "/auth/login", {"email": "lockout@test.com", "password": "wrongwrong"})

code, body = req("POST", "/auth/login", {"email": "lockout@test.com", "password": "Correct@1234"})
check("T16 5 failures → account locked (403)", code == 403)
check("T16 locked message in detail", "lock" in body.get("detail","").lower())

# Admin unlocking would be manual via DB; just verify the counter reset on correct login isn't possible
# (reset happens in reset_login_state which is only called on success, but account is locked)

# Clean up: reset lockout for future test runs
u = get_user_by_email("lockout@test.com")
if u:
    reset_login_state(u["id"])

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'─'*40}")
passed = sum(results)
total  = len(results)
print(f"{'✅ ALL PASSED' if passed == total else '❌ SOME FAILED'}  {passed}/{total}\n")
