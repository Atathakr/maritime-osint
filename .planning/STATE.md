---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Analyst Workflow
status: executing
stopped_at: "Completed 06-00-PLAN.md"
last_updated: "2026-03-10"
last_activity: 2026-03-10 — Plan 6-00 complete; test stubs created; ready for Plan 6-01
progress:
  total_phases: 10
  completed_phases: 5
  total_plans: 19
  completed_plans: 18
  percent: 95
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.
**Current focus:** Milestone v1.1 — Analyst Workflow (Phases 6-10)

## Current Position

Phase: 6 — Score History Infrastructure (Executing)
Plan: 06-01 (Wave 1, not started)
Status: Plan 6-00 complete — test stubs created; next action is Plan 6-01 (Wave 1)
Last activity: 2026-03-10 — Plan 6-00 executed; tests/test_hist.py created with 4 failing stubs (HIST-01, HIST-02)

Progress: [██████████] 95%

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
- History table is the prerequisite for: alert generation (ALRT-04 through ALRT-07 compare snapshots), trend chart (PROF-01), and change log (PROF-02)
- Phases 9 and 10 are independent of history and can be planned/executed in any order relative to 7 and 8

### Decisions from v1.1 Roadmap Creation

- [Roadmap]: Phase 6 (history) must complete before Phase 7 (alerts) and Phase 8 (profile enrichments) can begin — both require prior snapshots to compute deltas
- [Roadmap]: Phase 9 (watchlist) and Phase 10 (visual legibility) depend only on Phase 5 completion; they are independent of the history/alert chain and can run in parallel
- [Roadmap]: Alert read/unread state stored server-side in PostgreSQL (consistent with watchlist decision — single operator, cross-session persistence preferred)
- [Roadmap]: No new Railway services for any v1.1 feature; all tables in existing PostgreSQL DB

### Decisions from Phase 6 Planning

- [Phase 06]: vessel_score_history table already existed from Phase 2 but was missing risk_level and indicator_json — Phase 6 adds these via DDL migration (ALTER TABLE IF NOT EXISTS for PG, PRAGMA table_info pattern for SQLite)
- [Phase 06]: append_score_history() derives risk_level internally (not from caller) — backward-compatible with existing test_scores.py calls
- [Phase 06]: change-detection lives in _do_score_refresh() via _score_changed() helper, not inside append_score_history() itself — keeps append function as an unconditional write primitive
- [Phase 06]: history endpoint column rename: DB stores computed_at, API exposes it as recorded_at for downstream consumers (alert generation, trend chart)
- [Phase 06]: GET /api/vessels/<imo>/history must be registered BEFORE existing <path:imo> catch-all route in app.py to prevent shadowing

### Decisions from Plan 6-00 (Wave 0 Test Stubs)

- [Plan 06-00]: Four stubs defined covering HIST-01 (test_history_row_written, test_no_spurious_row) and HIST-02 (test_history_endpoint, test_history_endpoint_404)
- [Plan 06-00]: IMO8000001+ range reserved for Phase 6 tests to avoid fixture collisions with Phases 2-5
- [Plan 06-00]: Wave 0 stub pattern: pytest.fail("stub") in every test body, no imports beyond os and pytest

### Pending Todos

None.

### Blockers/Concerns

None known for v1.1 at this stage.
