---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_execute
stopped_at: Completed 03-detection-test-coverage/03-01-PLAN.md
last_updated: "2026-03-05T17:51:11.418Z"
last_activity: 2026-03-04 — Phase 2 plans 02-01/02/03/04 written and verified
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 10
  completed_plans: 8
  percent: 57
---

---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_execute
stopped_at: Phase 2 planning complete — 4 plans ready, plan-checker PASSED
last_updated: "2026-03-04T22:00:00.000Z"
last_activity: 2026-03-04 — Phase 2 plans 02-01 through 02-04 written and verified
progress:
  [██████░░░░] 57%
  completed_phases: 1
  total_plans: 7
  completed_plans: 3
  percent: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Any analyst can load the dashboard and immediately see which vessels are highest risk — with enough context to understand why and act on it.
**Current focus:** Phase 3 — Detection Test Coverage (3 plans total, 1 complete)

## Current Position

Phase: 2 of 5 complete ✅
Phase 3: 1 of 3 plans complete (03-01 done, 03-02 ready to execute)
Status: Phase 3 in progress — 03-01 complete, ready for 03-02
Last activity: 2026-03-05 — Phase 3 plan 03-01 (test infrastructure) complete

Progress: [████████░░] 80%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~24 min/plan
- Total execution time: ~72 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01-database-decomposition | 3 | ~72 min | ~24 min |

**Recent Trend:**
- Last 5 plans: 45 min (P01), 11 min (P02), 15 min (P03)
- Trend: Stable

*Updated after each plan completion*
| Phase 02-pre-computed-risk-scores P01 | 5 | 3 tasks | 6 files |
| Phase 02-pre-computed-risk-scores P02 | 5 | 1 tasks | 1 files |
| Phase 02-pre-computed-risk-scores P03 | 4 | 4 tasks | 3 files |
| Phase 02-pre-computed-risk-scores P04 | 5 | 2 tasks | 1 files |
| Phase 03-detection-test-coverage P01 | 3 | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Pre-Phase 1]: Dual SQLite/PostgreSQL backend preserved through this milestone; db/ decomposition must not break SQLite local dev path
- [Pre-Phase 1]: All callers use `import db; db.fn()` pattern — re-export surface in __init__.py must be complete before db.py is deleted (Pitfall B2)
- [Pre-Phase 2]: APScheduler 3.x selected over Celery+Redis; no new Railway services beyond existing PostgreSQL
- [Pre-Phase 4]: flask-talisman force_https=False required for Railway TLS termination at edge proxy
- [Phase 01-database-decomposition]: sanctions.py imports get_vessel_memberships from .vessels — intra-package dep needed by rebuild_all_source_tags
- [Phase 01-database-decomposition]: p='?' placeholder pattern kept inline in function bodies (not replaced with _ph()) to match original db.py verbatim style
- [Phase 01-database-decomposition]: scores.py scores block in __init__.py left commented — no functions to export in Phase 1; Phase 2 fills
- [Phase 01-database-decomposition]: Startup enforcement moved before load_dotenv() and module imports so .env cannot mask missing production env vars and subprocess tests don't need full dependency chain
- [Phase 01-database-decomposition]: pydantic must be declared explicitly in requirements.txt — schemas.py imports it directly; was previously a transitive dep of anthropic
- [Phase 02-pre-computed-risk-scores]: indicator_json stores all 31 indicators (fired + not-fired) as dict keyed by indicator ID; fired indicators: {pts, fired: true, fired_at}; not-fired: {pts: 0, fired: false}
- [Phase 02-pre-computed-risk-scores]: Staleness fallback = block + recompute inline + persist to vessel_scores; SCORE_STALENESS_MINUTES = 30 hardcoded constant in db/scores.py
- [Phase 02-pre-computed-risk-scores]: Multi-worker double-refresh via pg_try_advisory_xact_lock(42) (transaction-level, auto-releases on commit — NOT session-level pg_try_advisory_lock); SQLite skips lock; SCHEDULER_ADVISORY_LOCK_ID = 42
- [Phase 02-pre-computed-risk-scores]: map_data.py qualitative risk system (CRITICAL/HIGH/MEDIUM/LOW) is NOT changed in Phase 2 — map numeric score display deferred to Phase 5 (FE-2)
- [Phase 02-pre-computed-risk-scores]: db/scores.py uses __file__-anchored _sqlite_path() — tests must use db._sqlite_path() not tmp_path/monkeypatch.chdir for correct DB isolation
- [Phase 02-pre-computed-risk-scores]: _SCHEDULER_ADVISORY_LOCK_ID=42 defined inline in app.py co-located with scheduler code; BackgroundScheduler(daemon=True) starts after db.init_db(); _do_score_refresh() try/except handles missing compute_vessel_score gracefully until 02-03 ships
- [Phase 02-pre-computed-risk-scores]: score_is_stale() placed in screening.py (not db/) — staleness is a screening-layer concern; db layer stores the flag, application layer interprets it
- [Phase 02-pre-computed-risk-scores]: _cached_sanctioned extracted from score cache but VesselDetail display logic still runs live DB queries; only risk_score integer comes from cache for UI completeness
- [Phase 02-pre-computed-risk-scores]: Ranking route registered before /api/vessels/<path:imo> catch-all — prevents Flask consuming 'ranking' as an IMO value
- [Phase 02-pre-computed-risk-scores]: sanctioned_only filter applied in Python after single batch fetch — avoids additional DB round-trip
- [Phase 03-detection-test-coverage]: conftest.py upgraded from setdefault to direct os.environ["DATABASE_URL"] = "" assignment for CI-safe env guard
- [Phase 03-detection-test-coverage]: ais_factory.py uses plain functions not pytest fixtures — boundary tests need parametrize-friendly callables

### Pending Todos

None.

### Blockers/Concerns

- [Phase 2] APScheduler double-refresh with 2 Gunicorn workers — resolve during Phase 2 implementation (advisory lock or reduce to 1 worker on hobby tier)
- [Phase 4] Flask-Limiter PostgreSQL storage URI format — Railway uses postgres:// scheme; limits library may require postgresql://; verify during Phase 4 implementation before assuming it works
- [Phase 4] CSP inline script audit scope unknown — count of templates with {{ data | tojson }} inside <script> tags unknown; audit is first task of Phase 4 to size the work

## Session Continuity

Last session: 2026-03-05T17:51:11.413Z
Stopped at: Completed 03-detection-test-coverage/03-01-PLAN.md
Resume file: None
