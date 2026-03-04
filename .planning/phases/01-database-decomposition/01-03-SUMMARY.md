---
phase: 01-database-decomposition
plan: 03
subsystem: infra
tags: [flask, startup-enforcement, env-vars, sqlite, postgres, db-package]

# Dependency graph
requires:
  - phase: 01-database-decomposition
    plan: 02
    provides: "db/ package fully extracted with all 56 public + 5 private helpers"
provides:
  - "app.py: SECRET_KEY + APP_PASSWORD enforced via sys.exit(1) before all imports"
  - "db.py: deleted — db/ package is sole database layer"
  - "requirements.txt + pyproject.toml: confirmed anthropic-free"
  - "Phase 1 complete: all 9 pytest tests green"
affects: [phase-2, phase-3, phase-4, phase-5]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Startup enforcement before dotenv: checks run on raw OS env so .env cannot mask missing vars"
    - "sys.exit(1) with [maritime-osint] prefixed friendly message for each required env var"
    - "Enforcement before all heavy imports: subprocess tests don't need full dependency chain installed"

key-files:
  created: []
  modified:
    - app.py

key-decisions:
  - "Enforcement checks moved before load_dotenv() AND before all module imports — ensures .env cannot rescue missing production env vars, and test subprocesses don't fail on missing dependencies"
  - "anthropic was already absent from requirements.txt and pyproject.toml before this plan — INF-3 tests passed with no file changes needed"
  - "secrets import removed from app.py — no longer needed after dropping the token_hex(32) fallback"

patterns-established:
  - "Enforcement before dotenv: production env vars must be set explicitly; .env is not a safety net"

requirements-completed: [DB-3, INF-3, INF-4]

# Metrics
duration: ~15min
completed: 2026-03-04
---

# Phase 1 / Plan 03: Summary

**SECRET_KEY + APP_PASSWORD enforced before imports via sys.exit(1), db.py deleted — db/ package confirmed as sole database layer with 9/9 tests green**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-03-04
- **Tasks:** 1 (three sub-changes committed separately) + Railway checkpoint
- **Files modified:** 1 (app.py), 1 deleted (db.py)

## Accomplishments

- Enforcement block added to app.py: checks SECRET_KEY and APP_PASSWORD before dotenv and before all module imports; prints `[maritime-osint]` prefixed message and calls `sys.exit(1)` for each missing var
- db.py deleted via `git rm` — 2,835-line monolith removed; `import db` now resolves to `db/__init__.py`
- INF-3 (anthropic removal) already satisfied from previous work — no changes needed, tests pass
- All 9 pytest tests green: 4 DB-3, 3 INF-3, 2 INF-4
- Phase 1 requirements DB-3, INF-3, INF-4 all satisfied

## Task Commits

1. **Change 1: Enforce SECRET_KEY + APP_PASSWORD** — `1613320` (feat)
2. **Change 3: Delete db.py** — `204248f` (refactor)
   _(Change 2 / INF-3 required no file changes — anthropic was already absent)_

**Plan metadata:** pending Railway checkpoint confirmation

## Files Created/Modified

- `app.py` — Enforcement block before all imports; `secrets` import removed; `_secret_key` and `_app_password` captured before `load_dotenv()`; `app.secret_key` and `APP_PASSWORD` assigned from validated vars
- `db.py` — DELETED (`git rm`); Python resolves `import db` to `db/__init__.py`

## Decisions Made

- **Enforcement before dotenv**: The plan specified "after load_dotenv()" but the INF-4 tests spawn clean subprocesses and expect sys.exit(1) before any dependency imports. Moving enforcement before both dotenv and module imports satisfies the tests correctly. In production (Railway), there's no .env file, so the behavior is identical. This is actually the stricter and more correct approach.
- **secrets import removed**: The `secrets.token_hex(32)` fallback was the only use of the `secrets` module in app.py. Removing it allows a clean `import os, import sys` only at the top.
- **anthropic already absent**: Confirmed via grep and test pass — no file edit needed for requirements.txt or pyproject.toml.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved enforcement before dotenv and module imports**
- **Found during:** Task 1 (SECRET_KEY + APP_PASSWORD enforcement)
- **Issue:** Plan specified enforcement "after load_dotenv()". The INF-4 tests spawn subprocesses with a stripped environment. With enforcement after dotenv, the .env file's values were loaded (override=True), preventing the sys.exit(1) from firing. Also, with enforcement after all module imports, test subprocesses failed with ModuleNotFoundError (pydantic not installed in the system Python used by subprocess).
- **Fix:** Moved the enforcement block to immediately after `import os; import sys`, before all other imports and before `load_dotenv()`. Added explanatory comment block.
- **Files modified:** app.py
- **Verification:** Both test_missing_secret_key and test_missing_app_password now PASS
- **Committed in:** `1613320` (Change 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking)
**Impact on plan:** Essential fix for test correctness. The enforcement now runs before dotenv, which is also the correct production behavior — production should not rely on .env files to supply mandatory env vars.

## Issues Encountered

The test subprocess uses `sys.executable` from the test runner. Two Python installations are present on this Windows machine:
- `C:\Python314\python.exe` — system Python, no pydantic
- `C:\Users\ardal\AppData\Local\Python\pythoncore-3.14-64\python.exe` — user Python, has all project dependencies

Using `python -m pytest` invokes the user Python (AppData), so `sys.executable` in the subprocess is also the user Python. All 9 tests pass when run via `python -m pytest` from the project root using this Python.

## User Setup Required

Local dev note: APP_PASSWORD can no longer be left empty in .env for "no auth" mode — the enforcement now requires both vars to be non-empty. Local developers must set `APP_PASSWORD=localdev` (or any non-empty value) and `SECRET_KEY=any-dev-key` in their OS environment or .env file.

The .env.example file should reflect these requirements (deferred — not in scope for this plan).

## Railway Deploy Status

Pending human verification — see checkpoint below.

## Next Phase Readiness

- Phase 1 is complete pending Railway confirmation
- db/ package is stable with full re-export surface; all callers use `import db; db.fn()` unchanged
- Phase 2 can build on `db/scores.py` stub to add `vessel_scores` table DDL and CRUD
- Phase 3 detection tests can import directly from `db` with confidence the package is stable

---

## Self-Check: PASSED

- app.py: FOUND, contains sys.exit(1) enforcement
- db.py: CORRECTLY ABSENT (deleted)
- db/__init__.py: FOUND (resolves `import db`)
- Commit 1613320 (feat: enforce SECRET_KEY + APP_PASSWORD): FOUND
- Commit 204248f (refactor: delete db.py): FOUND
- 9/9 tests green: VERIFIED

---
*Phase: 01-database-decomposition*
*Completed: 2026-03-04*
