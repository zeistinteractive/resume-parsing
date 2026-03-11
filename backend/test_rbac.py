"""
Phase C tests — RBAC middleware enforcement.
docker exec resume-engine-backend python test_rbac.py
"""
import json, urllib.request, urllib.error

BASE = "http://localhost:8000/api"
PASS = "\033[32m✅ PASS\033[0m"
FAIL = "\033[31m❌ FAIL\033[0m"
results = []

def req(method, path, body=None, token=None):
    url  = BASE + path
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json"}
    if token: hdrs["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except: return e.code, {}

def check(name, cond, detail=""):
    results.append(cond)
    print(f"  {PASS if cond else FAIL}  {name}" + (f" — {detail}" if detail else ""))

print("\n=== Phase C — RBAC Middleware Tests ===\n")

# ── Get tokens ────────────────────────────────────────────────────────────────
_, b = req("POST", "/auth/login", {"email": "admin@example.com", "password": "Admin@1234"})
admin_tok = b.get("access_token", "")

from users_db import get_user_by_email, create_user
from auth_utils import hash_password
try:
    create_user("Rec C", "recruiter_c@test.com", hash_password("Recpass@1"), "recruiter")
except: pass
_, b = req("POST", "/auth/login", {"email": "recruiter_c@test.com", "password": "Recpass@1"})
rec_tok = b.get("access_token", "")

print("── Public routes (no token needed) ──")
code, _ = req("GET", "/health")
check("T01 GET /health → 200 (public)", code == 200)

code, _ = req("GET", "/download/file/invalidtoken")
check("T02 GET /download/file/* → 404 not 401 (public token route)", code == 404)

print("\n── Unauthenticated access → 401 ──")
for method, path in [
    ("GET",  "/resumes"),
    ("GET",  "/resumes/1"),
    ("GET",  "/search"),
    ("GET",  "/autocomplete/titles?q=eng"),
    ("GET",  "/saved-searches"),
    ("POST", "/upload"),
]:
    code, _ = req(method, path)
    check(f"T03 {method} {path} without token → 401", code == 401)

print("\n── Authenticated recruiter can access resume/search endpoints ──")
code, _ = req("GET", "/resumes", token=rec_tok)
check("T04 GET /resumes with recruiter token → 200", code == 200)

code, _ = req("GET", "/search", token=rec_tok)
check("T05 GET /search with recruiter token → 200", code == 200)

code, _ = req("GET", "/saved-searches", token=rec_tok)
check("T06 GET /saved-searches with recruiter token → 200", code == 200)

print("\n── Admin-only endpoints → 403 for recruiter ──")
code, _ = req("DELETE", "/resumes/99999", token=rec_tok)
check("T07 DELETE /resumes/* with recruiter → 403", code == 403)

code, _ = req("GET", "/download/history", token=rec_tok)
check("T08 GET /download/history with recruiter → 403", code == 403)

code, _ = req("GET", "/users", token=rec_tok)
check("T09 GET /users with recruiter → 403", code == 403)

code, _ = req("GET", "/audit-logs", token=rec_tok)
check("T10 GET /audit-logs with recruiter → 403", code == 403)

print("\n── Admin can access admin-only endpoints ──")
code, _ = req("GET", "/download/history", token=admin_tok)
check("T11 GET /download/history with admin → 200", code == 200)

code, _ = req("GET", "/users", token=admin_tok)
check("T12 GET /users with admin → 200", code == 200)

code, _ = req("GET", "/audit-logs", token=admin_tok)
check("T13 GET /audit-logs with admin → 200", code == 200)

# DELETE /resumes/99999 returns 404 (not found) with admin — confirms auth passed
code, _ = req("DELETE", "/resumes/99999", token=admin_tok)
check("T14 DELETE /resumes/* with admin → 404 (auth passed, resume missing)", code == 404)

print("\n── Expired / invalid token → 401 ──")
code, _ = req("GET", "/resumes", token="header.payload.badsig")
check("T15 garbled token → 401", code == 401)

print("\n── Logout blacklists token ──")
_, b = req("POST", "/auth/login", {"email": "recruiter_c@test.com", "password": "Recpass@1"})
fresh = b.get("access_token", "")
code, _ = req("GET", "/resumes", token=fresh)
check("T16 fresh token works before logout → 200", code == 200)
req("POST", "/auth/logout", token=fresh)
code, _ = req("GET", "/resumes", token=fresh)
check("T17 same token rejected after logout → 401", code == 401)

print(f"\n{'─'*40}")
passed = sum(results)
total  = len(results)
print(f"{'✅ ALL PASSED' if passed == total else '❌ SOME FAILED'}  {passed}/{total}\n")
