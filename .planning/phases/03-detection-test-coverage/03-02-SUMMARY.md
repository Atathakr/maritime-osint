---
phase: 03-detection-test-coverage
plan: "02"
subsystem: testing
tags: [pytest, tdd, dark-periods, sts-detection, boundary-tests, pure-functions, coverage]

# Dependency graph
requires:
  - phase: 03-detection-test-coverage
    plan: "01"
    provides: tests/ais_factory.py with make_gap/make_sts_pair factories; pytest-cov installed; conftest.py hardened

provides:
  - dark_periods.detect(gaps: list) -> list pure function (no DB calls)
  - sts_detection.detect(candidates: list) -> list pure function (no DB calls)
  - dark_periods module-level constants: DARK_THRESHOLD_HOURS, HIGH_RISK_HOURS, CRITICAL_HOURS
  - sts_detection module-level constants: STS_DISTANCE_KM, MAX_SOG, DEDUP_HOURS
  - tests/test_dark_periods.py T07-T13 boundary tests (all pass)
  - tests/test_sts_detection.py T14-T19 boundary tests (all pass)

affects:
  - 03-03-PLAN.md (loitering, spoofing — same extract-detect()-then-test pattern)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TDD red-green: write failing test file first, then add detect() implementation
    - detect() pure extraction: wrap existing private helpers (_haversine, _classify_zone, _risk_level, _deduplicate); pass sanctions_hit=False explicitly
    - event_ts mapping: detect() sets event_ts from input "ts" key before calling _deduplicate()
    - Boundary test values: reference module constants +/- EPSILON; never hardcode thresholds
    - Open-ocean coords (0.0, 0.0) for MEDIUM baseline tests (avoids zone upgrade side-effect)

key-files:
  created:
    - tests/test_dark_periods.py
    - tests/test_sts_detection.py
  modified:
    - dark_periods.py
    - sts_detection.py

key-decisions:
  - "detect() added before run_detection() in both modules — keeps pure function near module-level constants"
  - "T09 (MEDIUM baseline) uses open-ocean coords (0.0, 0.0) not default Gulf of Oman coords — default last_lat=22.5 lon=57.0 is inside HIGH_RISK_ZONES causing zone upgrade to HIGH which would fail the MEDIUM assertion"
  - "INSIDE_DELTA/OUTSIDE_DELTA corrected from plan's erroneous 0.0000808/0.0000898 to 0.0083/0.0090 degrees — plan comment had decimal point error (0.9km / 111.32km_per_degree = 0.00808 not 0.0000808)"
  - "Coverage plateau at 60-65% is structural: run_detection() in both modules (~40 lines each) requires live DB connection; cannot be reached by pure-function tests without DB mocking (deferred to 03-03 if needed)"

patterns-established:
  - "Pattern 3: detect() extraction — add pure function before run_detection(); reuse private helpers; sanctions_hit=False; set event_ts from input ts key before dedup"
  - "Pattern 4: STS delta calculation — use 0.0083 degrees lat for INSIDE (~0.923 km) and 0.0090 degrees lat for OUTSIDE (~1.001 km) relative to 0.926 km threshold"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-03-05
---

# Phase 3 Plan 02: Detection Test Coverage (dark_periods + STS) Summary

**Pure detect() functions extracted from dark_periods.py and sts_detection.py; 23 boundary tests (T07-T19 plus extras) pass with 49 total tests green and no regressions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-05T18:12:29Z
- **Completed:** 2026-03-05T18:17:15Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Extracted `dark_periods.detect(gaps)` pure function using existing `_classify_zone`/`_haversine` helpers; promotes DARK_THRESHOLD_HOURS, HIGH_RISK_HOURS, CRITICAL_HOURS as module-level constants
- Extracted `sts_detection.detect(candidates)` pure function wrapping `_haversine`, `_classify_zone`, `_risk_level`, `_deduplicate`; maps input `ts` key to `event_ts` before deduplication
- 23 boundary tests pass (T07-T19 + 8 extra coverage tests); full suite 49 passed, 0 failed

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: T07-T13 failing tests for dark_periods** - `test commit` (test)
2. **Task 1 GREEN: dark_periods.detect() implementation + T09 coord fix** - `d32e237` (feat)
3. **Task 2 RED: T14-T19 failing tests for sts_detection** - `test commit` (test)
4. **Task 2 GREEN: sts_detection.detect() + corrected INSIDE/OUTSIDE_DELTA** - `6f5d004` (feat)
5. **Extra coverage tests for detect() branches and summarise()** - `cd1025d` (test)

_Note: TDD tasks have separate test (RED) and feat (GREEN) commits_

## Files Created/Modified

- `dark_periods.py` - Added `detect()` pure function before `run_detection()`; module-level constants already present
- `sts_detection.py` - Added `detect()` pure function before `run_detection()`; module-level constants already present; event_ts mapping for _deduplicate()
- `tests/test_dark_periods.py` - T07-T13 boundary tests + 4 extra coverage tests; references dark_periods.CONSTANT values
- `tests/test_sts_detection.py` - T14-T19 boundary tests + 5 extra coverage tests; corrected lat-degree delta calculation

## Decisions Made

- `detect()` placed before `run_detection()` in both modules — keeps the pure function near module-level constants for readability
- T09 MEDIUM baseline test uses open-ocean coords `(0.0, 0.0)` instead of the default `(22.5, 57.0)` from `make_gap()` — default coordinates are inside the Gulf of Oman zone which triggers zone upgrade MEDIUM→HIGH, falsely failing the MEDIUM assertion
- `INSIDE_DELTA = 0.0083` / `OUTSIDE_DELTA = 0.0090` degrees latitude — corrected from plan's erroneous comment values `(0.0000808/0.0000898)` which had a misplaced decimal point; actual calculation: 0.926 km ÷ 111.32 km/degree ≈ 0.00832 degrees
- `event_ts` is set from the input `"ts"` key inside `detect()` before calling `_deduplicate()` — `_deduplicate()` accesses `ev["event_ts"]` internally; omitting this mapping would cause a KeyError on deduplication

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed T09 test coordinates to prevent zone upgrade false failure**
- **Found during:** Task 1 GREEN (running tests after implementing detect())
- **Issue:** T09 asserts `risk_level == "MEDIUM"` but `make_gap()` defaults `last_lat=22.5, last_lon=57.0` which is inside Gulf of Oman HIGH_RISK_ZONES; zone upgrade makes it HIGH, causing T09 to fail
- **Fix:** Added `last_lat=0.0, last_lon=0.0` override in T09 test (open-ocean coordinates outside all zones)
- **Files modified:** tests/test_dark_periods.py
- **Verification:** T09 passes with MEDIUM risk level; T12 (zone upgrade test) still passes with Gulf of Oman coords
- **Committed in:** d32e237 (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Corrected INSIDE_DELTA/OUTSIDE_DELTA values in STS tests**
- **Found during:** Task 2 verification (computed actual distances from plan's delta values)
- **Issue:** Plan's comment stated delta for 1km = `1.0 / 111320 ≈ 0.0000898 degrees`; correct is `1.0 / 111.32 ≈ 0.008985 degrees` (off by factor of 1000); both INSIDE and OUTSIDE deltas were ~0.009 km, both inside the 0.926 km threshold, making T15 (outside threshold) impossible
- **Fix:** Used correct values `INSIDE_DELTA = 0.0083` (~0.923 km) and `OUTSIDE_DELTA = 0.0090` (~1.001 km) verified via haversine calculation
- **Files modified:** tests/test_sts_detection.py
- **Verification:** T15 (pair outside threshold not detected) and T16 (pair inside detected) both pass
- **Committed in:** 6f5d004 (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes were necessary for test correctness. T09 coord fix prevents geography side-effect from masking the threshold test. Delta fix corrects a decimal-point error in the plan. No scope creep.

## Coverage Note

Coverage for `dark_periods.py` and `sts_detection.py` reached ~60-65% (target was ≥80%). The gap is structural: `run_detection()` in both modules requires a live database connection and accounts for ~38% of each module's lines. These functions cannot be reached by pure-function tests without DB mocking (which is out of scope for this plan). The pure `detect()` functions, helper functions, `summarise()`, and `_deduplicate()` are well-covered. DB-mocked tests for `run_detection()` can be added in a future plan if needed.

## Issues Encountered

None — all steps executed cleanly after correcting the two bugs above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 03-03 (loitering + spoofing detect() extraction) can proceed using the same pattern established here
- Pattern 3 (detect() extraction) and Pattern 4 (STS delta calculation) documented above
- 49 tests passing, no regressions
- dark_periods.detect() and sts_detection.detect() available for 03-03 integration tests if needed

---
*Phase: 03-detection-test-coverage*
*Completed: 2026-03-05*

## Self-Check: PASSED

- FOUND: dark_periods.py
- FOUND: sts_detection.py
- FOUND: tests/test_dark_periods.py
- FOUND: tests/test_sts_detection.py
- FOUND: .planning/phases/03-detection-test-coverage/03-02-SUMMARY.md
- FOUND: commit d32e237 (Task 1 - feat: dark_periods.detect())
- FOUND: commit 6f5d004 (Task 2 - feat: sts_detection.detect())
- FOUND: commit cd1025d (extra coverage tests)
- 49 tests pass, 0 failed
