---
phase: 05-frontend-ux
plan: "01"
subsystem: ui
tags: [flask, jinja2, javascript, csp, vessel-profile, permalink]

# Dependency graph
requires:
  - phase: 05-00
    provides: Wave 0 test stubs (pytest.fail) for FE-1 through FE-6
  - phase: 02-pre-computed-risk-scores
    provides: db.get_vessel(), db.get_vessel_score(), is_stale flag, computed_at timestamp
  - phase: 04-security-hardening
    provides: CSP enforcement (script-src self + cdn.jsdelivr.net), login_required decorator
provides:
  - GET /vessel/<path:imo> Flask route registered before /api/vessels/<path:imo> catch-all
  - templates/vessel.html — full vessel profile page with score hero and freshness stamp
  - static/vessel.js — scoreToRiskLevel(), relativeTime(), renderScoreHero() client logic
  - test_vessel_permalink passes GREEN (FE-5 permalink + FE-3 freshness stamps)
affects:
  - 05-03 (indicator breakdown reads window._vesselScore set by vessel.js)
  - 05-03 (CSV export: /vessel/<imo> permalink links in ranking table)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "<script type='application/json'> for server-to-JS data injection (CSP safe — browser treats as data, not executable)"
    - "Vessel profile permalink registered BEFORE /api/vessels/<path:imo> catch-all to prevent Flask shadowing"
    - "session_transaction() in tests for auth — avoids APP_PASSWORD env mismatch when local .env overrides conftest setdefault"

key-files:
  created:
    - templates/vessel.html
    - static/vessel.js
    - .planning/phases/05-frontend-ux/05-01-SUMMARY.md
  modified:
    - app.py
    - tests/test_fe.py

key-decisions:
  - "Score data embedded server-side via <script type='application/json'> — avoids second API round-trip, CSP safe"
  - "test_vessel_permalink uses session_transaction() not form POST — APP_PASSWORD in .env overrides conftest setdefault causing POST login to fail locally"
  - "vessel.js exposes window._vesselScore for plan 05-03 indicator breakdown (forward-compatible hook)"

patterns-established:
  - "CSP-safe data injection: <script id='...' type='application/json'>{{ data | tojson }}</script> — no inline JS, data-attr for string values"
  - "Auth in tests: with app_client.session_transaction() as sess: sess['authenticated'] = True — bypass form POST"

requirements-completed: [FE-5, FE-3]

# Metrics
duration: 6min
completed: 2026-03-10
---

# Phase 5 Plan 01: Vessel Profile Permalink Summary

**Bookmarkable GET /vessel/<imo> page with Jinja2 score hero, freshness stamps, and stale badge via CSP-safe server-injected JSON pattern**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-10T00:18:00Z
- **Completed:** 2026-03-10T00:24:52Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Flask route `/vessel/<path:imo>` registered correctly before the `/api/vessels/<path:imo>` catch-all — no Flask shadowing
- `templates/vessel.html` renders score hero with `composite_score`, risk badge pill, and freshness stamp ("Computed Xh ago"); amber Stale marker when `is_stale=True`; "Score not computed" when `computed_at` is NULL
- `static/vessel.js` provides `scoreToRiskLevel()`, `relativeTime()`, `riskBadgeHtml()`, `renderScoreHero()` — reads server-injected JSON, no inline `<script>` (CSP enforced)
- `test_vessel_permalink` GREEN: unauthenticated redirects 302, unknown IMO returns 404 HTML (not JSON)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add GET /vessel/<imo> Flask route** - `7ee68f0` (feat)
2. **Task 2: Create templates/vessel.html and static/vessel.js** - `5aa487e` (feat)
3. **Task 3: Implement test_vessel_permalink (TDD GREEN)** - `80259f2` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `app.py` - Added `vessel_profile()` view registered before `/api/vessels/<path:imo>` catch-all
- `templates/vessel.html` - Full vessel profile page: header, score hero div, freshness div, indicator placeholder, CSP-safe data element
- `static/vessel.js` - Client logic: scoreToRiskLevel(), relativeTime(), riskBadgeHtml(), renderScoreHero(); exposes window._vesselScore for plan 05-03
- `tests/test_fe.py` - Replaced test_vessel_permalink stub with real assertions (GREEN)

## Decisions Made

- Score data embedded server-side via `<script type="application/json">{{ score | tojson }}</script>` — avoids a second `/api/vessels/<imo>` fetch and is CSP safe (browser treats `type="application/json"` as data, not executable script)
- `test_vessel_permalink` authenticates via `session_transaction()` not form POST — the local `.env` file sets `APP_PASSWORD=dev-password` which overrides the conftest `setdefault("APP_PASSWORD", "testpass")`, causing the POST login to return 200 (wrong password) instead of 302

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_vessel_permalink login approach fails locally due to .env override**

- **Found during:** Task 3 (implement test_vessel_permalink)
- **Issue:** Plan specified `app_client.post("/login", data={"password": "testpass"})` for authentication. Local `.env` has `APP_PASSWORD=dev-password` (not `testpass`). `load_dotenv(override=True)` in `app.py` overrides `conftest.setdefault("APP_PASSWORD", "testpass")`, so the POST login returns 200 (renders login page with wrong-password error) instead of 302 redirect. Post-login session has no `authenticated=True`.
- **Fix:** Changed test to use `with app_client.session_transaction() as sess: sess["authenticated"] = True` — directly sets session state without touching APP_PASSWORD
- **Files modified:** `tests/test_fe.py`
- **Verification:** `pytest tests/test_fe.py::test_vessel_permalink` passes GREEN
- **Committed in:** `80259f2` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test approach)
**Impact on plan:** Auth via session_transaction is the established pattern (same as other Phase 5 tests that were pre-implemented). No scope creep.

## Issues Encountered

The `<script type="application/json">` CSP-safe injection pattern is the correct approach — confirmed that `type="application/json"` blocks browser from executing the block as JavaScript. This is the same pattern used in major frameworks (Next.js `__NEXT_DATA__`, Django REST Framework browsable API).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `window._vesselScore` is exposed by `vessel.js` for plan 05-03 indicator breakdown rendering
- `#indicator-section` and `#indicator-table-container` divs are already in `vessel.html` (hidden, ready to populate)
- FE-5 permalink route is bookmarkable — ranking table in plan 05-02 should link rows to `/vessel/<imo>`
- Plan 05-02 (ranking table) and 05-03 (indicator breakdown + CSV) can proceed in sequence

## Self-Check: PASSED

- templates/vessel.html: FOUND
- static/vessel.js: FOUND
- .planning/phases/05-frontend-ux/05-01-SUMMARY.md: FOUND
- Commit 7ee68f0 (Task 1): FOUND
- Commit 5aa487e (Task 2): FOUND
- Commit 80259f2 (Task 3): FOUND

---
*Phase: 05-frontend-ux*
*Completed: 2026-03-10*
