---
phase: 06-score-history-infrastructure
plan: "01"
subsystem: database
tags: [sqlite, postgres, flask, scoring, history]

# Dependency graph
requires:
  - phase: 06-00-score-history-infrastructure
    provides: "test stubs for HIST-01 and HIST-02 (4 failing pytest.fail stubs)"
provides:
  - vessel_score_history schema with risk_level TEXT and indicator_json columns
  - append_score_history() storing all 5 required fields with internal risk_level derivation
  - get_score_history(imo, limit=30) newest-first read function
  - _score_changed() change-detection helper in app.py
  - _do_score_refresh() only appends history when score has changed (HIST-01)
  - GET /api/vessels/<imo>/history endpoint (HIST-02) returning recorded_at alias
affects: [07-alerts, 08-profile-enrichments]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Risk level derivation from composite_score/is_sanctioned thresholds in append_score_history() — never passed as input"
    - "SQLite migration via PRAGMA table_info; Postgres migration via ADD COLUMN IF NOT EXISTS"
    - "History route registered before <path:imo> catch-all to prevent Flask shadowing"
    - "computed_at stored in DB, exposed as recorded_at in API responses"

key-files:
  created: []
  modified:
    - db/scores.py
    - db/__init__.py
    - app.py
    - tests/test_hist.py

key-decisions:
  - "append_score_history() derives risk_level internally (not from caller) — backward-compatible with test_scores.py"
  - "change-detection lives in _do_score_refresh() via _score_changed(), not inside append_score_history() — keeps append as unconditional write primitive"
  - "GET /api/vessels/<imo>/history registered before <path:imo> catch-all to prevent shadowing"
  - "API renames computed_at → recorded_at for clarity for downstream consumers (alerts, trend chart)"

patterns-established:
  - "SQLite column migration: PRAGMA table_info guard before ALTER TABLE ADD COLUMN"
  - "Postgres column migration: ADD COLUMN IF NOT EXISTS (idempotent)"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-03-10
---

# Phase 6 Plan 01: Score History Infrastructure (GREEN) Summary

**vessel_score_history schema migrated to include risk_level and indicator_json, with change-detection in the scheduler and a new GET /api/vessels/<imo>/history Flask route — all 4 HIST-01/HIST-02 acceptance tests pass**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-10T15:42:52Z
- **Completed:** 2026-03-10T15:46:24Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Updated `vessel_score_history` DDL (both postgres and sqlite) with `risk_level TEXT` and `indicator_json` columns plus idempotent migration ALTERs for pre-existing tables
- Updated `append_score_history()` to derive risk_level internally from thresholds and store indicator_json — backward-compatible with all existing callers
- Added `get_score_history(imo, limit=30)` read function with indicator_json normalisation; re-exported from `db/__init__.py`
- Added `_score_changed()` helper and updated `_do_score_refresh()` to only write history rows when composite_score, is_sanctioned, or indicator_json has changed
- Added `GET /api/vessels/<imo>/history` route (registered before `<path:imo>` catch-all); returns 200 with `recorded_at` alias or 404 for unknown IMO
- All 4 acceptance tests pass (HIST-01: test_history_row_written, test_no_spurious_row; HIST-02: test_history_endpoint, test_history_endpoint_404); full suite 155 tests, 0 regressions

## Task Commits

Each task was committed atomically:

1. **Task 6-01-01: Schema migration + update DDL + update append_score_history()** - `681a7f2` (feat)
2. **Task 6-01-02: Add get_score_history() + re-export + change-detection** - `8426a62` (feat)
3. **Task 6-01-03: Implement stubs + add /api/vessels/<imo>/history Flask route** - `b1f6464` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `db/scores.py` - Updated DDL, migration blocks, updated append_score_history(), added get_score_history()
- `db/__init__.py` - Added get_score_history to re-export list
- `app.py` - Added _score_changed() helper, updated _do_score_refresh() with change-detection, added api_vessel_history route
- `tests/test_hist.py` - Replaced 4 pytest.fail("stub") bodies with real assertions

## Decisions Made

None beyond what was specified in the plan — followed implementation details exactly as written.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 6 Plan 01 complete — HIST-01 and HIST-02 requirements satisfied
- Phase 7 (alerts) can now begin: alert generation depends on comparing prior history snapshots to detect score changes; history table is populated and queryable
- Phase 8 (profile enrichments) PROF-01 trend chart can now use the history endpoint
- All history rows contain: composite_score, risk_level, is_sanctioned, indicator_json, computed_at

---
*Phase: 06-score-history-infrastructure*
*Completed: 2026-03-10*
