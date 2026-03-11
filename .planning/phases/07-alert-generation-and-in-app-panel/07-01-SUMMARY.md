---
phase: 07-alert-generation-and-in-app-panel
plan: "01"
subsystem: database
tags: [sqlite, postgresql, dual-backend, alerts, apscheduler, scoring]

# Dependency graph
requires:
  - phase: 06-score-history
    provides: vessel_score_history table with risk_level and indicator_json; get_score_history() used for delta computation in _generate_alerts()
  - phase: 07-00
    provides: test stubs in tests/test_alerts.py covering ALRT-01 through ALRT-08
provides:
  - db/alerts.py with init_alerts_table, insert_alert, get_alerts, get_unread_count, mark_alert_read
  - alerts table (dual-backend DDL: BIGSERIAL/TIMESTAMPTZ/JSONB for Postgres; AUTOINCREMENT/TEXT for SQLite)
  - _generate_alerts() in app.py evaluating ALRT-04 (risk_level_crossing), ALRT-06 (sanctions_match), ALRT-07 (score_spike)
  - Updated _do_score_refresh() with two-pass ALRT-05 top_50_entry detection
  - ALRT-04, ALRT-05, ALRT-06, ALRT-07 stub tests replaced with real passing assertions
affects:
  - 07-02-PLAN (API endpoints for GET /api/alerts, GET /api/alerts/unread-count, POST /api/alerts/<id>/read)
  - 07-03-PLAN (frontend panel consuming alert API)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-backend DDL: separate _init_postgres / _init_sqlite helpers per feature module (matching db/scores.py pattern)"
    - "Count queries use plain conn.cursor() (not _cursor()) so fetchone()[0] returns int on both backends"
    - "UPDATE rowcount check via plain conn.cursor() (not _cursor()) for mark_alert_read bool return"
    - "Lazy app import inside test functions (not module-level) prevents dotenv reload polluting test env"
    - "ALRT-05 two-pass: capture top_50_before from rows[:50] pre-loop; re-query post-loop for top_50_after"

key-files:
  created:
    - db/alerts.py
    - .planning/phases/07-alert-generation-and-in-app-panel/deferred-items.md
  modified:
    - db/schema.py
    - db/__init__.py
    - app.py
    - tests/test_alerts.py

key-decisions:
  - "lazy import: 'from app import _generate_alerts' moved inside test functions (not module-level) to prevent app.py's load_dotenv(override=True) from re-setting AISSTREAM_API_KEY during test collection"
  - "vessel_scores INSERT fixture: plan had wrong schema (no risk_level column on vessel_scores); corrected to omit risk_level (only vessel_score_history has it)"
  - "get_unread_count and mark_alert_read use plain conn.cursor() not _cursor() to ensure fetchone()[0] and rowcount work on both backends"

patterns-established:
  - "Alert module pattern: separate _init_{backend}() helpers, dedicated module file, local import in schema.py init_db()"
  - "Two-pass alert detection: capture pre-refresh set, mutate state (upsert loop), re-query post-refresh for diff"

requirements-completed:
  - ALRT-04
  - ALRT-05
  - ALRT-06
  - ALRT-07

# Metrics
duration: 9min
completed: 2026-03-11
---

# Phase 07 Plan 01: Backend alerts table, generation logic, scheduler hook Summary

**Dual-backend alerts table, 5 CRUD functions, _generate_alerts() for ALRT-04/06/07, two-pass ALRT-05 in scheduler, all 4 backend stubs passing**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-11T00:25:28Z
- **Completed:** 2026-03-11T00:34:00Z
- **Tasks:** 3
- **Files modified:** 5 (created: db/alerts.py; modified: db/schema.py, db/__init__.py, app.py, tests/test_alerts.py)

## Accomplishments
- Created `db/alerts.py` with dual-backend DDL (Postgres: BIGSERIAL/TIMESTAMPTZ/JSONB; SQLite: INTEGER AUTOINCREMENT/TEXT) and 5 CRUD functions following the exact `db/scores.py` pattern
- Wired `init_alerts_table()` into `db/schema.py`'s `init_db()` and re-exported all 5 functions from `db/__init__.py`
- Added `_generate_alerts()` to `app.py` covering ALRT-04 (risk level crossing), ALRT-06 (sanctions flip), ALRT-07 (score spike >= 15 pts)
- Updated `_do_score_refresh()` with two-pass ALRT-05: `top_50_before` captured from `rows[:50]` pre-loop; `top_50_after` from re-query post-loop; fires `top_50_entry` alerts for new entrants
- Replaced 4 stub tests (ALRT-04, ALRT-05, ALRT-06, ALRT-07) with real assertions; all 4 pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Create db/alerts.py with dual-backend DDL and 5 CRUD functions** - `b024e14` (feat)
2. **Task 2: Wire init_alerts_table into db/schema.py and db/__init__.py** - `984bd5d` (feat)
3. **Task 3: Add _generate_alerts() to app.py and update _do_score_refresh() with ALRT-05 two-pass** - `54f0f65` (feat)

## Files Created/Modified
- `db/alerts.py` - New file: alerts table DDL + init_alerts_table, insert_alert, get_alerts, get_unread_count, mark_alert_read
- `db/schema.py` - Added `from .alerts import init_alerts_table` + `init_alerts_table()` call at end of `init_db()`
- `db/__init__.py` - Added `# ── Alerts (Phase 7)` block re-exporting all 5 alert functions
- `app.py` - Added `_generate_alerts()` function; replaced `_do_score_refresh()` with two-pass ALRT-05 version
- `tests/test_alerts.py` - 4 stubs replaced with real assertions; lazy import pattern; import db at module level

## Decisions Made
- Lazy `from app import _generate_alerts` inside each test function body (not module-level) prevents app.py's `load_dotenv(override=True)` line 51 from re-setting `AISSTREAM_API_KEY` during test collection, which would break `test_conftest_guards.py::test_aisstream_key_cleared`
- `get_unread_count()` and `mark_alert_read()` use `conn.cursor()` (not `_cursor()`) for plain tuple rows so `fetchone()[0]` and `rowcount` work identically on both backends

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect vessel_scores schema in test_top_50_entry_alert fixture**
- **Found during:** Task 3 (Add _generate_alerts() to app.py)
- **Issue:** Plan's test fixture included `risk_level` in the `vessel_scores` INSERT column list, but `vessel_scores` table has no `risk_level` column (it exists only on `vessel_score_history`). SQLite raised `OperationalError: table vessel_scores has no column named risk_level`.
- **Fix:** Removed `risk_level` from the INSERT statement; adjusted params tuple accordingly.
- **Files modified:** tests/test_alerts.py
- **Verification:** `test_top_50_entry_alert` passes after fix; verified `vessel_scores` schema in db/scores.py has no risk_level column
- **Committed in:** `54f0f65` (Task 3 commit)

**2. [Rule 1 - Bug] Fixed module-level `from app import _generate_alerts` causing dotenv env pollution**
- **Found during:** Task 3 (full suite regression check)
- **Issue:** Plan specified `from app import _generate_alerts` at module level in test_alerts.py. During test collection, importing `app` triggered `load_dotenv(override=True)` at app.py line 51, which re-set `AISSTREAM_API_KEY` from `.env` — causing `test_conftest_guards.py::test_aisstream_key_cleared` to fail. Confirmed pre-existing with original stubs but plan's code would still cause it.
- **Fix:** Moved `from app import _generate_alerts` inside each test function body as a lazy import. The module-level `import db` is safe (db package doesn't load dotenv).
- **Files modified:** tests/test_alerts.py
- **Verification:** 4 ALRT tests still pass; confirmed pre-existing conftest guard failure pattern (pre-existing issue documented in deferred-items.md, out of scope)
- **Committed in:** `54f0f65` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both required for test correctness. No scope creep.

## Issues Encountered
- Pre-existing conftest guard failure: `test_database_url_cleared` and `test_aisstream_key_cleared` fail when `test_alerts.py` is included in the full suite. Root cause: `app_client` fixture in any test_alerts.py test causes `app.py` load_dotenv(override=True) to run, re-setting env vars. This was already happening with the original stubs from Plan 07-00. Documented in `.planning/phases/07-alert-generation-and-in-app-panel/deferred-items.md`.

## Next Phase Readiness
- All backend infrastructure ready for Plan 07-02 (API endpoints: GET /api/alerts, GET /api/alerts/unread-count, POST /api/alerts/<id>/read)
- 4 remaining stubs (ALRT-01 through ALRT-03, ALRT-08) will be addressed in Plan 07-02
- No blockers

---
*Phase: 07-alert-generation-and-in-app-panel*
*Completed: 2026-03-11*
