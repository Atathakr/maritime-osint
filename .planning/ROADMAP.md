# Roadmap: maritime-osint

## Milestones

- ✅ **v1.0 Production Maturity Pass** - Phases 1-5 (shipped 2026-03-10)
- 🚧 **v1.1 Analyst Workflow** - Phases 6-10 (in progress)

## Phases

<details>
<summary>✅ v1.0 Production Maturity Pass (Phases 1-5) - SHIPPED 2026-03-10</summary>

### Phase 1: Database Decomposition
**Goal**: Replace the 2,835-line db.py monolith with a db/ package that all callers use identically, enforce SECRET_KEY from environment, and remove the unused Anthropic SDK — with zero observable behavior change.
**Depends on**: Nothing (first phase)
**Requirements**: DB-01, DB-02, DB-03, DB-04, DB-05, INF-03
**Success Criteria** (what must be TRUE):
  1. All existing callers (`import db; db.fn()`) work without modification after db.py is deleted.
  2. App fails with a clear error message at startup if SECRET_KEY is not set in the environment.
  3. The `anthropic` package is absent from requirements.txt and the app starts without import errors.
  4. All sub-modules in db/ import backend helpers only from db/connection.py — no sub-module duplicates placeholder logic.
  5. A fresh deploy to Railway behaves identically to the pre-split deployment (no new 500 errors on any route).
**Plans**: 3 plans

Plans:
- [x] 01-01: Audit all db.fn() call sites; create db/ skeleton with __init__.py re-exporting everything from connection.py; delete db.py only after re-export inventory is verified
- [x] 01-02: Extract schema.py, vessels.py, sanctions.py, ais.py, detection.py incrementally; update __init__.py re-exports after each extraction; add scores.py stub
- [x] 01-03: Enforce SECRET_KEY via os.environ["SECRET_KEY"]; remove anthropic from requirements.txt; smoke-test on Railway

### Phase 2: Pre-Computed Risk Scores
**Goal**: Store composite risk scores and indicator breakdowns in a vessel_scores table, refresh them every 15 minutes via APScheduler, eliminate N+1 query patterns in the dashboard, and archive stale AIS positions daily — so all analyst-facing features have fast, fresh data to read from.
**Depends on**: Phase 1
**Requirements**: INF-01, INF-02
**Success Criteria** (what must be TRUE):
  1. The vessel ranking dashboard endpoint returns in under 500ms for any fleet size (no per-vessel SELECT loops).
  2. vessel_scores contains composite_score, is_sanctioned, indicator_json (JSONB), and computed_at for every vessel; scores are no older than 15 minutes in steady state.
  3. A newly-ingested OFAC sanction causes the affected vessel's score to be marked stale and recomputed before the next dashboard load.
  4. AIS positions older than 90 days are removed by a daily archival job; Railway storage growth is bounded.
**Plans**: 4 plans

Plans:
- [x] 02-01: Create vessel_scores table in db/scores.py; add init_db() DDL; create score read/upsert/mark-stale functions
- [x] 02-02: Wire APScheduler in app.py (refresh_all_scores every 15 min; archive_old_positions daily); handle Gunicorn multi-worker double-refresh
- [x] 02-03: Add staleness fallback in screening.py (recompute on demand if score >30 min old); add mark_risk_scores_stale() to all ingest functions
- [x] 02-04: Eliminate N+1 query patterns in dashboard and vessel ranking endpoints; replace per-vessel SELECT loops with batch queries

### Phase 3: Detection Test Coverage
**Goal**: Give every detection module a pure detect(positions) function that is testable without a database, and a pytest suite that validates threshold boundary logic with synthetic AIS fixtures — so Phase 4 security changes have a regression safety net.
**Depends on**: Phase 1
**Requirements**: INF-02
**Success Criteria** (what must be TRUE):
  1. Each of the 5 detection modules exposes a pure detect(positions) function with no database calls.
  2. Running `pytest tests/` with no DATABASE_URL set completes successfully.
  3. Each detection module has at least one boundary test at threshold - epsilon (must NOT trigger) and one at threshold + epsilon (must trigger).
  4. 151 tests pass, all green.
**Plans**: 3 plans

Plans:
- [x] 03-01: Create tests/ structure; write conftest.py with DATABASE_URL guards; write ais_factory.py position sequence generators
- [x] 03-02: Extract detect(positions) from dark_periods.py and sts_detection.py; write boundary tests
- [x] 03-03: Extract detect(positions) from loitering.py, spoofing.py, and screening.py; write boundary tests

### Phase 4: Security Hardening
**Goal**: Add rate limiting on login (with correct Railway proxy handling), CSRF protection on the login form only, and security headers (CSP audited and enforced) — and formally dismiss the 7 CodeQL false positives.
**Depends on**: Phase 1, Phase 3
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05
**Success Criteria** (what must be TRUE):
  1. The /login endpoint returns 429 after 10 POST attempts per minute from a single IP; the limit counter persists across Railway deploys and Gunicorn worker restarts (stored in Redis).
  2. All /api/* POST endpoints continue to accept requests without CSRF tokens; only /login requires CSRF validation.
  3. Browser DevTools shows HSTS, X-Frame-Options: DENY, and X-Content-Type-Options: nosniff headers on every response.
  4. Dashboard renders correctly with CSP enforcement enabled (no browser console CSP violations).
  5. All 7 py/sql-injection CodeQL alerts show "Dismissed" status with false positive rationale.
**Plans**: 3 plans

Plans:
- [x] 04-01: Test stubs (T01-T12) + app_client fixture; all stubs fail (RED phase)
- [x] 04-02: security.py (Flask-Limiter Redis, CSRFProtect, Talisman report-only) + app.py wiring + login.html csrf_token; Railway deploy checkpoint
- [x] 04-03: Flip CSP to enforcement; dismiss 7 CodeQL py/sql-injection alerts via gh CLI

### Phase 5: Frontend UX
**Goal**: Make the dashboard credible to maritime analysts — vessels ranked by risk score, numeric scores visible everywhere, indicator evidence showing why each vessel is flagged, freshness stamps on all data, and a vessel permalink plus CSV export.
**Depends on**: Phase 2
**Requirements**: FE-01, FE-02, FE-03, FE-04, FE-05, FE-06
**Success Criteria** (what must be TRUE):
  1. An analyst opening the dashboard immediately sees vessels sorted by composite score (descending); the table is paginated (50/100/250 rows) and loads in under 500ms.
  2. Risk scores appear as integers (0-99) alongside the risk label everywhere: ranking table, vessel profile header, and map popup.
  3. Every vessel profile shows "AIS last seen: Xh ago", "Sanctions screened: X days ago", and "Risk score: computed X min ago"; scores older than 2 hours are visually flagged as stale.
  4. The vessel profile indicator breakdown table lists all 31 indicators with points awarded and detection timestamp; fired indicators are highlighted.
  5. Navigating to /vessel/<imo> loads the full vessel profile; the URL is stable and bookmarkable.
  6. The "Export CSV" button downloads the current view as a CSV with columns: IMO, Name, Flag, Score, Level, Sanctions, Last AIS, Score Computed At.
**Plans**: 4 plans

Plans:
- [x] 05-01: Add GET /vessel/<imo> permalink route; update vessel profile template to show risk score as integer, freshness stamps, and stale-score visual flag
- [x] 05-02: Build vessel ranking table — sortable columns, pagination (50/100/250), risk-colored rows, numeric scores, <500ms using vessel_scores index
- [x] 05-03: Add indicator point-contribution breakdown to vessel profile (reads indicator_json JSONB from vessel_scores); wire CSV export from ranking table

</details>

---

### 🚧 v1.1 Analyst Workflow (In Progress)

**Milestone Goal:** Minimize platform dwell time — analysts get notified when something changes, land on a clear explanation of what changed, and navigate to any vessel's full context in one click.

#### Phase 6: Score History Infrastructure
**Goal**: Record a score snapshot every time the APScheduler job runs and a vessel's score has changed, and expose the last 30 snapshots per vessel via API — providing the data foundation that alert generation and profile enrichments both require.
**Depends on**: Phase 5 (v1.0 complete)
**Requirements**: HIST-01, HIST-02
**Success Criteria** (what must be TRUE):
  1. After two consecutive scheduler runs where a vessel's score changes, the vessel_score_history table contains one new row per changed score per run, with composite_score, risk_level, is_sanctioned, indicator_json, and recorded_at populated.
  2. Vessels whose score did not change between runs produce no new history rows (no spurious snapshots).
  3. A GET request to `/api/vessels/<imo>/history` returns up to 30 snapshots in reverse chronological order as JSON; vessels with fewer than 30 changes return only what exists.
  4. The history endpoint returns a 404 for an unknown IMO and an empty list (not an error) for a valid vessel with no history yet.
**Plans**: 2 plans

Plans:
- [ ] 06-00: Wave 0 — Create tests/test_hist.py with 4 failing stubs (HIST-01, HIST-02)
- [ ] 06-01: Wave 1 — Schema migration (add risk_level + indicator_json), update append_score_history(), add get_score_history(), change-detection in scheduler, add GET /api/vessels/<imo>/history route

#### Phase 7: Alert Generation and In-App Panel
**Goal**: Generate alerts automatically during the scheduler job when defined conditions are met, and give the analyst a visible notification badge and drill-down panel to review and dismiss alerts without leaving the dashboard.
**Depends on**: Phase 6 (history rows required for before/after comparisons)
**Requirements**: ALRT-01, ALRT-02, ALRT-03, ALRT-04, ALRT-05, ALRT-06, ALRT-07, ALRT-08
**Success Criteria** (what must be TRUE):
  1. After a scheduler run that produces a risk level crossing, a top-50 entry, a new sanctions match, or a 15+ point delta, the alerts table gains one new row per triggered condition per vessel; no duplicate alerts are generated for the same event in the same run.
  2. The dashboard header shows a red badge with the unread alert count immediately after alert generation; the badge is hidden when no unread alerts exist.
  3. The analyst can open the alert panel and see each unread alert listed with: vessel name, alert type label, score at trigger time, and time elapsed since the alert fired.
  4. Clicking any alert in the panel opens a detail view showing: before and after composite score, before and after risk level, list of indicator names that newly fired, and a "View Vessel" link to the vessel profile.
  5. Clicking "Mark as read" on an individual alert decrements the badge count by one; the alert moves to a "read" section and remains visible there.
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

#### Phase 8: Vessel Profile Enrichments
**Goal**: Surface the vessel's score trajectory and recent changes directly on the profile page, so an analyst arriving via a "View Vessel" link from an alert can immediately see what changed and why without querying the history API manually.
**Depends on**: Phase 6 (history snapshots required for chart and change log)
**Requirements**: PROF-01, PROF-02
**Success Criteria** (what must be TRUE):
  1. The vessel profile page shows a score trend chart (Chart.js via CDN) plotting composite score on the y-axis against snapshot timestamp on the x-axis for the last 30 snapshots; the chart renders without an npm build pipeline.
  2. A vessel with only one history snapshot shows a single-point chart rather than an error.
  3. The vessel profile page shows a change log entry for the most recent scheduler run that produced a snapshot: score delta with direction arrow (e.g. "▲ +12 pts"), risk level change if any, indicator names that newly fired, and indicator names that newly cleared.
  4. A vessel whose most recent snapshot is identical to the prior one shows "No changes since last run" in the change log rather than an empty section.
**Plans**: TBD

Plans:
- [ ] 08-01: TBD

#### Phase 9: Watchlist
**Goal**: Let the analyst permanently pin high-interest vessels to the top of the ranking table so they appear first on every session without sorting or searching.
**Depends on**: Phase 5 (ranking table exists); independent of Phases 6-8
**Requirements**: WTCH-01, WTCH-02, WTCH-03
**Success Criteria** (what must be TRUE):
  1. The analyst can pin a vessel from the ranking table row (one click) or from the vessel profile page; the pin persists across browser sessions and devices (stored in server-side PostgreSQL).
  2. Pinned vessels appear as a distinct group at the top of the ranking table above all non-pinned vessels, with a visible pin icon or equivalent indicator, regardless of their composite score relative to non-pinned vessels.
  3. Clicking the pin button on an already-pinned vessel removes it from the watchlist immediately; the vessel returns to its score-based position in the table on next load.
**Plans**: TBD

Plans:
- [ ] 09-01: TBD

#### Phase 10: Visual Legibility Pass
**Goal**: Increase readability across the dashboard and vessel profile by raising the base font size, adding breathing room between sections, and establishing a clear typographic hierarchy so the analyst's eye lands on the most important data first.
**Depends on**: Phase 5 (templates exist); independent of Phases 6-9
**Requirements**: VIS-01, VIS-02, VIS-03
**Success Criteria** (what must be TRUE):
  1. The base body font size is at least 15px across both the dashboard and vessel profile pages; table row height is adjusted proportionally so rows do not feel cramped at the larger size.
  2. A visible gap separates each dashboard panel and each vessel profile section from its neighbors; table rows have additional vertical padding compared to v1.0.
  3. The composite score number is the largest numeric element in both the ranking table row and the vessel profile header; the risk badge and section headings are visually larger than supporting labels and timestamp text.
**Plans**: TBD

Plans:
- [ ] 10-01: TBD

## Progress

**Execution Order:**
- v1.0 Phases 1-5: Complete
- v1.1 Phase 6: Runs first (unblocks 7 and 8)
- v1.1 Phase 7: After Phase 6
- v1.1 Phase 8: After Phase 6 (can run parallel with Phase 7)
- v1.1 Phase 9: After Phase 5 (can start any time; independent of 6-8)
- v1.1 Phase 10: After Phase 5 (can start any time; independent of 6-9)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Database Decomposition | v1.0 | 3/3 | Complete | 2026-03-04 |
| 2. Pre-Computed Risk Scores | v1.0 | 4/4 | Complete | 2026-03-05 |
| 3. Detection Test Coverage | v1.0 | 3/3 | Complete | 2026-03-05 |
| 4. Security Hardening | v1.0 | 3/3 | Complete | 2026-03-09 |
| 5. Frontend UX | v1.0 | 4/4 | Complete | 2026-03-10 |
| 6. Score History Infrastructure | v1.1 | 0/? | Not started | - |
| 7. Alert Generation and In-App Panel | v1.1 | 0/? | Not started | - |
| 8. Vessel Profile Enrichments | v1.1 | 0/? | Not started | - |
| 9. Watchlist | v1.1 | 0/? | Not started | - |
| 10. Visual Legibility Pass | v1.1 | 0/? | Not started | - |
