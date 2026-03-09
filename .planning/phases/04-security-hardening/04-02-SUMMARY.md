---
phase: 04-security-hardening
plan: 02
subsystem: security
tags: [flask-limiter, flask-wtf, flask-talisman, csrf, rate-limiting, csp, proxyfix, security-headers]

# Dependency graph
requires:
  - phase: 04-security-hardening
    provides: 11 failing test stubs (T01-T12) in test_security.py, app_client fixture in conftest.py
  - phase: 01-database-decomposition
    provides: SECRET_KEY enforcement at startup (app.py startup guard)
provides:
  - security.py module with limiter, csrf, _CSP, init_security(app)
  - Flask-Limiter rate limiting on /login (10/min, Redis or memory fallback)
  - Flask-WTF CSRFProtect on login form; all 13 /api/* POST routes exempted
  - Flask-Talisman security headers (X-Frame-Options, X-Content-Type-Options, HSTS, CSP-Report-Only)
  - ProxyFix applied to app.wsgi_app for Railway real-IP extraction
  - /csp-report no-op endpoint for Talisman report-only mode
  - csrf_token hidden input in templates/login.html
  - 11 passing security tests (T01-T10, T12)
affects: [04-03-PLAN.md]

# Tech tracking
tech-stack:
  added: [flask-limiter[redis]>=4.1.1, flask-wtf>=1.2.0, flask-talisman>=1.1.0]
  patterns:
    - "security.py module pattern: all security extensions initialized in one file, imported into app.py"
    - "ProxyFix applied immediately after app = Flask(__name__) before init_security"
    - "CSRF exemption via csrf._exempt_views set (Flask-WTF 1.2.x mechanism, not _csrf_exempt attribute)"
    - "HSTS test requires X-Forwarded-Proto: https header (Talisman only adds HSTS for HTTPS requests)"

key-files:
  created: [security.py]
  modified: [app.py, templates/login.html, requirements.txt, tests/test_security.py]

key-decisions:
  - "Flask-Limiter 4.x: storage_uri passed via app.config['RATELIMIT_STORAGE_URI'] before limiter.init_app(app), not as kwarg to init_app()"
  - "wntrblm flask-talisman requires content_security_policy_report_uri when report_only=True — added /csp-report no-op endpoint"
  - "Flask-WTF csrf.exempt() adds view to _exempt_views set (module.qualname string), does not set _csrf_exempt attribute on function"
  - "T09 HSTS test uses X-Forwarded-Proto: https header — Talisman checks request.is_secure OR X-Forwarded-Proto header for HSTS eligibility"
  - "T03 ProxyFix test uses werkzeug EnvironBuilder + minimal WSGI capture app — Flask 3.x blocks before_request registration after first request"
  - "CSP in report-only mode (content_security_policy_report_only=True) for Plan 02 — flip to False in Plan 04-03 after verifying zero browser violations"

patterns-established:
  - "All security tests pass with WTF_CSRF_ENABLED=False in app_client fixture (T04 temporarily enables it)"
  - "T02 rate-limit test calls limiter.reset() before the 11-request loop to clear memory:// counter state"
  - "HSTS requires HTTPS signal (is_secure or X-Forwarded-Proto) — tests must simulate this explicitly"

requirements-completed: [SEC-1, SEC-2, SEC-3, SEC-4]

# Metrics
duration: 7min
completed: 2026-03-09
---

# Phase 4 Plan 02: Security Hardening Implementation Summary

**Flask-Limiter (10/min login rate limit), Flask-WTF CSRFProtect (login protected, all 13 /api/* POST routes exempted), and Flask-Talisman (X-Frame-Options DENY, nosniff, HSTS, CSP-Report-Only) wired into security.py and app.py**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-09T14:45:08Z
- **Completed:** 2026-03-09T14:52:04Z
- **Tasks:** 1 (+ checkpoint awaiting human verify)
- **Files modified:** 5

## Accomplishments
- Created security.py with module-level `limiter` (Flask-Limiter), `csrf` (Flask-WTF CSRFProtect), `_CSP` dict, and `init_security(app)` function
- Applied ProxyFix to app.wsgi_app, wired init_security into app.py startup sequence, added @limiter.limit and @csrf.exempt to all required routes
- Added csrf_token hidden input to templates/login.html
- Replaced all 11 STUB test bodies with real assertions — all 145 tests pass (11 new + 134 existing, zero regressions)
- CSP in report-only mode with report URI pointing to /csp-report no-op endpoint

## Task Commits

Each task was committed atomically:

1. **Task 1: Create security.py and wire into app.py + login.html + requirements.txt** - `5bf5f38` (feat)

**Plan metadata:** TBD (docs: complete plan)

_Note: TDD task — stubs existed from Wave 0 (04-01); Wave 2 implementation makes them GREEN._

## Files Created/Modified
- `security.py` — New: limiter, csrf, _CSP constant, init_security(app); RATELIMIT_STORAGE_URI via app.config; /csp-report URI for report-only mode
- `app.py` — ProxyFix applied; from security import; init_security(app) after db.init_db(); @limiter.limit on login_post; @csrf.exempt on 13 /api/* POST routes; /csp-report endpoint; 429 error handler
- `templates/login.html` — csrf_token hidden input added inside login form
- `requirements.txt` — flask-limiter[redis]>=4.1.1, flask-wtf>=1.2.0, flask-talisman>=1.1.0 added
- `tests/test_security.py` — All 11 STUB bodies replaced with real assertions (T01-T10, T12)

## Decisions Made
- Flask-Limiter 4.x `storage_uri` is passed via `app.config["RATELIMIT_STORAGE_URI"]` before `limiter.init_app(app)`, not as an `init_app()` kwarg (API changed from 3.x docs)
- wntrblm flask-talisman requires `content_security_policy_report_uri` when `report_only=True` — added `/csp-report` no-op POST endpoint (returns 204, discards body)
- Flask-WTF 1.2.x `csrf.exempt()` registers views in `csrf._exempt_views` set by `"module.qualname"` string; T06 test updated to check this set directly instead of `_csrf_exempt` attribute
- T09 HSTS test simulates Railway-proxied HTTPS by setting `X-Forwarded-Proto: https` header — Talisman checks `request.is_secure OR X-Forwarded-Proto` for HSTS eligibility
- T03 ProxyFix test uses werkzeug EnvironBuilder + minimal capture WSGI app — Flask 3.x raises AssertionError if `before_request` is registered after first request handled
- CSP stays in report-only mode for Plan 02; enforcement mode (`content_security_policy_report_only=False`) is Plan 04-03's task after confirming zero browser console violations

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Flask-Limiter 4.x init_app() does not accept storage_uri kwarg**
- **Found during:** Task 1 (first test run after creating security.py)
- **Issue:** `TypeError: Limiter.init_app() got an unexpected keyword argument 'storage_uri'` — Flask-Limiter 4.x API changed; storage_uri must be set via `app.config["RATELIMIT_STORAGE_URI"]` before calling `init_app()`
- **Fix:** Changed `limiter.init_app(app, storage_uri=storage_uri)` to set `app.config["RATELIMIT_STORAGE_URI"] = storage_uri` then `limiter.init_app(app)`
- **Files modified:** security.py
- **Verification:** T01, T02 pass after fix
- **Committed in:** 5bf5f38 (Task 1 commit)

**2. [Rule 1 - Bug] wntrblm flask-talisman requires report_uri when report_only=True**
- **Found during:** Task 1 (second test run after first fix)
- **Issue:** `ValueError: Setting content_security_policy_report_only to True also requires a URI to be specified in content_security_policy_report_uri` — the wntrblm fork enforces this; Google fork does not
- **Fix:** Added `content_security_policy_report_uri="/csp-report"` to Talisman init; added `/csp-report` no-op POST endpoint (CSRF exempt, returns 204) to app.py
- **Files modified:** security.py, app.py
- **Verification:** Talisman initializes without error; T10 passes (CSP-Report-Only header present)
- **Committed in:** 5bf5f38 (Task 1 commit)

**3. [Rule 1 - Bug] Flask-WTF csrf.exempt() does not set _csrf_exempt attribute**
- **Found during:** Task 1 (T06 failure)
- **Issue:** `AssertionError: api_screen is missing @csrf.exempt decorator` — Flask-WTF 1.2.x `csrf.exempt()` adds view to `csrf._exempt_views` set (by `"module.qualname"` key), does NOT set `_csrf_exempt` attribute on the function
- **Fix:** Updated T06 test to check `csrf._exempt_views` set directly: `f"{view.__module__}.{view.__qualname__}" in csrf_instance._exempt_views`
- **Files modified:** tests/test_security.py
- **Verification:** T06 passes after fix
- **Committed in:** 5bf5f38 (Task 1 commit)

**4. [Rule 1 - Bug] Flask 3.x blocks before_request registration after first request**
- **Found during:** Task 1 (T03 failure)
- **Issue:** `AssertionError: The setup method 'before_request' can no longer be called on the application. It has already handled its first request` — T03 tried to register a before_request hook inside the test function, but T01/T02 had already processed requests on the same app instance
- **Fix:** Rewrote T03 to use werkzeug EnvironBuilder + minimal WSGI capture app to verify ProxyFix environ transformation directly, plus structural `isinstance(flask_app.wsgi_app, ProxyFix)` check
- **Files modified:** tests/test_security.py
- **Verification:** T03 passes after fix
- **Committed in:** 5bf5f38 (Task 1 commit)

**5. [Rule 1 - Bug] Talisman only adds HSTS for HTTPS requests**
- **Found during:** Task 1 (T09 failure)
- **Issue:** HSTS header absent from test responses — Talisman's `_set_hsts_headers` checks `request.is_secure OR X-Forwarded-Proto == 'https'`; plain HTTP test requests have neither
- **Fix:** Updated T09 to pass `headers={"X-Forwarded-Proto": "https"}`, simulating a Railway-proxied HTTPS request
- **Files modified:** tests/test_security.py
- **Verification:** T09 passes after fix
- **Committed in:** 5bf5f38 (Task 1 commit)

---

**Total deviations:** 5 auto-fixed (all Rule 1 — API/behavior differences between documented patterns and installed library versions)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. All discovered via TDD test failures — each fix made exactly the failing test pass without breaking others.

## Issues Encountered
- flask-limiter 4.x, flask-wtf 1.2.x, and wntrblm flask-talisman all had minor API differences from the plan's documented patterns (based on older docs or 3.x APIs). All resolved by inspecting installed library source code.
- Flask 3.x is stricter about app setup after first request — before_request hooks cannot be registered after request processing starts.

## User Setup Required
**Redis plugin required on Railway before deploying.** See checkpoint verification steps:
1. Railway Dashboard → Project → + New → Database → Add Redis
2. Confirm REDIS_URL appears in Variables tab
3. Deploy and verify 429 on 11th /login POST and security headers with curl

## Next Phase Readiness
- Wave 2 implementation complete — all 11 T01-T10/T12 tests pass
- Plan 04-03 can flip `content_security_policy_report_only=False` in security.py to enforce CSP
- T11 (manual browser CSP check) must be completed during checkpoint verification before Plan 04-03
- Redis plugin must be provisioned on Railway before deploying

---
*Phase: 04-security-hardening*
*Completed: 2026-03-09*

## Self-Check: PASSED

- security.py: FOUND
- app.py: FOUND
- templates/login.html: FOUND
- requirements.txt: FOUND
- tests/test_security.py: FOUND
- .planning/phases/04-security-hardening/04-02-SUMMARY.md: FOUND
- Commit 5bf5f38 (feat: add Flask-Limiter, CSRFProtect, Talisman): VERIFIED
