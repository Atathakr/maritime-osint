---
phase: 05-frontend-ux
plan: "02"
subsystem: frontend-ux
tags: [ranking-table, map-popup, composite-score, pagination, sort, filter, tdd]
dependency_graph:
  requires:
    - 05-00  # Wave 0 stubs
    - 02-01  # vessel_scores table + composite_score
    - 02-04  # /api/vessels/ranking endpoint
  provides:
    - FE-1   # Vessel risk ranking table with sort/filter/pagination
    - FE-2   # Map popup numeric score + View Profile link
    - FE-3   # is_stale propagation verified in ranking API
  affects:
    - templates/dashboard.html
    - static/ranking.js
    - static/css/ranking.css
    - static/style.css
    - static/map.js
    - db/vessels.py
    - map_data.py
    - tests/test_fe.py
tech_stack:
  added: []
  patterns:
    - Vanilla ES2020 IIFE module pattern for ranking.js (CSP-safe, no inline scripts)
    - session_transaction() for Flask test client auth (consistent with test_vessel_permalink)
    - LEFT JOIN vessel_scores to extend existing map query without restructuring
key_files:
  created:
    - static/ranking.js
    - static/css/ranking.css
  modified:
    - templates/dashboard.html
    - static/style.css
    - static/map.js
    - db/vessels.py
    - map_data.py
    - tests/test_fe.py
decisions:
  - "Used session_transaction() for test auth instead of POST /login — POST login returned 302 even after successful form submit in test client; session_transaction() directly sets session['authenticated'] = True, matching the pattern used in test_vessel_permalink"
  - "scoreLine inserted inside <table> as a <tr> row (not after table) — matches the map-popup-table structure"
  - "CSS unicode escapes (\\25b2, \\25bc) used for sort arrows in ranking.css — avoids encoding issues with triangle characters in CSS content property"
metrics:
  duration: "~5 minutes"
  completed_date: "2026-03-09"
  tasks_completed: 3
  files_modified: 8
---

# Phase 5 Plan 02: Vessel Ranking Table + Map Score Popup Summary

**One-liner:** Sortable 8-column risk ranking table with real-time filter and pagination, plus numeric composite score in map popups with View Profile anchor link.

## What Was Built

### Task 1 — Extend map data pipeline with composite_score (commit: 26ad802)

- `db/vessels.py get_map_vessels_raw()`: Added `LEFT JOIN vessel_scores vs ON vs.imo_number = av.imo_number` and `vs.composite_score AS composite_score` to the SELECT clause. Works for both SQLite and PostgreSQL backends.
- `map_data.py get_map_vessels()`: Added `"composite_score": r.get("composite_score")` to the results.append() block — passes through the LEFT JOIN result (int or None).
- `static/map.js popupHtml(v)`: Added null-guarded score line (`if (v.composite_score != null)`) as a table row; replaced the `openVesselProfile()` button with a direct `<a href="/vessel/${escAttr(v.imo_number)}">View Profile &rarr;</a>` anchor. Preserves right-click/open-in-new-tab behavior. Existing qualitative risk badge retained.

### Task 2 — Risk Ranking panel + ranking.js + ranking.css (commit: 08a437a)

- `templates/dashboard.html`: Added "Risk Ranking" tab button (between Intelligence and System tabs). Added full tab pane with filter bar (`id="ranking-filter"`), 8-column sortable table (`id="ranking-tbody"`), rows/page select (50/100/250), CSV export link, and pagination bar. Added `<script src="{{ url_for('static', filename='ranking.js') }}">` before `</body>`.
- `static/ranking.js`: Full IIFE implementation (~170 lines). Functions: `loadRankingTable()` (fetch `/api/vessels/ranking?limit=500`), `applyRankingFilter()` (real-time name/IMO filter), `sortRanking(thEl)` (toggle asc/desc, header arrow updates), `sortAndRenderRanking()` (null-safe sort), `renderRankingPage()` (pagination, stale indicator, risk badge), `goRankingPage()`, `setRankingPageSize()`. Lazy-loads data on first tab switch via `switchTab` hook.
- `static/css/ranking.css`: Styles for `.ranking-th` headers, sortable header arrows (`sort-asc`/`sort-desc`), `.ranking-row-*` risk-colored left borders, hover state.
- `static/style.css`: Added `@import "css/ranking.css"` at end of imports.

### Task 3 — TDD GREEN tests (commit: 5342dd4)

Replaced three `pytest.fail()` stubs in `tests/test_fe.py`:

- `test_ranking_sort`: Verifies 302 for unauthenticated, 200+`{"vessels":[...]}` when authenticated, score descending order for multiple vessels.
- `test_stale_flag`: Verifies `is_stale` field present in every row of the ranking API response.
- `test_map_data_score`: Verifies `map_data.get_map_vessels()` returns a list where every dict has a `composite_score` key (value may be None).

All three use `session_transaction()` for auth injection.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] POST /login not persisting session in app_client**

- **Found during:** Task 3 (TDD GREEN phase)
- **Issue:** `app_client.post("/login", data={"password": "testpass"}, follow_redirects=True)` returned 200 but subsequent requests to `/api/vessels/ranking` still returned 302. The Flask test client session was not persisting `session["authenticated"] = True` across calls when using form POST.
- **Fix:** Replaced POST login with `with app_client.session_transaction() as sess: sess["authenticated"] = True` — the same pattern used in `test_vessel_permalink` (which had already been updated by plan 05-01).
- **Files modified:** `tests/test_fe.py`
- **Commit:** 5342dd4

## Verification Results

All specified verifications passed:

```
tests/test_fe.py::test_ranking_sort PASSED
tests/test_fe.py::test_stale_flag PASSED
tests/test_fe.py::test_map_data_score PASSED
3 passed in 1.27s
```

- `python -c "import db; import map_data; print(map_data.get_map_vessels.__doc__)"` succeeds
- `db/vessels.py` contains `LEFT JOIN vessel_scores` (line 709)
- `static/ranking.js` exists with `applyRankingFilter` and `loadRankingTable` functions
- `static/css/ranking.css` exists with `.ranking-th` and `.ranking-row-*` classes
- `templates/dashboard.html` contains `id="ranking-filter"` and `id="ranking-tbody"`
- `static/style.css` imports `ranking.css`

## Self-Check: PASSED

Files verified:
- static/ranking.js: EXISTS
- static/css/ranking.css: EXISTS
- templates/dashboard.html: EXISTS (modified)
- db/vessels.py: EXISTS (contains LEFT JOIN vessel_scores at line 709)
- map_data.py: EXISTS (contains composite_score)
- static/map.js: EXISTS (contains composite_score null guard)

Commits verified:
- 26ad802: feat(05-02): extend map data pipeline with composite_score
- 08a437a: feat(05-02): build vessel risk ranking table UI
- 5342dd4: feat(05-02): implement GREEN tests for FE-1, FE-2, FE-3
