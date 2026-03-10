---
phase: 05-frontend-ux
plan: "00"
subsystem: testing

tags: [pytest, test-stubs, wave-0, frontend, nyquist]

# Dependency graph
requires:
  - phase: 04-security-hardening
    provides: app_client fixture (function scope) in conftest.py used by all stubs
provides:
  - tests/test_fe.py with 6 pytest.fail() stubs covering FE-1 through FE-6
  - Wave 0 RED baseline for plans 05-01, 05-02, 05-03 to reference in verify blocks
affects:
  - 05-01-PLAN.md (test_vessel_permalink)
  - 05-02-PLAN.md (test_ranking_sort, test_map_data_score, test_stale_flag)
  - 05-03-PLAN.md (test_indicator_json, test_csv_export)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave 0 / RED phase: stubs use pytest.fail() not NotImplementedError — produces FAILED (exit 1) not ERROR (exit 2)"
    - "All frontend tests use app_client fixture (function scope) — no sqlite_db needed, app_client handles DB setup"

key-files:
  created:
    - tests/test_fe.py
  modified: []

key-decisions:
  - "Phase 5 follows same Wave 0 stub pattern as Phase 4: pytest.fail() stubs for Nyquist compliance before implementation begins"
  - "app_client fixture (function scope) used for all 6 stubs — avoids sqlite_db dependency, function scope resets Flask-Limiter counters"

patterns-established:
  - "Wave 0 RED: all 6 FE test stubs exit with code 1 (FAILED), enabling plans 05-01/02/03 to verify GREEN transitions"

requirements-completed: [FE-1, FE-2, FE-3, FE-4, FE-5, FE-6]

# Metrics
duration: 1min
completed: 2026-03-09
---

# Phase 5 Plan 00: Frontend UX Test Scaffold Summary

**6 pytest.fail() stubs in tests/test_fe.py covering FE-1 through FE-6 as Wave 0 RED baseline for frontend implementation plans**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-03-09T20:36:42Z
- **Completed:** 2026-03-09T20:37:21Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created tests/test_fe.py with exactly 6 test stubs for FE-1 through FE-6
- All stubs use pytest.fail() producing FAILED (exit code 1), not ERROR (exit code 2)
- All stubs use the app_client fixture (function scope) from conftest.py
- pytest tests/test_fe.py reports "6 failed in 1.84s" with zero errors — Nyquist compliance satisfied

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tests/test_fe.py with 6 failing stubs** - `861ab42` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `tests/test_fe.py` - 6 pytest.fail() stubs: test_ranking_sort, test_map_data_score, test_stale_flag, test_indicator_json, test_vessel_permalink, test_csv_export

## Decisions Made
- Phase 5 follows the same Wave 0 stub pattern established in Phase 4: pytest.fail() stubs ensure FAILED (not ERROR) for clean exit code 1
- app_client fixture used for all stubs — consistent with Phase 4 pattern, avoids sqlite_db dependency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- tests/test_fe.py exists with all 6 named test functions that plans 05-01, 05-02, 05-03 reference in their verify blocks
- Ready to execute 05-01 (vessel permalink route), 05-02 (ranking API + map score), 05-03 (indicator breakdown + CSV export)

## Self-Check: PASSED

- FOUND: tests/test_fe.py
- FOUND: .planning/phases/05-frontend-ux/05-00-SUMMARY.md
- FOUND: commit 861ab42 (test(05-00): add Wave 0 RED stubs for FE-1 through FE-6)

---
*Phase: 05-frontend-ux*
*Completed: 2026-03-09*
