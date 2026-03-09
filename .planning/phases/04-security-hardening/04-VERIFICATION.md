---
phase: 04-security-hardening
verified: 2026-03-09T21:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
human_verification:
  - test: "Verify 429 on 11th login attempt against the live Railway deployment"
    expected: "First 10 POST /login requests return 200/302; the 11th returns 429 with JSON error"
    why_human: "Rate limit counter persistence across Gunicorn workers requires Redis on Railway. Tests use memory:// backend; real multi-worker behavior can only be verified in production."
  - test: "Verify zero CSP violations in browser console on live deployment"
    expected: "No Content Security Policy warnings or errors appear in Chrome/Firefox DevTools console after logging in and using the dashboard"
    why_human: "CSP enforcement mode blocks inline scripts and disallowed sources — map tiles, CDN assets, and any dynamic content can only be tested end-to-end in a real browser session."
  - test: "Verify login CSRF protection is functioning on live deployment"
    expected: "Submitting the login form normally succeeds; a direct curl POST without csrf_token is rejected with 400"
    why_human: "The Flask test client disables CSRF validation (WTF_CSRF_ENABLED=False) for most tests. Live behavior with a real browser session generating the token is required for full confidence."
---

# Phase 4: Security Hardening Verification Report

**Phase Goal:** Harden the production application against brute-force, CSRF, and content-injection attacks without breaking existing API consumers.
**Verified:** 2026-03-09T21:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                              | Status     | Evidence                                                                                                   |
|----|------------------------------------------------------------------------------------|------------|------------------------------------------------------------------------------------------------------------|
| 1  | POST /login returns 200/302 on first attempt and 429 after 10 from same IP         | VERIFIED   | `@limiter.limit("10 per minute")` on `login_post` (app.py:197); T01/T02 tests pass                        |
| 2  | POST /api/* routes return 200/302 without a csrf_token field (CSRF exempted)       | VERIFIED   | All 13 API POST views carry `@csrf.exempt` (app.py lines 251,390,400,417,453,466,522,567,603,648,666,683,732) |
| 3  | POST /login without csrf_token returns 400 (CSRF enforced on login)                | VERIFIED   | `csrf.init_app(app)` in security.py; login.html has `{{ csrf_token() }}` hidden input; T04 passes          |
| 4  | Every response includes X-Frame-Options: DENY, X-Content-Type-Options: nosniff    | VERIFIED   | Talisman initialized with `frame_options="DENY"` in security.py; T07/T08 tests pass                        |
| 5  | Every HTTPS response includes Strict-Transport-Security with max-age               | VERIFIED   | Talisman `strict_transport_security=True, strict_transport_security_max_age=300`; T09 passes               |
| 6  | Every response includes Content-Security-Policy header (enforcement mode)          | VERIFIED   | `content_security_policy_report_only=False` confirmed in security.py:93; T10 passes                       |
| 7  | templates/login.html contains the csrf_token hidden input                          | VERIFIED   | login.html:44 `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` present                 |
| 8  | REDIS_URL env var used when set; falls back to memory:// for local dev             | VERIFIED   | security.py:63-72 — `redis_url = os.getenv("REDIS_URL")` branch with warning log on fallback              |
| 9  | ProxyFix applied to app.wsgi_app before init_security(app) is called              | VERIFIED   | app.py:52 `app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)`; :56 `init_security(app)` |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact                    | Expected                                                        | Status     | Details                                                                                     |
|-----------------------------|-----------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------|
| `security.py`               | `init_security(app)`, `limiter`, `csrf`, `_CSP` dict           | VERIFIED   | All four exports confirmed present; `content_security_policy_report_only=False` (enforcement) |
| `app.py`                    | ProxyFix applied; init_security called; @limiter.limit on login_post; @csrf.exempt on 13 /api/* POST views | VERIFIED | All wiring confirmed at lines 52, 56, 197, and 14 @csrf.exempt decorators |
| `templates/login.html`      | csrf_token hidden input inside login form                       | VERIFIED   | Line 44: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` confirmed      |
| `requirements.txt`          | flask-limiter[redis], flask-wtf, flask-talisman added           | VERIFIED   | Lines 11-13: `flask-limiter[redis]>=4.1.1`, `flask-wtf>=1.2.0`, `flask-talisman>=1.1.0`    |
| `tests/test_security.py`    | 11 real test functions (T01-T10, T12), not stubs                | VERIFIED   | All 11 functions have real assertions — no `pytest.fail("STUB")` remaining                  |
| `tests/conftest.py`         | `app_client` fixture yielding Flask test client                 | VERIFIED   | Function-scoped fixture at lines 35-54 with `SECRET_KEY`, `WTF_CSRF_ENABLED=False` set      |

---

### Key Link Verification

| From                          | To                           | Via                                            | Status   | Details                                                                              |
|-------------------------------|------------------------------|------------------------------------------------|----------|--------------------------------------------------------------------------------------|
| `app.py`                      | `security.py`                | `from security import limiter, csrf, init_security` | WIRED | app.py:47 — import confirmed; init_security(app) called at line 56                  |
| `security.py`                 | REDIS_URL env var            | `os.getenv("REDIS_URL", fallback "memory://")`  | WIRED    | security.py:63-67 — both Redis and memory:// branches implemented with warning log  |
| `app.py ProxyFix`             | Flask-Limiter get_remote_address | `app.wsgi_app = ProxyFix(...)` at line 52, before init_security at line 56 | WIRED | Correct ordering confirmed; ProxyFix sets REMOTE_ADDR before limiter key_func runs  |
| `templates/login.html`        | CSRFProtect                  | `{{ csrf_token() }}` hidden input               | WIRED    | login.html:44 — hidden input confirmed; csrf.init_app(app) in security.py:76        |
| `security.py Talisman`        | browser CSP enforcement      | `content_security_policy_report_only=False`     | WIRED    | security.py:93 — enforcement mode confirmed; not report-only                         |

---

### Requirements Coverage

| Requirement | Source Plans         | Description                                                                               | Status    | Evidence                                                                                                    |
|-------------|----------------------|-------------------------------------------------------------------------------------------|-----------|-------------------------------------------------------------------------------------------------------------|
| SEC-1       | 04-01, 04-02         | /login POST limited to 10 attempts/min per IP; Flask-Limiter with Redis backend; ProxyFix | SATISFIED | `@limiter.limit("10 per minute")` on login_post; ProxyFix applied; REDIS_URL branch in init_security        |
| SEC-2       | 04-01, 04-02         | Flask-WTF CSRFProtect on /login and /logout; all /api/* routes explicitly exempted         | SATISFIED | `csrf.init_app(app)` in security.py; 13 `@csrf.exempt` decorators verified on all required /api/* POST views |
| SEC-3       | 04-01, 04-02, 04-03  | Flask-Talisman with HSTS, CSP whitelist, X-Frame-Options DENY, X-Content-Type-Options      | SATISFIED | Talisman initialized with all required settings; CSP enforcement mode confirmed (`report_only=False`)        |
| SEC-4       | 04-01, 04-02         | All inline scripts moved to static/ before CSP enforcement enabled                         | SATISFIED | SUMMARY confirms template audit performed; CSP dict has no `unsafe-inline`; enforcement mode active          |
| SEC-5       | 04-03                | 7 open py/sql-injection CodeQL alerts dismissed as false positives                         | SATISFIED (vacuous) | 04-03-SUMMARY confirms 0 py/sql-injection alerts existed on GitHub scan; requirement vacuously satisfied; GitHub confirmed 0 open py/sql-injection alerts |

**Note on SEC-5:** The REQUIREMENTS.md acceptance criteria requires 7 alerts to be dismissed. The 04-03-SUMMARY documents that CodeQL scanned the repo and produced 0 `py/sql-injection` alerts — the rule did not trigger on the placeholder functions in `db/connection.py`. The plan explicitly anticipated this fallback condition and documented SEC-5 as vacuously satisfied with 0 alerts remaining open. This is acceptable: the goal was zero open alerts, and zero exist.

---

### Anti-Patterns Found

None detected. Scanned `security.py`, `app.py`, and `tests/test_security.py` for:
- TODO/FIXME/HACK/PLACEHOLDER comments
- `pytest.fail("STUB")` call remains (none found — all 11 stubs replaced with real assertions)
- Empty implementations (`return null`, `return {}`, `return []`)
- Stub-only handlers

All files are substantive implementations.

---

### Human Verification Required

#### 1. Live Rate Limiting (Multi-Worker Validation)

**Test:** Deploy to Railway with Redis plugin provisioned. From the command line, send 11 consecutive POST /login requests with a wrong password to the live Railway URL.
**Expected:** First 10 return 200 (wrong password render) or 302 (success redirect); the 11th returns 429 with JSON body `{"error": "Too many login attempts. Try again in 1 minute."}`.
**Why human:** Flask-Limiter uses `memory://` in the test suite (no REDIS_URL in test env). The persistence of counters across multiple Gunicorn workers on Railway (the production configuration) can only be verified on live infrastructure.

#### 2. CSP Enforcement — Browser Console Check

**Test:** Log into the live Railway deployment in Chrome or Firefox. Open DevTools Console tab. Navigate the dashboard, view the map, and trigger any visible dashboard features.
**Expected:** Zero Content Security Policy errors or warnings in the console. Map tiles (CARTO basemap) render correctly (not grey squares).
**Why human:** CSP enforcement mode (`content_security_policy_report_only=False`) blocks resources that violate the policy. The CSP dict allows `cdn.jsdelivr.net`, CARTO tiles, and `self` — but any other external resource loaded by a template would produce a browser-visible block that is invisible to the Python test suite.

#### 3. Login Form CSRF Flow (Live Session)

**Test:** Navigate to the live Railway login page in a browser. Submit the form with the correct password.
**Expected:** Login succeeds and user is redirected to the dashboard. The hidden `csrf_token` field is present in the page source.
**Why human:** The Flask test client sets `WTF_CSRF_ENABLED=False` for most tests to isolate behavior. A real browser session exercises the full CSRF token generation and validation round-trip that the automated tests bypass.

---

### Gaps Summary

No gaps. All 9 observable truths verified. All 6 required artifacts exist, are substantive, and are correctly wired. All 5 requirement IDs (SEC-1 through SEC-5) are satisfied. No blocker anti-patterns found.

Three items are flagged for human verification (live deployment checks), but these are operational validation concerns that cannot be verified programmatically, not code gaps.

---

_Verified: 2026-03-09T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
