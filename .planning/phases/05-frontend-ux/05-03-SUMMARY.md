---
phase: 05-frontend-ux
plan: "03"
subsystem: ui
tags: [flask, javascript, csv, indicator-breakdown, shadow-fleet]

# Dependency graph
requires:
  - phase: 05-01
    provides: vessel profile page with score hero, vessel.js IIFE structure, indicator-section div placeholder
  - phase: 05-02
    provides: ranking table UI, map score popup, FE-1/FE-2/FE-3 tests green
provides:
  - INDICATOR_META constant in app.py with all 31 Shadow Fleet Framework indicators
  - renderIndicatorTable() in vessel.js — 31-row indicator breakdown with fired-first sort
  - GET /export/vessels.csv route with login_required and 9-column CSV output
  - FE-4 and FE-6 tests passing (all 6 Phase 5 FE tests green)
affects: [future phases using vessel profile, CSV export, indicator breakdown]

# Tech tracking
tech-stack:
  added: [csv (stdlib), io (stdlib), make_response (flask)]
  patterns:
    - INDICATOR_META module-level constant passed to templates via render_template
    - CSP-safe server-side JSON injection via <script type="application/json"> for indicator metadata
    - Fired indicator key-existence check (not .fired property) — missing key means not fired
    - risk_level derived from composite_score in CSV export (not stored in vessel_scores schema)

key-files:
  created: []
  modified:
    - app.py
    - static/vessel.js
    - templates/vessel.html
    - tests/test_fe.py

key-decisions:
  - "session_transaction() used for FE-4/FE-6 test auth — POST /login returns 302 even on success in test env (same pattern as FE-1/FE-3/FE-5)"
  - "evidence_count in CSV derived by counting indicator_json dict values where fired=True — consistent with indicator_json semantics (missing key = not fired)"
  - "INDICATOR_META placed as module-level constant before app = Flask(...) — passed to every vessel_profile render_template call including 404 path"

patterns-established:
  - "Indicator fired check: use key existence (hasOwnProperty) not .fired property — indicator_json only stores fired indicators"
  - "Placeholder stubs for unimplemented indicators use category '—' and max_pts 0"

requirements-completed: [FE-4, FE-6]

# Metrics
duration: 4min
completed: 2026-03-09
---

# Phase 05 Plan 03: Indicator Breakdown and CSV Export Summary

**31-row indicator breakdown table in vessel.js with fired-first sort + GET /export/vessels.csv with 9-column CSV and login gate**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-09T00:08:02Z
- **Completed:** 2026-03-09T00:11:53Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- INDICATOR_META constant with all 31 Shadow Fleet Framework indicators (12 implemented + 19 named stubs) added to app.py
- renderIndicatorTable() in vessel.js renders a sortable breakdown: fired indicators float to top with light-red background (#fef2f2), not-fired show em dash and greyed text
- GET /export/vessels.csv route with @login_required delivers CSV with correct 9-column header (vessel_name, imo, mmsi, flag, composite_score, risk_level, evidence_count, computed_at, is_stale)
- All 6 Phase 5 tests green; full suite 151 tests green with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add INDICATOR_META and /export/vessels.csv route** - `3b48c04` (feat)
2. **Task 2: Add renderIndicatorTable() and indicator-meta element** - `3e8a52b` (feat)
3. **Task 3: Implement test_indicator_json and test_csv_export** - `ba3e9d4` (feat)

**Plan metadata:** (docs commit follows)

_Note: Task 3 is TDD GREEN phase — stubs replaced with real assertions._

## Files Created/Modified
- `app.py` - Added INDICATOR_META constant (31 entries), updated vessel_profile() to pass indicator_meta, added /export/vessels.csv route with csv/io stdlib imports and make_response
- `static/vessel.js` - Added renderIndicatorTable() function (60 lines) and updated DOMContentLoaded handler to call it
- `templates/vessel.html` - Added `<script id="indicator-meta" type="application/json">` element before vessel-score-data
- `tests/test_fe.py` - Replaced pytest.fail() stubs with real test_indicator_json and test_csv_export implementations

## Decisions Made
- session_transaction() used for test auth in FE-4/FE-6 — consistent with FE-1/FE-3/FE-5 (POST /login returns 302 even on success in test env due to APP_PASSWORD env mismatch)
- evidence_count in CSV computed by counting indicator_json values where fired=True — aligns with indicator_json semantics where key existence indicates fired status
- INDICATOR_META passed to 404 path of vessel_profile() to prevent Jinja2 KeyError on template render

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test auth method in test_indicator_json and test_csv_export**
- **Found during:** Task 3 (TDD GREEN phase)
- **Issue:** Plan specified `app_client.post("/login", data={"password": "testpass"})` but this returns 302 even on success (known issue documented in STATE.md decisions for FE-5)
- **Fix:** Replaced POST /login with session_transaction() pattern, consistent with all other FE tests
- **Files modified:** tests/test_fe.py
- **Verification:** All 6 FE tests pass; 151 total tests green
- **Committed in:** ba3e9d4 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Required fix — POST /login never worked in test env for FE tests. session_transaction() is the established pattern for this project.

## Issues Encountered
None beyond the auth method fix above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 5 is now complete: all 6 FE tests (FE-1 through FE-6) pass green
- Vessel profile shows full 31-row indicator breakdown with fired-at timestamps
- CSV export available at /export/vessels.csv for analyst offline use
- No blockers for milestone v1.0 completion

---
*Phase: 05-frontend-ux*
*Completed: 2026-03-09*
