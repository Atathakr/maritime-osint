# Milestones

## v1.0 — Production Maturity Pass

**Completed:** 2026-03-10
**Phases:** 1–5 (17 plans, 151 tests green)
**Goal:** Make the platform trustworthy and credible — solid architecture, security hardened, test-covered, and a frontend that a maritime analyst can actually use.

### What Shipped

| Phase | Name | Highlights |
|-------|------|-----------|
| 1 | Database Decomposition | db.py (2,835 lines) → db/ package with focused modules; SECRET_KEY enforcement |
| 2 | Pre-Computed Risk Scores | vessel_scores table, APScheduler (15-min cycle), N+1 eliminated, AIS archival |
| 3 | Detection Test Coverage | 151 automated tests; pure detect() functions; boundary fixtures |
| 4 | Security Hardening | flask-limiter (Redis-backed), flask-wtf CSRF, flask-talisman CSP enforcement, HSTS |
| 5 | Frontend UX | Ranking table (sortable, paginated), vessel permalink /vessel/<imo>, indicator breakdown (31 rows), map popup scores, CSV export |

### Requirements Delivered

DB-01 through DB-05, INF-01 through INF-05, SEC-01 through SEC-05, FE-01 through FE-06 — all complete.

---

## v1.1 — Analyst Workflow *(in progress)*

**Started:** 2026-03-10
**Phases:** 6+ (continuing from Phase 5)
**Goal:** Minimize platform dwell time — analysts get notified when something changes and can drill into any vessel's full context in one click.

See: REQUIREMENTS.md, ROADMAP.md
