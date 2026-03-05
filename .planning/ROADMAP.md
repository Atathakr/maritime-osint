# Roadmap: maritime-osint — Production Maturity Pass v1

## Overview

The platform has a sound detection and ingestion foundation. This milestone hardens it
structurally before adding new capabilities becomes dangerous. The work proceeds in
dependency order: decompose the db.py monolith first (zero behavior change, unblocks
everything), then add pre-computed risk scores (unblocks the entire frontend), then add
detection test coverage (safety net before security changes touch app.py), then harden
security and build the analyst-facing dashboard in parallel. The milestone ends when any
analyst can open the dashboard, see vessels ranked by risk, drill into why a vessel is
flagged, and trust that the data is fresh and the application is hardened.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Database Decomposition** - Split db.py into db/ package with re-exports; enforce SECRET_KEY; remove unused Anthropic SDK. Zero behavior change. (completed 2026-03-04)
- [x] **Phase 2: Pre-Computed Risk Scores** - Add vessel_scores table with APScheduler refresh; score history; staleness fallback; N+1 elimination; AIS archival. (completed 2026-03-05)
- [ ] **Phase 3: Detection Test Coverage** - Extract pure detect() functions from all 5 detection modules; pytest suite with synthetic AIS fixtures; conftest guards.
- [ ] **Phase 4: Security Hardening** - Flask-Limiter on login (PostgreSQL backend + ProxyFix); CSRF on login only; flask-talisman (CSP report-only then enforced); CodeQL dismissals.
- [ ] **Phase 5: Frontend UX** - Vessel ranking table; numeric scores everywhere; freshness stamps; indicator breakdown; vessel permalink; CSV export.

## Phase Details

### Phase 1: Database Decomposition
**Goal**: Replace the 2,835-line db.py monolith with a db/ package that all callers use identically, enforce SECRET_KEY from environment, and remove the unused Anthropic SDK — with zero observable behavior change.
**Depends on**: Nothing (first phase)
**Requirements**: DB-3, INF-3, INF-4
**Complexity**: M
**Success Criteria** (what must be TRUE):
  1. All existing callers (`import db; db.fn()`) work without modification after db.py is deleted.
  2. App fails with a clear error message at startup if SECRET_KEY is not set in the environment.
  3. The `anthropic` package is absent from requirements.txt and the app starts without import errors.
  4. All sub-modules in db/ import backend helpers only from db/connection.py — no sub-module duplicates placeholder logic.
  5. A fresh deploy to Railway behaves identically to the pre-split deployment (no new 500 errors on any route).
**Plans**: TBD

Plans:
- [ ] 01-01: Audit all db.fn() call sites; create db/ skeleton with __init__.py re-exporting everything from connection.py; delete db.py only after re-export inventory is verified
- [ ] 01-02: Extract schema.py, vessels.py, sanctions.py, ais.py, detection.py incrementally; update __init__.py re-exports after each extraction; add scores.py stub
- [ ] 01-03: Enforce SECRET_KEY via os.environ["SECRET_KEY"]; remove anthropic from requirements.txt; smoke-test on Railway

### Phase 2: Pre-Computed Risk Scores
**Goal**: Store composite risk scores and indicator breakdowns in a vessel_scores table, refresh them every 15 minutes via APScheduler, eliminate N+1 query patterns in the dashboard, and archive stale AIS positions daily — so all analyst-facing features have fast, fresh data to read from.
**Depends on**: Phase 1
**Requirements**: DB-1, DB-2, DB-4, DB-5, INF-1, INF-2
**Complexity**: L
**Success Criteria** (what must be TRUE):
  1. The vessel ranking dashboard endpoint returns in under 500ms for any fleet size (no per-vessel SELECT loops).
  2. vessel_scores contains composite_score, is_sanctioned, indicator_json (JSONB), and computed_at for every vessel; scores are no older than 15 minutes in steady state.
  3. vessel_score_history accumulates one row per vessel per refresh cycle; rows older than 90 days are deleted automatically.
  4. A newly-ingested OFAC sanction causes the affected vessel's score to be marked stale and recomputed before the next dashboard load.
  5. AIS positions older than 90 days are removed by a daily archival job; Railway storage growth is bounded.
**Plans**: TBD

Plans:
- [ ] 02-01: Create vessel_scores and vessel_score_history tables in db/scores.py; add init_db() DDL; create score read/upsert/mark-stale functions
- [ ] 02-02: Wire APScheduler in app.py (refresh_all_scores every 15 min; archive_old_positions daily); handle Gunicorn multi-worker double-refresh (advisory lock or single-worker)
- [ ] 02-03: Add staleness fallback in screening.py (recompute on demand if score >30 min old); add mark_risk_scores_stale() call to all ingest functions (upsert_sanctions, OFAC ingest)
- [ ] 02-04: Eliminate N+1 query patterns in dashboard and vessel ranking endpoints; replace per-vessel SELECT loops with batch queries

### Phase 3: Detection Test Coverage
**Goal**: Give every detection module a pure detect(positions) function that is testable without a database, and a pytest suite that validates threshold boundary logic with synthetic AIS fixtures — so Phase 4 security changes have a regression safety net.
**Depends on**: Phase 1
**Requirements**: INF (detection test coverage — implicit infrastructure requirement from PROJECT.md)
**Complexity**: M
**Success Criteria** (what must be TRUE):
  1. Each of the 5 detection modules (dark_periods, sts_detection, loitering, spoofing, screening) exposes a pure detect(positions) function that accepts a list of dicts and returns results with no database calls.
  2. Running `pytest tests/` with no DATABASE_URL set completes successfully; no test attempts to connect to PostgreSQL.
  3. Each detection module has at least one boundary test at threshold - epsilon (must NOT trigger) and one at threshold + epsilon (must trigger), with fixture values referencing module constants.
  4. pytest --cov reports: dark_periods >= 80%, sts_detection >= 80%, loitering >= 75%, spoofing >= 75%, screening >= 70%.
  5. conftest.py clears DATABASE_URL and AISSTREAM_API_KEY before any import of db or app, preventing CI environment leakage.
**Plans**: TBD

Plans:
- [ ] 03-01: Create tests/ structure; write conftest.py with DATABASE_URL/AISSTREAM_API_KEY guards and in-memory SQLite fixture via db.init_db(); write ais_factory.py position sequence generators
- [ ] 03-02: Extract detect(positions) pure function from dark_periods.py and sts_detection.py; write boundary tests for each referencing module constants
- [ ] 03-03: Extract detect(positions) from loitering.py, spoofing.py, and screening.py; write boundary tests; verify mock patch targets against db.* re-export surface with call_count assertions

### Phase 4: Security Hardening
**Goal**: Add rate limiting on login (with correct Railway proxy handling), CSRF protection on the login form only, and security headers (CSP audited and enforced) — and formally dismiss the 7 CodeQL false positives.
**Depends on**: Phase 1, Phase 3
**Requirements**: SEC-1, SEC-2, SEC-3, SEC-4, SEC-5
**Complexity**: M
**Success Criteria** (what must be TRUE):
  1. The /login endpoint returns 429 after 10 POST attempts per minute from a single IP; the limit counter persists across Railway deploys and Gunicorn worker restarts (stored in PostgreSQL, not memory).
  2. All /api/* POST endpoints continue to accept requests without CSRF tokens; only /login and /logout require CSRF validation.
  3. Browser DevTools shows HSTS, X-Frame-Options: DENY, and X-Content-Type-Options: nosniff headers on every response.
  4. The dashboard renders correctly with CSP enforcement enabled (no browser console CSP violations); all inline scripts have been moved to static/ JS files.
  5. All 7 py/sql-injection CodeQL alerts in GitHub Security tab show "Dismissed" status with rationale "Backend-agnostic placeholder variable, not user data."
**Plans**: TBD

Plans:
- [ ] 04-01: Audit all templates for inline <script> tags and {{ data | tojson }} patterns; move inline JS to static/ files; verify dashboard renders intact
- [ ] 04-02: Create security.py with init_security(app); add Flask-Limiter (PostgreSQL storage_uri, ProxyFix); add CSRFProtect with explicit /api/* exemptions; deploy CSP in report-only mode to Railway and check browser console
- [ ] 04-03: Enable CSP enforcement after template audit passes; verify HSTS at max_age=300; dismiss 7 CodeQL false positives via GitHub Security tab with documented rationale

### Phase 5: Frontend UX
**Goal**: Make the dashboard credible to maritime analysts — vessels ranked by risk score, numeric scores visible everywhere, indicator evidence showing why each vessel is flagged, freshness stamps on all data, and a vessel permalink plus CSV export.
**Depends on**: Phase 2
**Requirements**: FE-1, FE-2, FE-3, FE-4, FE-5, FE-6
**Complexity**: L
**Success Criteria** (what must be TRUE):
  1. An analyst opening the dashboard immediately sees vessels sorted by composite score (descending); the table is paginated (50/100/250 rows) and loads in under 500ms; clicking any column header re-sorts.
  2. Risk scores appear as integers (0-99) alongside the risk label everywhere: ranking table, vessel profile header, map popup on click, and search results.
  3. Every vessel profile shows "AIS last seen: Xh ago", "Sanctions screened: X days ago", and "Risk score: computed X min ago"; scores older than 2 hours are visually flagged as stale.
  4. The vessel profile indicator breakdown table lists all 31 indicators with points awarded, detection timestamp, and greyed-out indicators that did not fire; the total score is shown.
  5. Navigating to /vessel/<imo> loads the full vessel profile; the URL is stable and bookmarkable.
  6. The "Export CSV" button on the ranking table downloads the current filtered view as a CSV with columns: IMO, Name, Flag, Score, Level, Sanctions, Last AIS, Score Computed At.
**Plans**: TBD

Plans:
- [ ] 05-01: Add GET /vessel/<imo> permalink route; update vessel profile template to show risk score as integer, freshness stamps, and stale-score visual flag
- [ ] 05-02: Build vessel ranking table — sortable columns, pagination (50/100/250), risk-colored rows, numeric scores, <500ms using vessel_scores index; add /api/vessels/ranking endpoint
- [ ] 05-03: Add indicator point-contribution breakdown to vessel profile (reads indicator_json JSONB from vessel_scores); wire CSV export from ranking table

## Progress

**Execution Order:**
Phases execute in numeric order. Phases 2 and 3 can run in parallel (both depend on Phase 1 only).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Database Decomposition | 3/3 | Complete   | 2026-03-04 |
| 2. Pre-Computed Risk Scores | 4/4 | Complete   | 2026-03-05 |
| 3. Detection Test Coverage | 2/3 | In Progress|  |
| 4. Security Hardening | 0/3 | Not started | - |
| 5. Frontend UX | 0/3 | Not started | - |
