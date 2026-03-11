---
phase: 08-vessel-profile-enrichments
plan: "01"
subsystem: ui
tags: [chart.js, vessel-profile, history, javascript, css]

# Dependency graph
requires:
  - phase: 08-00
    provides: four PROF test stubs (RED phase)
  - phase: 06-score-history
    provides: vessel_score_history table and /api/vessels/<imo>/history endpoint

provides:
  - Score History card in vessel profile with Chart.js line chart (PROF-01)
  - Recent Changes card showing score delta, risk level change, fired/cleared indicators (PROF-02)
  - initHistorySection() JS function fetching and rendering history data
  - History card CSS classes (history-log, history-row, history-label, etc.)

affects: [phase-09-watchlist, phase-10-visual-legibility]

# Tech tracking
tech-stack:
  added: [chart.js@4.4.4 via cdn.jsdelivr.net CDN]
  patterns:
    - Chart.js loaded via CDN (no defer) before vessel.js DOMContentLoaded
    - Server-side data consumed client-side via fetch() to authenticated API endpoint
    - RISK_COLOR map used for per-point dot color coding on Chart.js line chart
    - Identical-snapshot detection via delta==0, same risk_level, same indicator key order

key-files:
  created: []
  modified:
    - templates/vessel.html
    - static/vessel.js
    - static/style.css
    - tests/test_profile_enrichments.py

key-decisions:
  - "Chart.js loaded via CDN without defer so it is available before vessel.js DOMContentLoaded fires"
  - "initHistorySection() silently degrades on fetch error — shows 'Unable to load history' message"
  - "Identical-snapshot detection: delta===0 and same risk_level and same indicator key order (not full deep-equal)"
  - "Test stubs replaced with API-level tests that validate /api/vessels/<imo>/history JSON shape"

patterns-established:
  - "Phase 8 CSS appended directly to static/style.css following Phase 7 pattern"
  - "History cards placed between score-hero and indicator-section in vessel.html else branch"

requirements-completed: [PROF-01, PROF-02]

# Metrics
duration: 12min
completed: 2026-03-11
---

# Phase 8 Plan 01: Vessel Profile Enrichments Summary

**Chart.js score trend line chart and Recent Changes log added to vessel profile page, consuming /api/vessels/<imo>/history endpoint, with all 4 PROF tests GREEN**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-11T17:40:35Z
- **Completed:** 2026-03-11T17:52:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Score History card with Chart.js 4.4.4 line chart: y-axis 0-100, per-point risk-level dot colors (CRITICAL red, HIGH orange, MEDIUM amber, LOW green), relative-time x-axis labels
- Recent Changes card: score delta with direction arrow, risk level transition (if changed), newly fired indicator names, newly cleared indicator names
- Edge cases handled: 0 snapshots show placeholder text, 1 snapshot shows "No prior snapshot to compare", identical snapshots show "No changes since last run"
- All 4 PROF tests pass GREEN; full 167-test suite passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add history card HTML to vessel.html and Chart.js CDN script tag** - `fb5e91a` (feat)
2. **Task 2: Add initHistorySection() to vessel.js and history card CSS** - `369142a` (feat)

**Plan metadata:** (docs commit — see below)

_Note: TDD tasks — test stubs replaced with real implementations in same commits as implementation_

## Files Created/Modified
- `templates/vessel.html` - Added score-history-card, recent-changes-card divs; Chart.js CDN script tag before vessel.js
- `static/vessel.js` - Added RISK_COLOR map, renderScoreHistoryCard(), renderRecentChangesCard(), initHistorySection(); boot block calls initHistorySection()
- `static/style.css` - Appended Phase 8 history card CSS (.history-log, .history-row, .history-label, .history-value, .history-delta, .history-fired, .history-cleared)
- `tests/test_profile_enrichments.py` - Replaced all 4 pytest.fail stubs with real API-level acceptance tests

## Decisions Made
- Chart.js loaded via CDN (cdn.jsdelivr.net, already allowed in CSP) without `defer` — must be synchronously available before vessel.js DOMContentLoaded fires
- Test implementations test the `/api/vessels/<imo>/history` API endpoint shape (JSON structure, snapshot ordering, indicator_json contents) rather than DOM rendering — browser JS rendering not testable in Flask test client
- Identical-snapshot detection uses delta==0 + same risk_level + joined indicator key order comparison (per CONTEXT.md decision — full deep-equal not needed)
- `initHistorySection()` silently degrades on fetch failure, showing "Unable to load history" rather than breaking the rest of the page

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 8 complete: vessel profile page now shows score history trend and change log
- Phase 9 (Watchlist) and Phase 10 (Visual Legibility) are independent and ready to proceed

---
*Phase: 08-vessel-profile-enrichments*
*Completed: 2026-03-11*
