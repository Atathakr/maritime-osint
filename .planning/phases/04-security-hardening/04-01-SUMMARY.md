---
phase: 04-security-hardening
plan: 01
subsystem: testing
tags: [pytest, flask, security, rate-limiting, csrf, talisman, tdd]

# Dependency graph
requires:
  - phase: 03-detection-test-coverage
    provides: conftest.py test infrastructure, sqlite_db fixture, 134 passing tests
provides:
  - 11 failing test stubs (T01-T12, T11 excluded) for SEC-1 through SEC-4 requirements
  - app_client fixture in conftest.py for Flask security testing
  - Test contract for security.py implementation in Wave 2
affects: [04-02-PLAN.md, 04-03-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns: [TDD Wave 0 stub pattern — stubs fail with pytest.fail() STUB messages, not collection errors]

key-files:
  created: [tests/test_security.py]
  modified: [tests/conftest.py]

key-decisions:
  - "app_client fixture uses function scope (not session) so Flask-Limiter counters reset between T01/T02 rate-limit tests"
  - "WTF_CSRF_ENABLED=False in app_client allows isolated CSRF path testing in T04 via a separate client instance"
  - "Stubs use pytest.fail() not raise NotImplementedError — pytest.fail() is a proper FAILED not ERROR, giving clean exit code 1"
  - "apscheduler was in requirements.txt but not installed in venv — installed all requirements as Rule 3 fix during Task 1"

patterns-established:
  - "Wave 0 TDD: all stubs in test_security.py use pytest.fail('STUB — description (T0N)') pattern"
  - "Security tests grouped by requirement: SEC-1 rate-limit, SEC-2 CSRF, SEC-3 headers, SEC-4 template audit"

requirements-completed: [SEC-1, SEC-2, SEC-3, SEC-4]

# Metrics
duration: 2min
completed: 2026-03-09
---

# Phase 4 Plan 01: Security Hardening Test Stubs Summary

**11 pytest stubs covering rate limiting, CSRF protection, security headers, and template audit — all failing with STUB messages, ready for Wave 2 implementation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-09T14:39:44Z
- **Completed:** 2026-03-09T14:41:48Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added app_client fixture to tests/conftest.py (function-scoped Flask test client with SECRET_KEY/APP_PASSWORD pre-set)
- Created tests/test_security.py with 11 test stubs covering T01-T12 (T11 manual-only, excluded)
- All 11 stubs fail cleanly with descriptive STUB messages (exit code 1 not 2 — failures not errors)
- All 134 existing tests continue to pass after conftest.py modification

## Task Commits

Each task was committed atomically:

1. **Task 0: Add app_client fixture** - `28408de` (feat)
2. **Task 1: Write failing test stubs T01-T12** - `d25486f` (test)

**Plan metadata:** TBD (docs: complete plan)

_Note: TDD tasks may have multiple commits (test -> feat -> refactor). This is Wave 0 (stubs only)._

## Files Created/Modified
- `tests/test_security.py` — 11 failing test stubs for SEC-1 through SEC-4 security requirements
- `tests/conftest.py` — app_client fixture appended after sqlite_db fixture

## Decisions Made
- app_client uses function scope so Flask-Limiter counters don't bleed between T01 (allowed) and T02 (blocked) rate-limit tests
- WTF_CSRF_ENABLED=False in app_client fixture enables isolated CSRF testing in T04
- pytest.fail() chosen over NotImplementedError — produces FAILED not ERROR, giving clean exit code 1
- apscheduler missing from venv despite being in requirements.txt — installed all requirements (Rule 3 fix, blocking import)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed apscheduler and other missing packages**
- **Found during:** Task 1 (first pytest run)
- **Issue:** `ModuleNotFoundError: No module named 'apscheduler'` — app.py imports it at module level; conftest imports app.py via app_client fixture
- **Fix:** Ran `python -m pip install -r requirements.txt` to install all declared requirements
- **Files modified:** None (environment only)
- **Verification:** Subsequent pytest run collected all 11 stubs cleanly
- **Committed in:** d25486f (Task 1 commit, no file change needed)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary environment fix. No scope creep.

## Issues Encountered
- apscheduler not installed in local venv despite being in requirements.txt. Fixed by running full requirements install. Common issue when venv is recreated without installing dev dependencies.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 1 stubs complete — all 11 test IDs (T01-T12 minus T11) have named test functions
- Wave 2 (04-02) can implement security.py, apply decorators, and run `pytest tests/test_security.py` against real code to turn RED -> GREEN
- No blockers for Wave 2

---
*Phase: 04-security-hardening*
*Completed: 2026-03-09*
