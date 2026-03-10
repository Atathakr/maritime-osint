---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Analyst Workflow
status: defining_requirements
stopped_at: —
last_updated: "2026-03-10"
last_activity: 2026-03-10 — Milestone v1.1 started, requirements defined, roadmap pending
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.
**Current focus:** Milestone v1.1 — Analyst Workflow (Phase 6 onwards)

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Roadmap pending — roadmapper running
Last activity: 2026-03-10 — Milestone v1.1 started

Progress: 0%

## Accumulated Context

### Decisions from v1.0

- [Pre-Phase 1]: Dual SQLite/PostgreSQL backend preserved; db/ decomposition must not break SQLite local dev path
- [Pre-Phase 1]: All callers use `import db; db.fn()` pattern — re-export surface in __init__.py must be complete
- [Pre-Phase 2]: APScheduler 3.x selected over Celery+Redis; no new Railway services beyond existing PostgreSQL
- [Pre-Phase 4]: flask-talisman force_https=False required for Railway TLS termination at edge proxy
- [Phase 04]: CSP enforcement active — no inline `<script>` blocks; all JS in static/*.js files
- [Phase 05]: indicator_json only stores FIRED indicators (keys = indicator IDs, absent = not fired)
- [Phase 05]: vessel_scores schema: composite_score INT, risk_level TEXT, indicator_json JSONB, computed_at TIMESTAMP, is_stale BOOLEAN
- [Phase 05]: Score data embedded server-side via `<script type="application/json">` — CSP safe
- [Phase 05]: session_transaction() used for test auth — POST /login returns 302 in test env

### Key Architecture Facts for v1.1

- APScheduler runs every 15 minutes; score history hooks into this same scheduler job
- vessel_scores table has one row per vessel (upserted each run); history table will be append-only
- Risk level thresholds: sanctioned=CRITICAL(100), >=70=HIGH, >=40=MEDIUM, else=LOW
- Chart library: Chart.js via CDN (zero-cost); no npm build pipeline
- Watchlist stored server-side in PostgreSQL — single operator but cross-session persistence preferred
- Alert generation runs inside APScheduler job, after scores are updated, comparing to prior snapshots

### Pending Todos

None.

### Blockers/Concerns

None known for v1.1 at this stage.
