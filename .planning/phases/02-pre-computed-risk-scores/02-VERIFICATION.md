---
phase: 02-pre-computed-risk-scores
verified: 2026-03-04T00:00:00Z
status: passed
score: 16/16 must-haves verified
re_verification: false
---

# Phase 2: Pre-Computed Risk Scores Verification Report

**Phase Goal:** Pre-compute vessel risk scores so every request reads from cache rather than re-running the full indicator pipeline — eliminating N+1 patterns and decoupling display from computation.
**Verified:** 2026-03-04
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | `db.init_db()` creates `vessel_scores` and `vessel_score_history` tables without error on both SQLite and PostgreSQL | VERIFIED | `db/schema.py` line 49-50 calls `init_scores_tables()` at end of `init_db()`; both table DDLs confirmed in `db/scores.py` lines 41-98; `test_init_scores_tables` passes |
| 2  | `db.upsert_vessel_score()` inserts a new row and updates an existing row; `is_stale` resets to 0 on upsert | VERIFIED | `db/scores.py` lines 103-148: ON CONFLICT DO UPDATE SET with `is_stale = 0` hardcoded; `test_upsert_vessel_score` and `test_upsert_clears_stale` both pass |
| 3  | `db.get_vessel_score()` returns a dict with `indicator_json` as a Python dict (not a string) regardless of backend | VERIFIED | `db/scores.py` lines 151-174: `isinstance(row["indicator_json"], str)` check and `_json.loads()` normalisation; `test_get_vessel_score` confirms `isinstance(row["indicator_json"], dict)` |
| 4  | `db.get_all_vessel_scores()` returns a list of dicts from a single JOIN — no per-vessel query loop | VERIFIED | `db/scores.py` lines 177-215: single SQL `SELECT ... FROM vessel_scores vs JOIN vessels_canonical vc USING (imo_number) LEFT JOIN ais_vessels av ON vc.mmsi = av.mmsi ORDER BY vs.composite_score DESC` — one query, no loop; `test_get_all_vessel_scores` passes |
| 5  | `db.mark_risk_scores_stale()` sets `is_stale=1` for the given IMOs and returns count of rows updated | VERIFIED | `db/scores.py` lines 218-236: `UPDATE vessel_scores SET is_stale = 1 WHERE imo_number IN (...)` returns `c.rowcount`; `test_mark_risk_scores_stale` passes with `count == 1` |
| 6  | `db.append_score_history()` inserts a history row; `db.prune_score_history()` deletes rows older than 90 days | VERIFIED | `db/scores.py` lines 239-282; `test_append_score_history` confirms count == 1; `test_prune_score_history` confirms old row deleted, recent row kept |
| 7  | `db.archive_old_ais_positions()` deletes `ais_positions` rows older than 90 days and returns count | VERIFIED | `db/scores.py` lines 285-301; `test_archive_old_ais_positions` inserts old+recent rows, confirms at least 1 deleted and recent row remains |
| 8  | All 8 scores functions are re-exported from `db/__init__.py` and visible as `db.<fn>()` | VERIFIED | `db/__init__.py` lines 74-79: explicit `from .scores import (...)` block with all 8 functions; `test_all_public_functions_exported` passes |
| 9  | APScheduler BackgroundScheduler starts after `db.init_db()` and registers 3 jobs: `score_refresh` (every 15 min), `ais_archive` (03:00 UTC), `history_prune` (03:05 UTC) | VERIFIED | `app.py` lines 134-158: `_scheduler = BackgroundScheduler(daemon=True)` with 3 `add_job()` calls; runtime check confirms `jobs: ['score_refresh', 'ais_archive', 'history_prune']` |
| 10 | On PostgreSQL, only one Gunicorn worker executes the score refresh job body at a time via `pg_try_advisory_xact_lock(42)` | VERIFIED | `app.py` lines 73-80: `c.execute("SELECT pg_try_advisory_xact_lock(%s)", (42,))` inside `db._conn()` context manager (transaction-level, auto-releases on commit) |
| 11 | On SQLite local dev, the advisory lock is skipped; scheduler runs jobs normally | VERIFIED | `app.py` lines 81-83: `else: _do_score_refresh()` branch for non-postgres backend |
| 12 | `compute_vessel_score(imo)` exists in `screening.py` and returns dict with `composite_score`, `is_sanctioned`, `indicator_json` (31 IND keys), `computed_at` | VERIFIED | `screening.py` lines 183-341: function defined; runtime check confirms `Keys: ['composite_score', 'computed_at', 'indicator_json', 'is_sanctioned']` and `IND count: 31` |
| 13 | `score_is_stale(score_row)` returns True when `is_stale=1` regardless of age; returns True when `computed_at` > 30 min ago; returns False when score is fresh | VERIFIED | `screening.py` lines 165-180; `test_score_is_stale_age` verifies age-based staleness (35 min = stale, 10 min = fresh); `test_score_is_stale_flag` verifies flag-based staleness |
| 14 | `screen_vessel_detail()` checks `db.get_vessel_score()` at the top; if stale or missing it calls `compute_vessel_score()` + `db.upsert_vessel_score()` before building VesselDetail | VERIFIED | `screening.py` lines 368-377: `score_row = db.get_vessel_score(imo_clean)` then `if score_row is None or score_is_stale(score_row): fresh = compute_vessel_score(imo_clean); db.upsert_vessel_score(imo_clean, fresh)` |
| 15 | `_run_ingest()` in `app.py` calls `db.mark_risk_scores_stale()` with affected IMOs after a successful `upsert_sanctions_entries()` | VERIFIED | `app.py` lines 340-345: `_affected_imos = [e.get("imo_number") for e in entries if e.get("imo_number")]; if _affected_imos: db.mark_risk_scores_stale(_affected_imos)` inside the try block, before `log_ingest_complete()` |
| 16 | `GET /api/vessels/ranking` endpoint exists and uses `db.get_all_vessel_scores()` — a single JOIN with no per-vessel SELECT loop | VERIFIED | `app.py` lines 290-320: route `@app.get("/api/vessels/ranking")` before `/api/vessels/<path:imo>`; `rows = db.get_all_vessel_scores()` is the only DB call; runtime confirms route registered |

**Score:** 16/16 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/scores.py` | Full scores CRUD implementation (8 functions + 2 constants); min 120 lines | VERIFIED | 301 lines; 8 public functions + `SCORE_STALENESS_MINUTES=30` + `SCHEDULER_ADVISORY_LOCK_ID=42` |
| `db/__init__.py` | Uncommented scores re-export block with all 8 functions | VERIFIED | Lines 72-79: live `from .scores import (...)` block — not commented out |
| `db/schema.py` | `init_db()` calls `init_scores_tables()` | VERIFIED | Lines 49-50: local import + explicit call after `_migrate_vessels_canonical()` |
| `requirements.txt` | `apscheduler>=3.10,<4` listed | VERIFIED | Line 6: `apscheduler>=3.10,<4` present |
| `tests/test_scores.py` | 11 unit tests covering all requirement IDs; min 80 lines | VERIFIED | 282 lines; 11 test functions; non-trivial staleness tests confirmed |
| `app.py` | BackgroundScheduler with 3 jobs; `mark_risk_scores_stale` in `_run_ingest()` | VERIFIED | `from apscheduler.schedulers.background import BackgroundScheduler` at line 39; scheduler at lines 134-158; ingest hook at lines 342-345; ranking endpoint at lines 290-320 |
| `screening.py` | `compute_vessel_score()` + `score_is_stale()` + updated `screen_vessel_detail()` | VERIFIED | Functions at lines 183 and 165 respectively; staleness fallback at lines 368-377 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `db/schema.py init_db()` | `db/scores.py init_scores_tables()` | Local import + explicit call at end of `init_db()` | WIRED | `schema.py` line 49-50: `from .scores import init_scores_tables; init_scores_tables()` |
| `db/__init__.py` | `db/scores.py` | `from .scores import (...)` | WIRED | `__init__.py` lines 74-79: all 8 functions imported |
| `db/scores.py` | `db/connection.py` | `from .connection import _BACKEND, _conn, _cursor, _rows, _ph, _jp` | WIRED | `scores.py` line 23: exact import confirmed |
| `app.py BackgroundScheduler` | `refresh_all_scores_job, archive_ais_job, prune_history_job` | `_scheduler.add_job()` | WIRED | `app.py` lines 135-158: 3 `add_job()` calls with correct triggers |
| `app.py _do_score_refresh()` | `db.upsert_vessel_score` + `screening.compute_vessel_score()` | Direct calls inside `for row in rows` loop | WIRED | Lines 99-101: `fresh = screening.compute_vessel_score(imo)` then `db.upsert_vessel_score(imo, fresh)` |
| `screening.screen_vessel_detail()` | `screening.compute_vessel_score()` | Called when `db.get_vessel_score()` returns None or stale | WIRED | `screening.py` lines 369-372: stale/missing guard with direct `compute_vessel_score()` call |
| `screening.compute_vessel_score()` | `db.upsert_vessel_score()` | Persisted by `screen_vessel_detail()` after compute | WIRED | `screening.py` line 372: `db.upsert_vessel_score(imo_clean, fresh)` |
| `app._run_ingest()` | `db.mark_risk_scores_stale()` | Called with IMOs extracted from entries after upsert | WIRED | `app.py` lines 343-345: extraction + conditional call |
| `app.api_vessels_ranking()` | `db.get_all_vessel_scores()` | Direct call — no per-vessel loop | WIRED | `app.py` line 309: `rows = db.get_all_vessel_scores()` — only DB call in handler |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| DB-1 | 02-01 | Pre-computed composite risk scores; `vessel_scores` table with `composite_score`, `indicator_json` (JSONB), `computed_at`; APScheduler refreshes every 15 min | SATISFIED | `vessel_scores` table created by `init_scores_tables()`; upsert/get/mark-stale all implemented; scheduler job `score_refresh` fires every 15 min |
| DB-2 | 02-01 | Risk score history; `vessel_score_history` table; one row per vessel per refresh; 90-day retention | SATISFIED | `vessel_score_history` DDL confirmed; `append_score_history()` and `prune_score_history(90)` both implemented and tested |
| DB-4 | 02-01, 02-03 | Score freshness metadata; `computed_at` stored on every score row; staleness fallback in `screening.py` re-computes on-demand if score is >30 min old | SATISFIED | `computed_at` in schema; `score_is_stale()` checks age against `SCORE_STALENESS_MINUTES=30`; `screen_vessel_detail()` recomputes on stale/missing |
| DB-5 | 02-01, 02-03 | Score invalidation after ingest; ingest functions mark affected vessel scores stale | SATISFIED | `_run_ingest()` in `app.py` calls `db.mark_risk_scores_stale()` with extracted IMOs after every `upsert_sanctions_entries()` call |
| INF-1 | 02-01, 02-04 | N+1 query elimination; no per-vessel SELECT loops in dashboard or vessel ranking endpoints | SATISFIED | `get_all_vessel_scores()` is a single 3-table JOIN; `/api/vessels/ranking` makes only one DB call; N+1 audit comment in `app.py` lines 286-289 confirms all multi-vessel endpoints are batch-query only |
| INF-2 | 02-01, 02-02 | AIS position archival strategy; APScheduler job deletes `ais_positions` rows older than 90 days; daily | SATISFIED | `archive_old_ais_positions(days=90)` in `db/scores.py`; `_archive_ais_job()` registered with cron trigger `hour=3, minute=0`; `test_archive_old_ais_positions` passes |

All 6 requirements: SATISFIED.

---

### Anti-Patterns Found

None. Scan of `db/scores.py`, `screening.py`, and `app.py` found:
- No TODO/FIXME/HACK/PLACEHOLDER comments
- No stub implementations (`return null`, `return {}`, `return []`)
- No empty handlers
- No console.log-only implementations
- The `placeholders` variable in `db/scores.py` line 227 is a legitimate SQL placeholder string, not a code stub

---

### Human Verification Required

**1. Advisory lock behaviour under 2-worker Gunicorn load**
- **Test:** Deploy to Railway with 2 Gunicorn workers; trigger a manual score refresh cycle; observe logs from both workers.
- **Expected:** Only one worker logs `[scheduler] score refresh complete: N vessels refreshed`; the other logs nothing (returns early from advisory lock check).
- **Why human:** Requires live Railway deployment and multi-worker log inspection; cannot verify programmatically in single-process dev environment.

**2. Scheduler keeps running after `screen_vessel_detail()` exception**
- **Test:** Call `/api/screen/<imo>` for an IMO that causes a DB error; wait for next 15-min job cycle; confirm scheduler still fires.
- **Expected:** Job cycle completes without crashing app; individual vessel error is logged but does not propagate.
- **Why human:** Requires real DB state and timing; `try/except` coverage confirmed in code but resilience is a runtime property.

---

### Gaps Summary

No gaps. All 16 observable truths verified. All 6 requirement IDs (DB-1, DB-2, DB-4, DB-5, INF-1, INF-2) are satisfied by concrete implementation evidence. All key links are wired. Test suite passes 15/15 (when using the correct Python interpreter with project deps installed — `C:\Users\ardal\AppData\Local\Python\bin\python3.exe`).

**Note on test environment:** The default `python` at `C:\Python314\python.exe` lacks `pydantic` and `apscheduler`, causing 2 staleness tests to fail with `ModuleNotFoundError: No module named 'pydantic'`. This is an environment issue, not an implementation issue — the same tests pass when run with the project's Python at `C:\Users\ardal\AppData\Local\Python\bin\python3.exe`. The implementation is correct.

---

_Verified: 2026-03-04_
_Verifier: Claude (gsd-verifier)_
