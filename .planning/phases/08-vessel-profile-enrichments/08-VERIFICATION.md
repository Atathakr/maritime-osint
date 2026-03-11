---
phase: 08-vessel-profile-enrichments
verified: 2026-03-11T18:10:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 8: Vessel Profile Enrichments Verification Report

**Phase Goal:** Surface the vessel's score trajectory and recent changes directly on the profile page, so an analyst arriving via a "View Vessel" link from an alert can immediately see what changed and why without querying the history API manually.
**Verified:** 2026-03-11T18:10:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Vessel profile page shows a Score History card with a Chart.js trend chart | VERIFIED | `id="score-history-card"` present in vessel.html; Chart.js CDN script tag at line 102; `renderScoreHistoryCard()` in vessel.js calls `new Chart(canvas, ...)` |
| 2 | Vessel profile page shows a Recent Changes card with score delta, risk level change if any, and fired/cleared indicator names | VERIFIED | `id="recent-changes-card"` present in vessel.html; `renderRecentChangesCard()` in vessel.js builds delta row, risk-level row (if changed), newly-fired row, newly-cleared row |
| 3 | A vessel with 0 snapshots shows placeholder text in both cards (cards are visible, not hidden) | VERIFIED | `renderScoreHistoryCard` shows `score-history-placeholder` when history is empty; `renderRecentChangesCard` renders "No changes recorded yet." — cards are never hidden by JS |
| 4 | A vessel with exactly 1 snapshot shows a single-point chart and "No prior snapshot to compare" in Recent Changes | VERIFIED | `renderRecentChangesCard` branches at `history.length === 1` and renders "No prior snapshot to compare — this is the first recorded score." |
| 5 | Identical consecutive snapshots show "No changes since last run" in Recent Changes | VERIFIED | Identical-snapshot guard in `renderRecentChangesCard` at vessel.js line 253; `test_change_log_identical_snapshots` passes green |
| 6 | All 4 PROF tests pass green | VERIFIED | `python -m pytest tests/test_profile_enrichments.py -v` → 4 passed; full suite 167 passed, 0 failed |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `templates/vessel.html` | Score History and Recent Changes card scaffolds + Chart.js CDN script tag | VERIFIED | Contains `id="score-history-card"` (line 63), `id="recent-changes-card"` (line 74), Chart.js CDN tag (line 102), `<canvas id="score-history-chart">` (line 69) |
| `static/vessel.js` | `initHistorySection()` fetching `/api/vessels/<imo>/history` and rendering both cards | VERIFIED | `initHistorySection()` at line 295; `fetch('/api/vessels/' + encodeURIComponent(imo) + '/history')` at line 311; calls `renderScoreHistoryCard` and `renderRecentChangesCard`; called from DOMContentLoaded boot block |
| `static/style.css` | CSS for history and change log cards | VERIFIED | Phase 8 CSS block appended at line 209; classes `.history-log`, `.history-row`, `.history-label`, `.history-value`, `.history-delta`, `.history-fired`, `.history-cleared` all present |
| `tests/test_profile_enrichments.py` | Real acceptance tests for PROF-01 and PROF-02 (stubs replaced) | VERIFIED | Stubs replaced with API-level tests; 4 tests pass green |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `static/vessel.js` | `/api/vessels/<imo>/history` | `fetch()` in `initHistorySection()` | WIRED | `fetch('/api/vessels/' + encodeURIComponent(imo) + '/history')` at vessel.js line 311; response consumed via `.then(data => ...)` calling both render functions |
| `static/vessel.js` | `Chart` (Chart.js CDN) | `new Chart(canvas, config)` in `renderScoreHistoryCard()` | WIRED | `new Chart(canvas, {...})` at vessel.js line 184; CDN loaded synchronously (no defer) before vessel.js in vessel.html |
| `static/vessel.js` | `#indicator-meta` | `JSON.parse(metaEl.textContent)` at startup | WIRED | `document.getElementById('indicator-meta')` at vessel.js line 299; parsed to build `indicatorNameMap` passed to `renderRecentChangesCard` |
| `app.py` route | `db.get_score_history()` | `GET /api/vessels/<imo>/history` at app.py line 580 | WIRED | Route calls `db.get_score_history(imo, limit=30)` at line 596; result serialized and returned as `{"history": [...]}` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROF-01 | 08-00-PLAN.md, 08-01-PLAN.md | Vessel profile shows a score trend chart displaying the vessel's composite score over the last 30 snapshots, with timestamps on the x-axis | SATISFIED | Chart.js line chart in `renderScoreHistoryCard()`; x-axis uses `relativeTime(row.recorded_at)` labels; y-axis 0-100; `test_profile_has_history_card` and `test_history_single_snapshot` both pass |
| PROF-02 | 08-00-PLAN.md, 08-01-PLAN.md | Vessel profile shows a change log summarizing score delta, risk level change if any, and names of indicators that newly fired or newly cleared since prior snapshot | SATISFIED | `renderRecentChangesCard()` computes delta, risk change, fired/cleared indicator names; `test_change_log_diff` and `test_change_log_identical_snapshots` both pass |

No orphaned requirements: REQUIREMENTS.md traceability table maps PROF-01 and PROF-02 to Phase 8 only. Both claimed by plans 08-00 and 08-01. Both verified.

---

### Anti-Patterns Found

No blockers or stubs detected.

| File | Pattern | Severity | Verdict |
|------|---------|----------|---------|
| `static/vessel.js` | References to "placeholder" (DOM element `score-history-placeholder`) | Info | Legitimate — references the no-history UI element, not a code stub |
| `templates/vessel.html` | Comment "Indicator breakdown placeholder" | Info | Pre-existing comment from Phase 5; refers to indicator section populated in prior phase, not Phase 8 work |

---

### Human Verification Required

The following behaviors are implemented in client-side JavaScript and cannot be verified via Flask test client. Automated tests cover the API contract; visual rendering requires a browser.

#### 1. Score History Chart Rendering

**Test:** Load `/vessel/<imo>` for a vessel with 10+ history snapshots in a browser.
**Expected:** A Chart.js line chart appears in the Score History card with dots color-coded by risk level (red=CRITICAL, orange=HIGH, amber=MEDIUM, green=LOW) and relative-time labels on the x-axis (e.g. "3h ago", "1d ago").
**Why human:** Chart.js rendering requires a real browser; jsdom cannot execute Chart.js canvas drawing.

#### 2. Recent Changes Card — Full Diff Display

**Test:** Load `/vessel/<imo>` for a vessel whose most recent snapshot differs from the prior snapshot in score, risk level, and indicators.
**Expected:** The Recent Changes card shows: score delta with direction arrow (e.g. "▲ +12 pts"), a risk level transition line (e.g. "MEDIUM → HIGH"), newly fired indicator names in red, newly cleared indicator names in green.
**Why human:** DOM content rendered by `renderRecentChangesCard()` after `fetch()` response; not inspectable via Flask test client.

#### 3. Zero-Snapshot Edge Case Visual

**Test:** Load `/vessel/<imo>` for a vessel with no history snapshots.
**Expected:** Both cards are visible (not hidden); Score History card shows "No score history yet — snapshots are recorded when the score changes."; Recent Changes card shows "No changes recorded yet."
**Why human:** Card visibility and placeholder text display controlled by JS after async fetch; requires browser.

---

### Gaps Summary

No gaps. All 6 observable truths are verified. Both PROF requirements are satisfied. The full test suite of 167 tests passes with no regressions.

---

_Verified: 2026-03-11T18:10:00Z_
_Verifier: Claude (gsd-verifier)_
