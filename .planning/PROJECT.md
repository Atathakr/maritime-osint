# maritime-osint

## What This Is

An open-source maritime threat intelligence platform that detects shadow fleet activity, sanctions evasion, and smuggling through a 31-indicator risk framework. It ingests live AIS streams, OFAC SDN data, OpenSanctions, and NOAA historical data, surfacing risk scores and alerts through a web dashboard. Deployed on Railway and built for maritime security analysts and researchers.

## Core Value

Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.

## Requirements

### Validated

These capabilities exist in the current codebase and are working in production.

- ✓ Canonical vessel registry with IMO-based deduplication — existing
- ✓ OFAC SDN and OpenSanctions sanctions screening — existing
- ✓ Live AIS stream ingestion via aisstream.io WebSocket — existing
- ✓ NOAA historical AIS baseline ingestion — existing
- ✓ Dark period detection (Indicator 1) — existing
- ✓ AIS spoofing detection — existing
- ✓ Ship-to-ship transfer detection (Indicator 7) — existing
- ✓ Loitering detection — existing
- ✓ Flask web dashboard with password auth — existing
- ✓ Railway deployment (PostgreSQL + Gunicorn) — existing

### Active

This milestone: production maturity pass across four areas.

**Database**
- [ ] Composite risk scores pre-computed and stored per vessel (fast ranking queries)
- [ ] Risk score history tracked over time (trend visibility)
- [ ] db.py decomposed into focused modules (schema, ingestion, detection, screening)

**Infrastructure**
- [ ] N+1 query patterns eliminated in dashboard data loading
- [ ] AIS position table has an archival/partitioning strategy (unbounded growth addressed)
- [ ] Unused Anthropic SDK dependency removed or justified
- [ ] Detection logic (loitering, STS, dark periods, spoofing) has automated test coverage

**Security**
- [ ] Rate limiting on login endpoint (brute force protection)
- [ ] CSRF protection on state-changing endpoints
- [ ] Security headers in place (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- [ ] 7 CodeQL false positive alerts formally dismissed with documented rationale
- [ ] Session secret enforced via environment variable (not auto-generated on restart)

**Frontend**
- [ ] Dashboard layout conveys analyst-grade credibility (risk table, vessel detail, indicator breakdown)
- [ ] Vessel risk scores visible and sortable without writing queries
- [ ] Indicator evidence shown per vessel (why is this vessel risky?)

### Out of Scope

- Real-time WebSocket dashboard push updates — polling sufficient for v1
- Multi-user auth / RBAC — single-operator tool for now
- Mobile application — web-first
- ML-based anomaly detection — rule-based indicators only in this milestone
- Paid data sources (Lloyd's, Refinitiv) — open data only

## Context

- **db.py is a 2,835-line monolith** combining schema, migrations, CRUD, and business logic for both backends — the single largest maintainability risk
- **Dual-backend pattern** (SQLite for local dev, PostgreSQL for production) enables offline development but adds complexity throughout db.py; production is PostgreSQL on Railway
- **Local SQLite file is 213MB** with WAL fragments — local dev story needs clarifying
- **Risk scores are computed on request**, not stored — limits dashboard performance and makes vessel ranking expensive
- **No test coverage** for the detection modules (loitering, STS, dark periods, spoofing) — these are the highest-value and highest-risk code paths
- **7 CodeQL py/sql-injection alerts** are false positives: the `p` variable in f-string SQL is the placeholder character (`"?"` or `"%s"`), never user data; pyproject.toml already suppresses the equivalent Ruff rule (S608)
- **Anthropic SDK** listed as a dependency but not used anywhere in the codebase

## Constraints

- **Tech stack**: Python 3.11+, Flask, PostgreSQL (production), Railway — no stack changes
- **Budget**: Low operational cost; Railway hobby tier acceptable
- **Auth model**: Single shared password (`APP_PASSWORD`) is acceptable for a solo operator tool
- **Backward compatibility**: Maintain dual SQLite/PostgreSQL backend through this milestone (local dev story needs resolution before removing it)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dual SQLite/PostgreSQL backend | Enables local development without cloud DB | ⚠️ Revisit — primary driver of db.py complexity |
| Risk scores computed on-demand | Simplest first approach | ⚠️ Revisit — active work to pre-compute |
| Single password auth | Simple operator tool, not multi-user SaaS | — Pending |
| Open data sources only | Keeps operational cost near zero | ✓ Good |

---
*Last updated: 2026-03-03 after initialization*
