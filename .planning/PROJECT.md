# maritime-osint

## What This Is

An open-source maritime threat intelligence platform that detects shadow fleet activity, sanctions evasion, and smuggling through a 31-indicator risk framework. It ingests live AIS streams, OFAC SDN data, OpenSanctions, and NOAA historical data, surfacing risk scores and alerts through a web dashboard. Deployed on Railway and built for maritime security analysts and researchers.

## Core Value

Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.

## Current Milestone: v1.1 — Analyst Workflow

**Goal:** Minimize platform dwell time — analysts should be notified when something changes, land on a clear explanation of what changed, and navigate to any vessel's full context in one click.

**Target features:**
- In-app alerting system (threshold crossing, top-50 entry, sanctions flip, large score delta)
- Score history tracking (foundation for alerts + trend visualization)
- Vessel profile enrichments (score trend chart, change log showing what changed since last run)
- Vessel watchlist (pin vessels to top of ranking table)
- Visual legibility pass (larger fonts, reduced density, clearer hierarchy)

## Requirements

### Validated

These capabilities shipped in v1.0 (Production Maturity Pass) and are working in production.

- ✓ Canonical vessel registry with IMO-based deduplication — v1.0
- ✓ OFAC SDN and OpenSanctions sanctions screening — v1.0
- ✓ Live AIS stream ingestion via aisstream.io WebSocket — v1.0
- ✓ NOAA historical AIS baseline ingestion — v1.0
- ✓ Dark period detection (Indicator 1) — v1.0
- ✓ AIS spoofing detection — v1.0
- ✓ Ship-to-ship transfer detection (Indicator 7) — v1.0
- ✓ Loitering detection — v1.0
- ✓ Flask web dashboard with password auth — v1.0
- ✓ Railway deployment (PostgreSQL + Gunicorn) — v1.0
- ✓ db/ package decomposition (schema, ingestion, detection, screening modules) — v1.0
- ✓ Pre-computed risk scores via APScheduler (vessel_scores table) — v1.0
- ✓ Automated detection test coverage (151 tests, all green) — v1.0
- ✓ Security hardening (rate limiting, CSRF, CSP enforcement, HSTS, Redis-backed limits) — v1.0
- ✓ Vessel ranking table (sortable, paginated 50/100/250, risk-colored, CSV export) — v1.0
- ✓ Vessel profile permalink (/vessel/<imo>) with freshness stamps and stale badge — v1.0
- ✓ Indicator breakdown table (31 rows, fired indicators highlighted) — v1.0
- ✓ Numeric risk score in map popups with "View Profile →" link — v1.0

### Active

This milestone: analyst workflow tools + legibility.

**Score History**
- [ ] Score snapshots stored per scheduler run when score changes (HIST-01)
- [ ] Last 30 snapshots queryable per vessel via API (HIST-02)

**Alerting**
- [ ] Dashboard header shows unread alert badge (ALRT-01)
- [ ] Alert list shows vessel name, alert type, trigger time (ALRT-02)
- [ ] Alert detail shows before/after score, newly fired indicators, link to vessel profile (ALRT-03)
- [ ] Alert fires on risk level threshold crossing (ALRT-04)
- [ ] Alert fires when vessel enters top 50 (ALRT-05)
- [ ] Alert fires when vessel becomes newly sanctioned (ALRT-06)
- [ ] Alert fires on 15+ point score delta in single scheduler run (ALRT-07)
- [ ] Analyst can mark alerts as read; badge decrements (ALRT-08)

**Vessel Profile Enrichments**
- [ ] Score trend chart (last 30 data points) on vessel profile (PROF-01)
- [ ] Change log on vessel profile: delta + newly fired indicators since prior snapshot (PROF-02)

**Watchlist**
- [ ] Analyst can pin a vessel to watchlist from ranking table or vessel profile (WTCH-01)
- [ ] Analyst can remove a vessel from watchlist (WTCH-02)
- [ ] Pinned vessels appear at top of ranking table with visual indicator (WTCH-03)

**Visual Legibility**
- [ ] Base font size increased across dashboard and vessel profile (VIS-01)
- [ ] Section spacing reduced — more breathing room between panels and table rows (VIS-02)
- [ ] Scores, risk badges, and indicator names have clear visual hierarchy (VIS-03)

### Out of Scope

- Real-time WebSocket dashboard push updates — polling sufficient
- Multi-user auth / RBAC — single-operator tool
- Mobile application — web-first
- ML-based anomaly detection — rule-based indicators only
- Paid data sources (Lloyd's, Refinitiv) — open data only
- Email / webhook alert delivery — in-app only for v1.1 (email deferred to v1.2+)
- Persistent watchlist across devices — localStorage acceptable for single-operator use

## Context

- **v1.0 shipped 2026-03-10**: DB decomposition, pre-computed scores, detection test coverage, security hardening, frontend UX all complete. 151 tests green, deployed on Railway.
- **APScheduler runs every 15 minutes**: computes vessel_scores for all vessels. Score history (v1.1) will hook into this same scheduler job.
- **Single-user platform**: watchlist and alert read-state can live in server-side DB keyed by a single user session, or localStorage. DB preferred for persistence across devices/sessions.
- **indicator_json stores only FIRED indicators**: keys are "IND1", "IND7" etc (no zero-padding). 12 of 31 implemented. Not-fired = absent key.
- **vessel_scores table**: composite_score INT, risk_level TEXT, indicator_json JSONB, computed_at TIMESTAMP, is_stale BOOLEAN.

## Constraints

- **Tech stack**: Python 3.11+, Flask, PostgreSQL (production), Railway — no stack changes
- **Budget**: Low operational cost; Railway hobby tier acceptable
- **Auth model**: Single shared password (`APP_PASSWORD`) — single operator tool
- **Chart library**: Must be zero-cost. Chart.js (CDN) or pure SVG acceptable. No npm build pipeline.
- **No new Railway services**: Alerts, history, watchlist all stored in existing PostgreSQL DB

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dual SQLite/PostgreSQL backend | Enables local development without cloud DB | ⚠️ Revisit — primary driver of db.py complexity |
| Risk scores computed on-demand | Simplest first approach | ✓ Resolved — pre-computed in v1.0 |
| Single password auth | Simple operator tool, not multi-user SaaS | ✓ Good |
| Open data sources only | Keeps operational cost near zero | ✓ Good |
| APScheduler over Celery+Redis | No new Railway services needed | ✓ Good |
| Score history in PostgreSQL (no separate time-series DB) | Keeps infrastructure simple; 30-snapshot query is fast with index | — Pending |

---
*Last updated: 2026-03-10 after v1.0 completion, v1.1 milestone started*
