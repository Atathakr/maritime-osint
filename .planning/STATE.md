---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Analyst Workflow
status: executing
last_updated: "2026-03-11T17:38:21.480Z"
last_activity: 2026-03-11 — Plan 07-02 complete; all ALRT-01 through ALRT-08 pass
progress:
  total_phases: 10
  completed_phases: 7
  total_plans: 24
  completed_plans: 23
---

---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Analyst Workflow
status: executing
last_updated: "2026-03-11"
last_activity: 2026-03-11 — Plan 07-02 complete; all 8 ALRT tests passing, alert API routes + JS badge/panel + CSS complete
progress:
  total_phases: 10
  completed_phases: 7
  total_plans: 22
  completed_plans: 22
  percent: 100
  bar: "[██████████] 100%"
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.
**Current focus:** Milestone v1.1 — Analyst Workflow (Phases 6-10)

## Current Position

Phase: 8 — Vessel Profile Enrichments (In Progress)
Plan: 08-00 complete (4 PROF stubs created, RED phase done)
Status: Phase 8 Wave 0 complete. Next: Plan 08-01 (Wave 1 GREEN — implementation)
Last activity: 2026-03-11 — Plan 08-00 complete; 4 PROF test stubs created and failing on pytest.fail("stub")

Progress: [██████████] 96% (23/24 plans complete)

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

### Decisions from Plan 6-01 (GREEN — Implementation)

- [Plan 06-01]: append_score_history() derives risk_level internally (not from caller) — backward-compatible with test_scores.py calls that omit risk_level and indicator_json
- [Plan 06-01]: _score_changed() compares composite_score, is_sanctioned, and indicator_json (normalised to dict) — both sides normalised before comparison
- [Plan 06-01]: GET /api/vessels/<imo>/history registered before <path:imo> catch-all in app.py to prevent Flask route shadowing
- [Plan 06-01]: API exposes computed_at as recorded_at for downstream consumers (alert generation, trend chart)

### Decisions from Phase 7 Planning

- [Phase 07]: alerts table: dual-backend DDL (BIGSERIAL/TIMESTAMPTZ/JSONB Postgres; INTEGER AUTOINCREMENT/TEXT/TEXT SQLite); follows exact db/scores.py pattern
- [Phase 07]: alert_type TEXT enum: "risk_level_crossing" (ALRT-04), "top_50_entry" (ALRT-05), "sanctions_match" (ALRT-06), "score_spike" (ALRT-07)
- [Phase 07]: ALRT-05 two-pass: top_50_before captured from rows[:50] pre-loop; top_50_after from re-query post-loop; fires for top_50_after - top_50_before
- [Phase 07]: _generate_alerts() only called when prior history exists (guarded by `if prior:`) — no alert fires on first-ever history row
- [Phase 07]: static/alerts.js uses addEventListener throughout; no onclick injected into JS-generated HTML (CSP compliance)
- [Phase 07]: IMO range IMO9000001+ reserved for Phase 7 tests (avoids collision with Phases 2-6)
- [Phase 07]: POST /api/alerts/<id>/read is @csrf.exempt per Phase 4 decision (all /api/* POSTs exempt)
- [Phase 07]: vessel_name stored as snapshot at alert insert time (deliberate denormalization — consistent with vessel_score_history pattern)

### Decisions from Plan 7-00 (Wave 0 Test Stubs)

- [Plan 07-00]: Eight stubs defined covering ALRT-01 through ALRT-08 in tests/test_alerts.py
- [Plan 07-00]: IMO9000001+ range reserved for Phase 7 tests to avoid fixture collision with Phases 2-6
- [Plan 07-00]: Wave 0 stub pattern: pytest.fail("stub") in every test body, no imports beyond os and pytest at module level

### Decisions from Plan 7-01 (Backend: alerts table, generation, scheduler hook)

- [Plan 07-01]: lazy import: 'from app import _generate_alerts' moved inside test functions (not module-level) to prevent app.py's load_dotenv(override=True) from re-setting AISSTREAM_API_KEY during test collection
- [Plan 07-01]: get_unread_count() and mark_alert_read() use plain conn.cursor() (not _cursor()) so fetchone()[0] and rowcount work identically on both SQLite and PostgreSQL backends
- [Plan 07-01]: vessel_scores table has no risk_level column (only vessel_score_history does); test fixtures must not include risk_level in vessel_scores INSERT

### Decisions from Plan 7-02 (API routes, frontend JS, badge/panel HTML)

- [Plan 07-02]: Alert CSS appended directly to static/style.css after @imports (valid CSS per spec) — keeps Phase 7 scope in one commit vs adding a new import file
- [Plan 07-02]: test_conftest_guards DATABASE_URL failure in full suite is pre-existing (caused by ALRT-04/07 calling db._init_backend()) — not introduced or worsened by Plan 07-02
- [Plan 07-02]: Slide-in panel pattern established: #alert-panel (fixed right) + #alert-overlay (full-screen dim), toggled together via JS addEventListener

### Decisions from Plan 8-00 (Wave 0 Test Stubs)

- [Plan 08-00]: Four stubs defined covering PROF-01 (test_profile_has_history_card, test_history_single_snapshot) and PROF-02 (test_change_log_diff, test_change_log_identical_snapshots)
- [Plan 08-00]: IMO range IMO0200001+ reserved for Phase 8 tests (no collision with Phases 2-7)
- [Plan 08-00]: Wave 0 stub pattern: pytest.fail("stub") in every test body, no imports beyond os and pytest at module level

### Pending Todos

None.

### Blockers/Concerns

None known for v1.1 at this stage.
