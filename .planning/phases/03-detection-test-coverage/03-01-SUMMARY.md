---
phase: 03-detection-test-coverage
plan: "01"
subsystem: testing
tags: [pytest, pydantic, pytest-cov, ais, conftest, fixtures, tdd]

# Dependency graph
requires:
  - phase: 01-database-decomposition
    provides: db package with _init_backend/init_db/_sqlite_path API
  - phase: 02-pre-computed-risk-scores
    provides: vessel_scores table, screening.py with score_is_stale()

provides:
  - tests/conftest.py with force-cleared DATABASE_URL and AISSTREAM_API_KEY guards
  - tests/ais_factory.py with make_gap/make_position_sequence/make_sts_pair/make_consecutive_pair
  - tests/test_conftest_guards.py T01-T02 self-tests for env guard correctness
  - tests/test_ais_factory.py T03-T06 self-tests for factory function shape correctness
  - pytest-cov installed and declared in requirements.txt

affects:
  - 03-02-PLAN.md (dark_periods, STS detection boundary tests — use ais_factory)
  - 03-03-PLAN.md (loitering, spoofing boundary tests + coverage gate — uses ais_factory + pytest-cov)

# Tech tracking
tech-stack:
  added:
    - pydantic>=2.0.0 (was transitive dep of anthropic, now declared explicitly in main section)
    - pytest-cov>=4.0 (new — coverage gate for plan 03-03)
  patterns:
    - TDD red-green: write failing test files first, then implement production code
    - conftest.py module-level env guards using os.environ["KEY"] = "" (not setdefault) for CI safety
    - ais_factory.py plain functions (not pytest fixtures) with explicit dict shapes per detection module
    - Phase 3 DB-touching tests use IMO7000001+ to avoid collision with Phase 2 test data

key-files:
  created:
    - tests/ais_factory.py
    - tests/test_conftest_guards.py
    - tests/test_ais_factory.py
  modified:
    - tests/conftest.py
    - requirements.txt

key-decisions:
  - "conftest.py upgraded from setdefault to direct assignment os.environ[\"DATABASE_URL\"] = \"\" to force-clear even when CI exports DATABASE_URL=postgresql://..."
  - "AISSTREAM_API_KEY removed via os.environ.pop() to prevent live WebSocket connections during CI test runs"
  - "ais_factory.py uses plain functions not pytest fixtures — boundary tests need parametrize-friendly callables with custom args"
  - "sqlite_db fixture scope=session to match Phase 2 pattern and avoid repeated DB init overhead"

patterns-established:
  - "Pattern 1: conftest.py force-clear pattern — os.environ[\"KEY\"] = \"\" before any db import"
  - "Pattern 2: ais_factory import pattern — sys.path.insert + from ais_factory import for tests/ directory"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-03-05
---

# Phase 3 Plan 01: Detection Test Infrastructure Summary

**pytest conftest.py hardened with CI-safe env guards, ais_factory.py created with 4 AIS data shape generators enabling boundary tests for dark periods, STS, loitering, and spoofing detection modules**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-05T13:47:44Z
- **Completed:** 2026-03-05T13:50:39Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Upgraded conftest.py from `setdefault` (broken in CI) to direct `os.environ["DATABASE_URL"] = ""` assignment plus `pop("AISSTREAM_API_KEY", None)` — prevents live DB/WebSocket connections in CI
- Created ais_factory.py with 4 factory functions producing correctly-shaped dicts consumed by dark_periods, loitering, sts_detection, and spoofing detection modules
- Added pytest-cov>=4.0 to requirements.txt; installed pydantic>=2.0.0 (was missing from runtime) — fixes 2 previously failing test_scores.py tests
- All 26 tests pass (was 24 passing + 2 failing due to missing pydantic)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies and update requirements.txt** - `75663e8` (chore)
2. **Task 2 RED: Add failing tests for conftest guards and ais_factory** - `a94e48f` (test)
3. **Task 2 GREEN: Harden conftest.py and create ais_factory.py** - `48effde` (feat)

## Files Created/Modified

- `requirements.txt` - Added pytest-cov>=4.0 to dev/test section (pydantic already in main section)
- `tests/conftest.py` - Upgraded env guards: setdefault -> direct assignment; added AISSTREAM_API_KEY pop; added session-scoped sqlite_db fixture
- `tests/ais_factory.py` - 4 factory functions: make_gap, make_position_sequence, make_sts_pair, make_consecutive_pair
- `tests/test_conftest_guards.py` - T01 (DATABASE_URL cleared) and T02 (AISSTREAM_API_KEY absent) self-tests
- `tests/test_ais_factory.py` - T03-T06 self-tests verifying factory function output shapes

## Decisions Made

- `os.environ["DATABASE_URL"] = ""` (not `setdefault`) — `setdefault` is a no-op when CI already sets `DATABASE_URL=postgresql://...`; direct assignment forces override every time conftest.py loads
- `ais_factory.py` uses plain functions not pytest fixtures — boundary tests in 03-02/03-03 need to call factories with custom parameters (e.g., `make_gap(gap_hours=25)`) which isn't possible with fixtures without additional parametrize complexity
- `scope="session"` for `sqlite_db` fixture — consistent with Phase 2 test pattern; avoids re-running DB init for every test function

## Deviations from Plan

None - plan executed exactly as written. pydantic was already in requirements.txt main section (not the dev/test section as the plan described), but was not installed in the runtime environment. Task 1 installed it and added pytest-cov to the dev/test section.

## Issues Encountered

None — all steps executed cleanly. The 2 previously failing pydantic tests (test_score_is_stale_age, test_score_is_stale_flag) now pass after pydantic installation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 03-02 and 03-03 can now proceed: ais_factory.py provides the data shapes they need
- pytest-cov is available for the coverage gate in 03-03
- All 26 existing tests pass — no regressions introduced
- Phase 3 DB-touching tests should use IMO7000001+ MMSI/IMO ranges per sqlite_db fixture docstring

---
*Phase: 03-detection-test-coverage*
*Completed: 2026-03-05*

## Self-Check: PASSED

- FOUND: tests/conftest.py
- FOUND: tests/ais_factory.py
- FOUND: tests/test_conftest_guards.py
- FOUND: tests/test_ais_factory.py
- FOUND: .planning/phases/03-detection-test-coverage/03-01-SUMMARY.md
- FOUND: commit 75663e8 (Task 1 - chore)
- FOUND: commit 48effde (Task 2 - feat)
