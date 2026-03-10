---
phase: 05-frontend-ux
verified: 2026-03-09T00:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 5: Frontend UX Verification Report

**Phase Goal:** Make the dashboard credible to maritime analysts — vessels ranked by risk score, numeric scores visible everywhere, indicator evidence showing why each vessel is flagged, freshness stamps on all data, and a vessel permalink plus CSV export.
**Verified:** 2026-03-09
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                       | Status     | Evidence                                                                                            |
|----|---------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------|
| 1  | Vessels are ranked by composite_score descending in /api/vessels/ranking                    | VERIFIED   | test_ranking_sort PASSED; ranking.js fetches /api/vessels/ranking?limit=500                        |
| 2  | Numeric score visible on ranking table, map popup, and vessel profile                       | VERIFIED   | ranking.js renders v.composite_score; map.js scoreLine conditional; vessel.js renderScoreHero()    |
| 3  | Freshness stamps ("Computed Xh ago") and stale marker on profile; is_stale in ranking API  | VERIFIED   | test_stale_flag PASSED; vessel.js relativeTime()+staleStr; ranking.js stale bullet                 |
| 4  | 31-row indicator breakdown on vessel profile with fired indicators at top                   | VERIFIED   | vessel.js renderIndicatorTable() exists and correct; INDICATOR_META has 31 entries                 |
| 5  | GET /vessel/<imo> returns bookmarkable HTML page, requires login, returns 404 for unknown   | VERIFIED   | test_vessel_permalink PASSED; /vessel/<path:imo> route registered before /api/vessels/<path:imo>   |
| 6  | GET /export/vessels.csv returns text/csv with 9-column header, requires login               | VERIFIED   | test_csv_export PASSED; export_vessels_csv() route registered and wired to db.get_all_vessel_scores |

**Score:** 6/6 truths verified

---

## Required Artifacts

| Artifact                    | Expected                                                          | Status     | Details                                                              |
|-----------------------------|-------------------------------------------------------------------|------------|----------------------------------------------------------------------|
| `tests/test_fe.py`          | 6 real tests covering FE-1 through FE-6                           | VERIFIED   | 6 substantive tests; all 6 PASSED in pytest run                     |
| `templates/vessel.html`     | Full vessel profile page — score hero, freshness, indicator div   | VERIFIED   | 84 lines; indicator-meta, vessel-score-data, vessel.js src all present; no inline scripts |
| `static/vessel.js`          | renderScoreHero(), relativeTime(), renderIndicatorTable()          | VERIFIED   | 159 lines; all three functions implemented; boot handler calls both render functions |
| `static/ranking.js`         | loadRankingTable(), applyRankingFilter(), sortRanking(); 100+ lines | VERIFIED  | 210 lines; all functions implemented; fetches /api/vessels/ranking  |
| `static/css/ranking.css`    | .ranking-th, .ranking-row-* classes                               | VERIFIED   | 26 lines; all required classes present                              |
| `templates/dashboard.html`  | Risk Ranking tab pane with ranking-filter, ranking-tbody          | VERIFIED   | Tab button at line 30; tab pane at line 297; ranking-filter and ranking-tbody present; ranking.js included |
| `db/vessels.py`             | get_map_vessels_raw() with LEFT JOIN vessel_scores                 | VERIFIED   | Line 709: `LEFT JOIN vessel_scores vs ON vs.imo_number = av.imo_number`; composite_score in SELECT (line 705) |
| `map_data.py`               | get_map_vessels() includes composite_score field                  | VERIFIED   | Line 141: `"composite_score": r.get("composite_score")`            |
| `static/map.js`             | popupHtml() shows score line and View Profile link                | VERIFIED   | Lines 113-125: scoreLine conditional; profileLink anchor; both included in returned HTML |
| `app.py`                    | INDICATOR_META (31 entries) + vessel_profile route + /export/vessels.csv route | VERIFIED | Lines 56-88: 31 entries confirmed by `python -c` output; routes at lines 387, 403 |
| `static/style.css`          | @import css/ranking.css                                           | VERIFIED   | Line 7: `@import "css/ranking.css";`                                |

---

## Key Link Verification

| From                                   | To                            | Via                                       | Status  | Details                                                              |
|----------------------------------------|-------------------------------|-------------------------------------------|---------|----------------------------------------------------------------------|
| `static/ranking.js` loadRankingTable() | `/api/vessels/ranking`        | fetch on DOMContentLoaded                 | WIRED   | Line 53: `fetch('/api/vessels/ranking?limit=500')`                  |
| `db/vessels.py` get_map_vessels_raw()  | `vessel_scores` table         | LEFT JOIN                                 | WIRED   | Line 709 confirmed present                                           |
| `map_data.py` get_map_vessels()        | `composite_score`             | r.get('composite_score')                  | WIRED   | Line 141 present                                                     |
| `static/map.js` popupHtml(v)           | `v.composite_score`           | conditional score line in HTML string     | WIRED   | Lines 113-114: null guard + interpolation                           |
| `app.py` vessel_profile()              | `templates/vessel.html`       | render_template with indicator_meta       | WIRED   | Lines 397-400: render_template("vessel.html", ..., indicator_meta=INDICATOR_META) |
| `templates/vessel.html`                | `static/vessel.js`            | `<script src>` tag via url_for            | WIRED   | Line 82: `<script src="{{ url_for('static', filename='vessel.js') }}">` |
| `static/vessel.js` DOMContentLoaded   | vessel-score-data element     | JSON.parse(scoreEl.textContent)           | WIRED   | Lines 150-157: reads, parses, calls renderScoreHero + renderIndicatorTable |
| `templates/vessel.html`                | `static/vessel.js` indicator-meta | `<script id='indicator-meta' type='application/json'>` | WIRED | Lines 72-75: INDICATOR_META injected as JSON data element |
| `static/vessel.js` renderIndicatorTable() | window._vesselScore.indicator_json | dict lookup per INDICATOR_META entry | WIRED | Line 96: `var indJson = (score && score.indicator_json) ? score.indicator_json : {}` |
| `app.py` export_vessels_csv()          | `db.get_all_vessel_scores()`  | batch JOIN query                          | WIRED   | Line 411: `rows = db.get_all_vessel_scores()`                       |
| `dashboard.html`                       | `static/ranking.js`           | `<script src>` tag                        | WIRED   | Line 587: `<script src="{{ url_for('static', filename='ranking.js') }}">` |

---

## Requirements Coverage

| Requirement | Source Plan | Description                                                    | Status    | Evidence                                                              |
|-------------|-------------|----------------------------------------------------------------|-----------|-----------------------------------------------------------------------|
| FE-1        | 05-00/02    | Vessel ranking table — sortable, paginated 50/100/250          | SATISFIED | ranking.js: sort, filter, pagination; dashboard.html: 8-col table; test_ranking_sort PASSED |
| FE-2        | 05-00/02    | Numeric score (0-99) everywhere — ranking, profile, map popup  | SATISFIED | map.js scoreLine; vessel.js renderScoreHero; ranking.js score column; test_map_data_score PASSED |
| FE-3        | 05-00/01/02 | Freshness stamps — "Xh ago", stale flag (>2h)                 | SATISFIED | vessel.js relativeTime()+staleStr; ranking.js stale bullet; test_stale_flag PASSED |
| FE-4        | 05-00/03    | Indicator point-contribution breakdown — 31 rows, greyed not-fired | SATISFIED | vessel.js renderIndicatorTable(); 31-entry INDICATOR_META; fired=top+red bg; not-fired=greyed |
| FE-5        | 05-00/01    | Vessel profile permalink GET /vessel/<imo>                     | SATISFIED | Route at app.py line 387; returns HTML 404 for unknown; test_vessel_permalink PASSED |
| FE-6        | 05-00/03    | CSV export from ranking table                                  | SATISFIED | Route at app.py line 403; 9-column header; login required; test_csv_export PASSED |

No orphaned requirements — all FE-1 through FE-6 are claimed across plans 05-00 through 05-03 and verified.

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None | — | — | — |

Scan results:
- No `TODO`, `FIXME`, `PLACEHOLDER` comments in any phase 5 files
- No `return null` / `return {}` / `return []` stub bodies in JS files
- No inline `<script>` blocks in `vessel.html` or `dashboard.html` (CSP compliant)
- No `pytest.fail()` stubs remaining — all 6 tests are fully implemented

---

## Human Verification Required

### 1. Risk Ranking Tab — Visual and Interactive Behavior

**Test:** Log in to the dashboard, click "Risk Ranking" tab. Verify the table loads vessels sorted by score descending. Click a column header to sort ascending/descending. Type in the filter bar to filter by vessel name or IMO.
**Expected:** Table re-renders in <500ms, sort arrows appear, filter narrows rows, pagination controls appear when >50 rows.
**Why human:** Sort/filter/pagination are client-side DOM operations that cannot be exercised by Flask test client (no JS execution).

### 2. Map Popup Score Display

**Test:** Click a vessel marker on the map. Verify the popup shows a "Score: N" row with a bold numeric value. Verify "View Profile" link navigates to /vessel/<imo>.
**Expected:** Score line appears when composite_score is not null; no "null" text when score is absent.
**Why human:** Map popup rendering requires a live browser with Leaflet JS.

### 3. Vessel Profile Page — Score Hero and Stale Badge

**Test:** Navigate to /vessel/<imo> for a vessel with a known stale score (computed_at > 2h ago). Verify the score hero shows the numeric score, risk badge, "Computed Xh ago" freshness text, and amber "Stale" bullet.
**Expected:** Score renders large (3rem), badge has correct risk color, stale marker is amber.
**Why human:** CSS rendering and relative-time display require a live browser.

### 4. Vessel Profile — Indicator Breakdown Table

**Test:** Navigate to /vessel/<imo> for a vessel with fired indicators. Verify the Indicator Breakdown section is visible, fired rows float to top with light-red (#fef2f2) background, not-fired rows are greyed out, 31 rows total, "Total Score" footer matches composite_score.
**Expected:** 31 rows present, fired indicators visually distinguished, total consistent.
**Why human:** Row ordering and background color require visual inspection; indicator_json content varies by live data.

### 5. CSV Export — File Download

**Test:** Click "Export CSV" button in the Risk Ranking tab. Verify the browser downloads `maritime-osint-vessels.csv` with 9 column headers and one row per scored vessel.
**Expected:** File downloads (not displayed inline), header row is correct, data rows are populated.
**Why human:** File download behavior (Content-Disposition attachment) requires a live browser.

---

## Gaps Summary

No gaps. All 6 FE requirements have substantive implementation, correct wiring, and passing tests. The full test suite (151 tests) passes with no regressions.

---

_Verified: 2026-03-09_
_Verifier: Claude (gsd-verifier)_
