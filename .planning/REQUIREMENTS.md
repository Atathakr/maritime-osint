# Requirements

**Milestone:** Production Maturity Pass v1
**Date:** 2026-03-03
**Status:** Active

---

## Milestone Goal

Bring the maritime-osint platform to a level where it can be used confidently by maritime analysts, compliance researchers, and sanctions screeners — without hitting performance walls, security gaps, or maintainability landmines.

---

## Validated Requirements (Existing Capabilities)

These are confirmed working and out of scope for this milestone:

- ✓ Canonical vessel registry with IMO-based deduplication
- ✓ OFAC SDN and OpenSanctions sanctions screening
- ✓ Live AIS stream ingestion via aisstream.io WebSocket
- ✓ NOAA historical AIS baseline ingestion
- ✓ Dark period detection (Indicator 1)
- ✓ AIS spoofing detection
- ✓ Ship-to-ship transfer detection (Indicator 7)
- ✓ Loitering detection
- ✓ Flask web dashboard with password auth
- ✓ Railway deployment (PostgreSQL + Gunicorn)

---

## Active Requirements

### Area 1: Database

**Goal:** Pre-compute risk scores so the dashboard is fast, and decompose db.py so the codebase is maintainable.

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| DB-1 | Pre-computed composite risk scores | `vessel_scores` table with `composite_score`, `indicator_json` (JSONB), `computed_at`; APScheduler refreshes every 15 min |
| DB-2 | Risk score history | `vessel_score_history` table; one row appended per vessel per refresh; 90-day retention policy in place |
| DB-3 | db.py decomposed into db/ package | `db/` package with `connection.py`, `schema.py`, and domain sub-modules; `__init__.py` re-exports all public functions; all existing callers (`import db; db.fn()`) unchanged |
| DB-4 | Score freshness metadata | `computed_at` timestamp stored on every score row; staleness fallback in `screening.py` re-computes on-demand if score is >30 min old |
| DB-5 | Score invalidation after ingest | Ingest functions (`upsert_sanctions`, OFAC ingest) mark affected vessel scores stale; next refresh re-scores them |

---

### Area 2: Infrastructure

**Goal:** Eliminate known reliability and maintainability landmines before they compound.

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| INF-1 | N+1 query elimination | No per-vessel SELECT loops in dashboard or vessel ranking endpoints; batch queries used for all multi-vessel data fetches |
| INF-2 | AIS position archival strategy | APScheduler job deletes `ais_positions` rows older than 90 days; job runs daily; Railway storage growth bounded |
| INF-3 | Unused Anthropic SDK removed | `anthropic` package removed from `requirements.txt` if confirmed unused; no import errors |
| INF-4 | Session secret enforcement | `SECRET_KEY` loaded from environment variable; app fails with clear error at startup if not set; no hardcoded or generated-at-runtime secret |

---

### Area 3: Security

**Goal:** Harden the live application against common web attacks and raise code-level security posture.

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| SEC-1 | Login rate limiting | `/login` POST limited to 10 attempts/minute per IP; Flask-Limiter with PostgreSQL storage backend (not in-memory); ProxyFix applied for Railway proxy headers |
| SEC-2 | CSRF protection on login form | Flask-WTF CSRFProtect on `/login` and `/logout`; all `/api/*` routes explicitly exempted; no impact on ingest endpoints |
| SEC-3 | Security headers | flask-talisman applied with: HSTS, CSP whitelist (self + unpkg.com + OSM tiles), X-Frame-Options DENY, X-Content-Type-Options; `force_https=False` for Railway |
| SEC-4 | CSP template audit | All inline `<script>` tags in dashboard templates moved to `static/` JS files before CSP enforcement enabled; CSP deployed in report-only mode first |
| SEC-5 | CodeQL false positives dismissed | 7 open `py/sql-injection` medium alerts in GitHub Security tab dismissed as false positives; reason documented: "Backend-agnostic placeholder variable, not user data" |

---

### Area 4: Frontend

**Goal:** Make the dashboard credible to maritime professionals by surfacing risk data clearly and completely.

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FE-1 | Vessel ranking table | Sortable table of all vessels ranked by composite score (desc default); columns: Name, IMO, Flag, Score (number), Level (label), Last AIS, Sanctions; paginated 50/100/250; loads in <500ms |
| FE-2 | Risk score as number everywhere | Numeric score (0-99) displayed alongside risk label on: ranking table, vessel profile header, map popup on click, search results |
| FE-3 | Data freshness stamps | Vessel profile shows: "AIS last seen: Xh ago", "Sanctions screened: X days ago", "Risk score: computed X min ago"; stale scores (>2h) flagged visually |
| FE-4 | Indicator point-contribution breakdown | Vessel profile shows per-indicator table: indicator name, description, points awarded, detection timestamp; indicators that did NOT fire shown greyed out; total shown |
| FE-5 | Vessel profile permalink | Stable route `GET /vessel/<imo>` returns full profile; URL copyable and bookmarkable |
| FE-6 | CSV export | From vessel ranking table, export current filtered view as CSV (IMO, Name, Flag, Score, Level, Sanctions, Last AIS, Score Computed At) |

---

## Out of Scope (This Milestone)

- Real-time WebSocket push to browser
- Multi-user RBAC / user management
- Mobile app or responsive redesign
- ML-based anomaly detection
- Paid data source integrations (MarineTraffic, Windward API)
- AIS track replay timeline slider
- Score trend visualization charts
- Automated CodeQL remediation agent (Gasparilla — deferred)

---

## Dependencies Between Areas

```
DB-1 (vessel_scores table)
  → FE-1 (ranking table — needs pre-computed scores for <500ms)
  → FE-2 (score number — needs score to be stored)
  → FE-3 (freshness stamps — needs computed_at)
  → FE-4 (indicator breakdown — needs indicator_json JSONB)

DB-3 (db/ package)
  → SEC-1, SEC-2, SEC-3 (stable public API before security layer wraps it)
  → INF-1 (batch queries easier to write against clean db modules)

INF-4 (SECRET_KEY enforcement)
  → SEC-1, SEC-2 (Flask-Limiter and Flask-WTF both need app.secret_key)
```

---

## Build Order Recommendation

Based on dependencies and risk:

1. **Phase 1 — Database Decomposition** (DB-3, INF-3, INF-4): Foundation; zero behavior change; creates `db/` package that all subsequent phases depend on
2. **Phase 2 — Pre-Computed Scores** (DB-1, DB-2, DB-4, DB-5, INF-1, INF-2): Highest value; unblocks all frontend features; do after Phase 1
3. **Phase 3 — Test Coverage** (parallel with Phase 2): Write detection module tests; provides regression safety net for Phase 4
4. **Phase 4 — Security Hardening** (SEC-1 through SEC-5): After stable db surface and test safety net
5. **Phase 5 — Frontend UX** (FE-1 through FE-6): After pre-computed scores exist; FE-1 through FE-4 are all blocked on DB-1

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-3 | Phase 1 — Database Decomposition | Complete |
| INF-3 | Phase 1 — Database Decomposition | Complete |
| INF-4 | Phase 1 — Database Decomposition | Complete |
| DB-1 | Phase 2 — Pre-Computed Risk Scores | Complete |
| DB-2 | Phase 2 — Pre-Computed Risk Scores | Complete |
| DB-4 | Phase 2 — Pre-Computed Risk Scores | Complete |
| DB-5 | Phase 2 — Pre-Computed Risk Scores | Complete |
| INF-1 | Phase 2 — Pre-Computed Risk Scores | Complete |
| INF-2 | Phase 2 — Pre-Computed Risk Scores | Complete |
| INF (detection test coverage) | Phase 3 — Detection Test Coverage | Pending |
| SEC-1 | Phase 4 — Security Hardening | Complete |
| SEC-2 | Phase 4 — Security Hardening | Complete |
| SEC-3 | Phase 4 — Security Hardening | Complete |
| SEC-4 | Phase 4 — Security Hardening | Complete |
| SEC-5 | Phase 4 — Security Hardening | Complete |
| FE-1 | Phase 5 — Frontend UX | Pending |
| FE-2 | Phase 5 — Frontend UX | Pending |
| FE-3 | Phase 5 — Frontend UX | Pending |
| FE-4 | Phase 5 — Frontend UX | Pending |
| FE-5 | Phase 5 — Frontend UX | Pending |
| FE-6 | Phase 5 — Frontend UX | Pending |
