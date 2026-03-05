---
phase: 02-pre-computed-risk-scores
plan: "01"
subsystem: database
tags: [sqlite, postgres, vessel-scores, apscheduler, dual-backend, crud, ddl]

# Dependency graph
requires:
  - phase: 01-database-decomposition
    provides: db/ package with _conn, _cursor, _rows, _ph, _jp helpers and __init__.py re-export surface
provides:
  - vessel_scores table (imo_number PK, composite_score, is_sanctioned, indicator_json, computed_at, is_stale)
  - vessel_score_history table (id, imo_number, composite_score, is_sanctioned, computed_at — 90-day retention)
  - 8 public functions in db.scores re-exported from db/__init__.py
  - init_db() now creates scores tables on every app startup (idempotent)
  - apscheduler>=3.10,<4 in requirements.txt
affects: [02-02-scheduler, 02-03-staleness, 02-04-n1-elimination, 05-frontend-ux]

# Tech tracking
tech-stack:
  added: [apscheduler>=3.10,<4]
  patterns:
    - "Dual-backend DDL via _init_scores_postgres() / _init_scores_sqlite() helper split"
    - "ON CONFLICT (imo_number) DO UPDATE SET with is_stale=0 reset on every upsert"
    - "indicator_json normalisation: always check isinstance(str) and json.loads() on read"
    - "Local import in schema.py: from .scores import init_scores_tables avoids circular"

key-files:
  created:
    - db/scores.py
    - tests/test_scores.py
  modified:
    - db/__init__.py
    - db/schema.py
    - requirements.txt
    - tests/test_db_package.py

key-decisions:
  - "SCORE_STALENESS_MINUTES=30 and SCHEDULER_ADVISORY_LOCK_ID=42 are module-level constants in db/scores.py — no env var override"
  - "vessel_score_history stores only composite_score/is_sanctioned/computed_at (no indicator_json) to keep history table small"
  - "upsert_vessel_score always resets is_stale=0 in the ON CONFLICT SET clause — callers never need to clear stale explicitly"
  - "get_all_vessel_scores uses single JOIN (vessel_scores JOIN vessels_canonical LEFT JOIN ais_vessels) — no per-vessel loop"

patterns-established:
  - "Scores CRUD pattern: upsert normalises is_stale; reads normalise indicator_json to dict"
  - "Test isolation: tests use db._sqlite_path() (not tmp_path) since _sqlite_path is __file__-anchored; tests clean up per-IMO state before asserting counts"

requirements-completed: [DB-1, DB-2, DB-4, DB-5, INF-1, INF-2]

# Metrics
duration: 5min
completed: 2026-03-05
---

# Phase 2 Plan 01: vessel_scores DDL and CRUD storage layer Summary

**SQLite/PostgreSQL dual-backend score storage with 8 CRUD functions (upsert, get, get-all JOIN, mark-stale, history append/prune, AIS archive) wired into db/__init__.py and init_db()**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-05T12:56:10Z
- **Completed:** 2026-03-05T13:01:56Z
- **Tasks:** 3 (Task 0 RED, Task 1 implementation, Task 2 wiring)
- **Files modified:** 5

## Accomplishments
- vessel_scores and vessel_score_history tables created on every db.init_db() call (idempotent, both backends)
- Full CRUD layer: upsert/get/get-all/mark-stale/history-append/history-prune/ais-archive all implemented and tested
- All 8 functions re-exported from db/__init__.py; test_all_public_functions_exported passes
- apscheduler>=3.10,<4 added to requirements.txt (ready for 02-02 scheduler plan)
- 15 tests total passing (11 in test_scores.py, 4 in test_db_package.py)

## Task Commits

Each task was committed atomically:

1. **Task 0: Create test stubs (RED phase)** - `a06fcaf` (test)
2. **Task 1: Implement db/scores.py + requirements.txt** - `9c4c157` (feat)
3. **Task 2: Wire into __init__.py and schema.py + fix test paths** - `72ad826` (feat)

_Note: TDD task 0 established RED; tasks 1 and 2 together completed the GREEN phase._

## Files Created/Modified
- `db/scores.py` - Full scores CRUD: 8 public functions + 2 constants; dual-backend DDL and SQL
- `db/__init__.py` - Replaced commented placeholder with live scores re-export block
- `db/schema.py` - init_db() now calls init_scores_tables() after _migrate_vessels_canonical()
- `requirements.txt` - Added apscheduler>=3.10,<4
- `tests/test_scores.py` - 11 unit tests covering all 6 requirement IDs
- `tests/test_db_package.py` - PUBLIC_FUNCTIONS extended with 8 scores entries

## Decisions Made
- SCORE_STALENESS_MINUTES=30 and SCHEDULER_ADVISORY_LOCK_ID=42 are hardcoded constants per plan; no env override needed
- History table omits indicator_json to keep per-vessel history rows lightweight
- ON CONFLICT upsert pattern always resets is_stale=0; callers only need to call upsert — no separate clear-stale step

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test DB path resolution — use db._sqlite_path() not tmp_path**
- **Found during:** Task 0/RED verification
- **Issue:** Plan's test pattern used `monkeypatch.chdir(tmp_path)` and `tmp_path / "maritime_osint.db"`, but `db._sqlite_path()` is `__file__`-anchored to the project root — not cwd-relative. Tests connected to an empty tmp_path DB that had no tables.
- **Fix:** Removed `monkeypatch.chdir`; replaced `tmp_path / "maritime_osint.db"` with `db._sqlite_path()`; added per-test IMO cleanup so tests that check counts aren't polluted by other test runs on the shared project-root DB.
- **Files modified:** tests/test_scores.py
- **Verification:** All 11 test_scores.py tests pass
- **Committed in:** `72ad826` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test path assumption)
**Impact on plan:** Test path fix was necessary for correctness. No functional scope creep; all 8 functions implemented exactly as specified.

## Issues Encountered
- Windows WAL journal file holds lock when cwd-based SQLite approach is used with TemporaryDirectory — resolved by using project-root anchored path and per-test state cleanup.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 02-02 (APScheduler job) can import `db.upsert_vessel_score`, `db.mark_risk_scores_stale`, `db.SCHEDULER_ADVISORY_LOCK_ID` directly
- 02-03 (staleness screening) can use `db.get_vessel_score` to read `is_stale` and `computed_at`
- 02-04 (N+1 elimination) can replace per-vessel score calls with `db.get_all_vessel_scores()`
- No blockers

---
*Phase: 02-pre-computed-risk-scores*
*Completed: 2026-03-05*

## Self-Check: PASSED

- db/scores.py: FOUND
- tests/test_scores.py: FOUND
- 02-01-SUMMARY.md: FOUND
- Commit a06fcaf (RED tests): FOUND
- Commit 9c4c157 (db/scores.py implementation): FOUND
- Commit 72ad826 (wiring + test fix): FOUND
- pytest tests/test_scores.py tests/test_db_package.py: 15 passed
