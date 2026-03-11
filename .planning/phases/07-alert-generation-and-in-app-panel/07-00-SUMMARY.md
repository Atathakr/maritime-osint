---
phase: 07-alert-generation-and-in-app-panel
plan: "00"
subsystem: testing
tags: [pytest, tdd, stubs, alerts]

# Dependency graph
requires:
  - phase: 06-vessel-score-history
    provides: vessel_score_history table and append_score_history() used by alert generation
provides:
  - "8 pytest.fail('stub') stubs in tests/test_alerts.py matching ALRT-01 through ALRT-08"
  - "Exact test function names that Wave 1 verify commands reference"
  - "IMO9000001+ range reservation documented via stub docstrings"
affects: [07-01-wave-1-implementation, 07-02-wave-2-implementation]

# Tech tracking
tech-stack:
  added: []
  patterns: [TDD Wave 0 stub pattern — pytest.fail("stub") with no module-level imports beyond os and pytest]

key-files:
  created:
    - tests/test_alerts.py
  modified: []

key-decisions:
  - "Wave 0 stub pattern: pytest.fail('stub') in every test body, no imports beyond os and pytest at module level"
  - "IMO9000001+ range reserved for Phase 7 alert tests — avoids fixture collision with Phases 2-6"

patterns-established:
  - "Wave 0 stub: bare pytest.fail('stub') with no helper code — Wave 1 replaces full function body without merge conflicts"

requirements-completed: [ALRT-01, ALRT-02, ALRT-03, ALRT-04, ALRT-05, ALRT-06, ALRT-07, ALRT-08]

# Metrics
duration: 5min
completed: 2026-03-10
---

# Phase 7 Plan 00: Test Stubs (RED) Summary

**8 pytest.fail("stub") stubs for ALRT-01 through ALRT-08 added to tests/test_alerts.py — all collected as FAILED with zero errors**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-10T00:00:00Z
- **Completed:** 2026-03-10T00:05:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created `tests/test_alerts.py` with 8 stub test functions whose names exactly match the Wave 1 verify commands
- Confirmed `pytest tests/test_alerts.py -q` produces `8 failed` with zero collection errors
- IMO9000001+ range reserved for Phase 7 fixtures via stub docstrings

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tests/test_alerts.py with 8 failing stubs** - `c5870dc` (test)

**Plan metadata:** (included in final commit)

## Files Created/Modified
- `tests/test_alerts.py` - 8 pytest.fail("stub") stubs for ALRT-01 through ALRT-08; no module-level imports beyond os and pytest

## Decisions Made
None - followed plan as specified. File written verbatim from plan template.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. The `app_client` fixture is resolved from the existing `tests/conftest.py` — stubs collected cleanly because app_client is a session fixture that initialises before any test body runs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 8 stub functions are in place with exact names required by Wave 1 verify commands
- Plan 07-01 (Wave 1 implementation) can proceed — it will replace stub bodies with real assertions and add the alerts table, _generate_alerts() function, and /api/alerts/* endpoints

---
*Phase: 07-alert-generation-and-in-app-panel*
*Completed: 2026-03-10*
