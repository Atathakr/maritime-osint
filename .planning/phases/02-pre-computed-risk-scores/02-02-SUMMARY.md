---
phase: 02-pre-computed-risk-scores
plan: "02"
subsystem: infra
tags: [apscheduler, background-jobs, postgresql, advisory-lock, gunicorn, scheduler]

# Dependency graph
requires:
  - phase: 02-pre-computed-risk-scores
    provides: "02-01: vessel_scores table, upsert_vessel_score, get_all_vessel_scores, archive_old_ais_positions, prune_score_history, SCHEDULER_ADVISORY_LOCK_ID=42"
provides:
  - BackgroundScheduler in app.py with 3 registered jobs
  - score_refresh job (interval 15min) with pg_try_advisory_xact_lock(42) multi-worker guard
  - ais_archive job (cron 03:00 UTC) calling db.archive_old_ais_positions(90)
  - history_prune job (cron 03:05 UTC) calling db.prune_score_history(90)
  - _do_score_refresh() ready to call screening.compute_vessel_score() once 02-03 ships
affects: [02-03-staleness, 02-04-n1-elimination, 05-frontend-ux]

# Tech tracking
tech-stack:
  added: []  # apscheduler already added to requirements.txt in 02-01
  patterns:
    - "pg_try_advisory_xact_lock(42) transaction-level guard — auto-releases on transaction commit, not session-scoped"
    - "Dual-path scheduler: PostgreSQL workers use advisory lock, SQLite local dev skips lock entirely"
    - "BackgroundScheduler(daemon=True) — daemon thread does not block Gunicorn worker shutdown"
    - "Job try/except in each job function — scheduler keeps running even if one job body fails"

key-files:
  created: []
  modified:
    - app.py

key-decisions:
  - "_SCHEDULER_ADVISORY_LOCK_ID = 42 defined as module-level constant in app.py (not imported from db.scores) to keep advisory lock logic co-located with scheduler code"
  - "BackgroundScheduler import placed with top-level imports; scheduler start placed immediately after AIS listener block — before route definitions"
  - "_do_score_refresh() calls screening.compute_vessel_score(imo) which does not yet exist (02-03's job); try/except in the per-vessel loop catches AttributeError gracefully; no crash"
  - "replace_existing=True on all add_job calls — safe for future app restarts / hot reload"

patterns-established:
  - "Scheduler job pattern: outer job function handles advisory lock + exception logging; inner _do_* function contains business logic"
  - "Advisory lock scope: entire _do_score_refresh() runs inside the advisory lock transaction — lock auto-releases when 'with db._conn()' block exits"

requirements-completed: [DB-1, INF-2]

# Metrics
duration: 5min
completed: 2026-03-05
---

# Phase 2 Plan 02: APScheduler background jobs Summary

**APScheduler BackgroundScheduler wired into app.py with 3 jobs: 15-min score refresh (pg_try_advisory_xact_lock multi-worker guard), 03:00 UTC AIS archive, 03:05 UTC history prune**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-05T13:05:00Z
- **Completed:** 2026-03-05T13:10:00Z
- **Tasks:** 1 (Task 1 implementation)
- **Files modified:** 1

## Accomplishments
- BackgroundScheduler (daemon=True) starts after db.init_db() — tables guaranteed to exist on first job fire
- score_refresh uses pg_try_advisory_xact_lock(42) on PostgreSQL; SQLite path skips lock entirely
- All 3 jobs verified: `score_refresh interval[0:15:00]`, `ais_archive cron[hour='3', minute='0']`, `history_prune cron[hour='3', minute='5']`
- _do_score_refresh() gracefully handles missing compute_vessel_score (02-03 not yet shipped) via per-vessel try/except

## Task Commits

Each task was committed atomically:

1. **Task 1: Add scheduler job functions and BackgroundScheduler to app.py** - `5efcfcc` (feat)

## Files Created/Modified
- `app.py` - Added BackgroundScheduler import, 4 job functions (_refresh_all_scores_job, _do_score_refresh, _archive_ais_job, _prune_history_job), scheduler init with 3 registered jobs

## Decisions Made
- Advisory lock constant _SCHEDULER_ADVISORY_LOCK_ID = 42 defined inline in app.py (co-located with scheduler code) rather than imported from db.scores.SCHEDULER_ADVISORY_LOCK_ID — both equal 42, co-location is cleaner
- replace_existing=True on all jobs ensures safe re-registration on app restarts
- BackgroundScheduler(daemon=True) — daemon thread exits cleanly when Gunicorn worker shuts down

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- apscheduler not installed in local Python 3.14 at C:\Python314 — used C:\Users\ardal\AppData\Local\Python\bin\python3.exe (which has project deps) for verification. apscheduler installed there for verification purposes.

## User Setup Required
None - no external service configuration required. apscheduler is already in requirements.txt (added in 02-01) so Railway deploys will have it.

## Next Phase Readiness
- 02-03 (staleness + compute_vessel_score extraction) can be executed immediately — _do_score_refresh() already calls screening.compute_vessel_score(imo); once 02-03 ships that function, the scheduler will automatically start computing real scores
- 02-04 (N+1 elimination) unaffected — scheduler is independent background concern
- No blockers

---
*Phase: 02-pre-computed-risk-scores*
*Completed: 2026-03-05*

## Self-Check: PASSED

- app.py: FOUND (modified with scheduler block)
- Commit 5efcfcc (scheduler implementation): FOUND
- 3 jobs registered: score_refresh, ais_archive, history_prune — VERIFIED via import test
- Advisory lock uses pg_try_advisory_xact_lock (not session-level): VERIFIED in code
- SQLite path skips lock: VERIFIED in code (db._BACKEND == "postgres" guard)
