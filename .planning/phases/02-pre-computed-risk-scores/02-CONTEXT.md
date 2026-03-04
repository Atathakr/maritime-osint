# Phase 2: Pre-Computed Risk Scores — Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a `vessel_scores` table that stores pre-computed composite risk scores and indicator breakdowns. Refresh every 15 minutes via APScheduler. Add a `vessel_score_history` table with 90-day retention. Add a staleness fallback to `screening.py` that recomputes on-demand if a score is >30 min old. Mark scores stale when ingest runs. Eliminate N+1 query patterns in the dashboard/vessel-ranking endpoints. Add a daily APScheduler job to archive `ais_positions` rows older than 90 days. **No new UI in this phase — that is Phase 5.**

</domain>

<decisions>
## Implementation Decisions

### indicator_json JSONB schema

Store **all 31 indicators** (fired and not-fired) in a single dict keyed by indicator ID:

```json
{
  "IND1":  {"pts": 30, "fired": true,  "fired_at": "2026-03-04T14:00:00Z"},
  "IND7":  {"pts": 45, "fired": true,  "fired_at": "2026-03-04T09:00:00Z"},
  "IND8":  {"pts": 0,  "fired": false},
  "IND9":  {"pts": 0,  "fired": false},
  "IND10": {"pts": 16, "fired": true,  "fired_at": "2026-03-04T11:30:00Z"},
  ...all 31 indicators...
}
```

Rules:
- **Key:** indicator ID string (`"IND1"`, `"IND7"`, ..., `"IND31"`)
- **Fired indicator fields:** `pts` (int), `fired` (true), `fired_at` (ISO 8601 UTC string)
- **Not-fired indicator fields:** `pts` (0), `fired` (false) — no `fired_at` key
- **Coverage:** All 31 indicators always present, even if pts=0. Phase 5 renders the full breakdown table directly from JSONB without merging against a hardcoded config.

### Staleness fallback behavior

When `screening.py` serves a vessel profile and the cached score is >30 minutes old:

1. **Block and recompute inline** — always return fresh data, never stale
2. **Persist the recomputed score** to `vessel_scores` (`upsert_vessel_score()`) with the new `computed_at` timestamp
3. Next request gets the cached result; no repeated recompute penalty

Staleness threshold: `SCORE_STALENESS_MINUTES = 30` — hardcoded constant in `db/scores.py` (no env var).

```python
# screening.py — on-demand fallback pattern
score_row = db.get_vessel_score(imo)
if score_row is None or score_is_stale(score_row, SCORE_STALENESS_MINUTES):
    fresh = compute_score(vessel_detail)
    db.upsert_vessel_score(imo, fresh)  # persist
    return fresh
return score_row
```

### Gunicorn multi-worker double-refresh (Claude's discretion)

Not discussed — handled by implementation. Recommended approach: **PostgreSQL advisory lock** (`pg_try_advisory_lock(42)`) wrapping the APScheduler job body. Each worker races to acquire the lock; the winner runs the refresh; the others skip silently. This is cleaner than reducing to 1 worker (which would hurt throughput) and simpler than a separate scheduler process. Lock ID 42 is arbitrary — document it in a comment.

```python
# APScheduler job with advisory lock
def refresh_all_scores_job():
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(42)")
            if not cur.fetchone()[0]:
                return  # another worker is running the job
        _do_refresh()
        # lock released when connection closes
```

For SQLite (local dev): advisory lock is skipped — `_BACKEND == 'sqlite'` check bypasses the lock entirely. APScheduler runs normally.

### Scheduler schedule

- **Score refresh:** every 15 minutes (`trigger='interval', minutes=15`)
- **AIS archival:** once daily at 03:00 UTC (`trigger='cron', hour=3`)
- **History pruning:** once daily at 03:05 UTC (run after archival, same scheduler)

### vessel_scores table schema

```sql
CREATE TABLE IF NOT EXISTS vessel_scores (
    imo_number      TEXT PRIMARY KEY,
    composite_score INTEGER NOT NULL DEFAULT 0,
    is_sanctioned   INTEGER NOT NULL DEFAULT 0,  -- 0/1 (SQLite-compatible)
    indicator_json  TEXT NOT NULL DEFAULT '{}',  -- JSONB in Postgres, TEXT in SQLite
    computed_at     TEXT NOT NULL,               -- ISO 8601 UTC
    is_stale        INTEGER NOT NULL DEFAULT 0   -- 1 = marked stale by ingest
);
```

### vessel_score_history table schema

```sql
CREATE TABLE IF NOT EXISTS vessel_score_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,  -- SERIAL in Postgres
    imo_number      TEXT NOT NULL,
    composite_score INTEGER NOT NULL,
    is_sanctioned   INTEGER NOT NULL DEFAULT 0,
    computed_at     TEXT NOT NULL
    -- No indicator_json in history — keep history rows small
);
CREATE INDEX IF NOT EXISTS idx_score_history_imo ON vessel_score_history(imo_number);
CREATE INDEX IF NOT EXISTS idx_score_history_computed_at ON vessel_score_history(computed_at);
```

Retention: delete rows WHERE computed_at < NOW() - 90 days (daily job).

### Score invalidation scope

When `upsert_sanctions_entries()` or OFAC ingest runs:
- Call `db.mark_risk_scores_stale(imo_numbers: list[str])` for affected IMOs only
- Sets `is_stale = 1` on the matching `vessel_scores` rows
- The staleness check in `screening.py` treats `is_stale = 1` the same as age > 30 min → triggers on-demand recompute
- The scheduler's next 15-min run also picks up stale rows

### N+1 elimination scope

The dashboard vessel listing endpoint must use a single JOIN/batch query:
- `SELECT vs.imo_number, vs.composite_score, vs.is_sanctioned, vs.computed_at, vc.vessel_name, vc.flag_state, vc.vessel_type, vc.last_seen FROM vessel_scores vs JOIN vessels_canonical vc USING (imo_number) ORDER BY vs.composite_score DESC`
- No Python-level per-vessel SELECT loops for any multi-vessel response

The map endpoint (`map_data.get_map_vessels_raw()`) already uses a batch query — **no changes needed there in Phase 2**.

</decisions>

<code_context>
## Existing Code Insights

### Current risk scoring (on-demand in screening.py)
Located in `screening.screen_vessel_detail()` — the 0-99 composite formula using:
- IND1 (dark periods): `min(dp_count × 10, 40)`
- IND7 (STS events): `min(sts_count × 15, 45)`
- IND8 (STS in hazard zone): `min(sts_zone_count × 5, 10)`
- IND17 (flag risk tier): `flag_tier × 7` (max 21)
- IND15 (ownership hops): `min(hop_count × 8, 16)`
- IND10 (AIS spoofing): `min(spoof_count × 8, 24)`
- IND29 (port calls in high-risk ports): `min(port_count × 20, 40)`
- IND9 (loitering): `min(loiter_count × 5, 15)`
- Sanctioned → 100 (hard ceiling); else cap at 99

Phase 2 extracts this logic into a reusable `compute_vessel_score(imo)` function (called by both the scheduler and the staleness fallback).

### map_data.py — already batched, no N+1
`get_map_vessels()` calls `db.get_map_vessels_raw()` — single batch query returning all vessel data. Map uses a qualitative CRITICAL/HIGH/MEDIUM/LOW/NONE risk level from {dark periods, STS, sanctions}. This is **separate** from the 0-99 composite score. The map endpoint does NOT need changes in Phase 2. Phase 5 wires the numeric score into map popups.

### db/scores.py — placeholder stub
Currently a placeholder stub (module docstring + TODO). Phase 2 fills in:
- `init_scores_tables()` — DDL for vessel_scores + vessel_score_history
- `upsert_vessel_score(imo, score_data)` — insert/update vessel_scores
- `get_vessel_score(imo)` → dict | None
- `get_all_vessel_scores()` → list[dict] (for dashboard batch query)
- `mark_risk_scores_stale(imo_numbers)` — sets is_stale=1
- `append_score_history(imo, score_data)` — inserts into history
- `prune_score_history(days=90)` — deletes old history rows
- `archive_old_ais_positions(days=90)` — deletes old ais_positions rows

### app.py — no APScheduler yet
`app.py` starts db (init_db), optionally starts ais_listener. No scheduler present. APScheduler is wired in Plan 02-02 after the table DDL is in place.

### Caller pattern (unchanged from Phase 1)
All callers use `import db; db.fn()`. New scores functions will be re-exported from `db/__init__.py` via:
```python
from .scores import (
    init_scores_tables, upsert_vessel_score, get_vessel_score,
    get_all_vessel_scores, mark_risk_scores_stale,
    append_score_history, prune_score_history,
    archive_old_ais_positions
)  # noqa: F401
```

The `db/__init__.py` scores block is currently commented — uncomment it in Plan 02-01.

</code_context>

<specifics>
## Specific Ideas

- The `fired_at` timestamp for each indicator should come from the most recent detection record in the findings tables (e.g., `dark_periods.detected_at`, `sts_transfers.detected_at`). The score computation function queries these when building `indicator_json`.
- The advisory lock ID (42) should be documented in a comment: `SCHEDULER_ADVISORY_LOCK_ID = 42`.
- The staleness check should handle the `score_row is None` case (vessel has no score yet) identically to "stale" — triggers an immediate recompute + insert.

</specifics>

<deferred>
## Deferred Ideas

- Map popup numeric score display (Phase 5 / FE-2)
- Raw indicator values stored in indicator_json (e.g., `raw_value: 2` for dark period count) — skipped, `pts + fired_at` sufficient for Phase 5 FE-4
- Configurable staleness threshold via env var — not needed, hardcoded is fine

</deferred>

---

*Phase: 02-pre-computed-risk-scores*
*Context gathered: 2026-03-04*
