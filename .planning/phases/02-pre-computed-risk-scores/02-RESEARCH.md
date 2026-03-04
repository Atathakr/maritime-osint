# Phase 2: Pre-Computed Risk Scores — Research

**Researched:** 2026-03-04
**Domain:** APScheduler 3.x, PostgreSQL advisory locks, dual-backend UPSERT, JSONB persistence, N+1 query elimination, AIS archival
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **indicator_json schema:** All 31 indicators always present in one dict keyed by indicator ID. Fired: `{pts, fired: true, fired_at}`. Not-fired: `{pts: 0, fired: false}`. No `fired_at` key on not-fired entries.
- **Staleness fallback:** Block + recompute inline + persist to `vessel_scores` via `upsert_vessel_score()`. `SCORE_STALENESS_MINUTES = 30` hardcoded in `db/scores.py`. No env var.
- **Multi-worker protection:** `pg_try_advisory_lock(42)` wrapping APScheduler job body. SQLite skips the lock (`_BACKEND == 'sqlite'` check). Lock constant: `SCHEDULER_ADVISORY_LOCK_ID = 42`.
- **Scheduler schedule:** Score refresh every 15 minutes (`trigger='interval', minutes=15`). AIS archival once daily at 03:00 UTC (`trigger='cron', hour=3`). History pruning at 03:05 UTC.
- **vessel_scores schema:** `imo_number TEXT PK`, `composite_score INTEGER`, `is_sanctioned INTEGER 0/1`, `indicator_json TEXT` (JSONB in PG), `computed_at TEXT` (ISO 8601 UTC), `is_stale INTEGER DEFAULT 0`.
- **vessel_score_history schema:** `id INTEGER PK AUTOINCREMENT`, `imo_number TEXT`, `composite_score INTEGER`, `is_sanctioned INTEGER`, `computed_at TEXT`. Indexed on `imo_number` and `computed_at`. No indicator_json.
- **N+1 scope:** Dashboard listing endpoint — single JOIN query. Map endpoint already batched — no changes in Phase 2.
- **No new UI in Phase 2.** Map numeric score display deferred to Phase 5.

### Claude's Discretion

- None explicitly stated beyond the above. Implementation details of `compute_vessel_score(imo)` function (called by both scheduler and staleness fallback) are Claude's discretion. The advisory lock release mechanism (session vs transaction level) is an implementation detail to be decided.

### Deferred Ideas (OUT OF SCOPE)

- Map popup numeric score display (Phase 5 / FE-2)
- Raw indicator values in indicator_json (e.g. `raw_value: 2` for dark period count)
- Configurable staleness threshold via env var
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DB-1 | `vessel_scores` table; APScheduler refreshes every 15 min; composite_score + indicator_json stored | APScheduler 3.x BackgroundScheduler confirmed; dual-backend DDL pattern established from Phase 1 |
| DB-2 | `vessel_score_history` table; one row per vessel per refresh; 90-day retention | DDL pattern from Phase 1; daily pruning job added to APScheduler |
| DB-4 | `computed_at` stored on every score row; staleness fallback in `screening.py` recomputes if >30 min old | `score_is_stale()` helper function; upsert on staleness hit |
| DB-5 | Ingest functions mark affected vessel scores stale after `upsert_sanctions_entries`; next refresh rescores | `mark_risk_scores_stale(imo_numbers)` function; called inside ingest path in `db/vessels.py` or `app.py` |
| INF-1 | No per-vessel SELECT loops in dashboard or vessel ranking endpoints; batch queries for all multi-vessel fetches | `get_all_vessel_scores()` returns a single JOIN result; documented anti-pattern to avoid |
| INF-2 | APScheduler job deletes `ais_positions` rows older than 90 days; runs daily | `archive_old_ais_positions(days=90)` function; cron trigger at 03:00 UTC |
</phase_requirements>

---

## Summary

Phase 2 adds pre-computed risk scores as a background-maintained cache layer between the expensive on-demand `screen_vessel_detail()` computation and analyst-facing endpoints. The core work is: (1) implement `db/scores.py` with DDL and CRUD for `vessel_scores` + `vessel_score_history`, (2) extract the composite score formula from `screening.py` into a reusable `compute_vessel_score(imo)` function, (3) wire APScheduler into `app.py` to run the refresh and archival jobs, (4) add a staleness fallback in `screening.py`, (5) replace the dashboard N+1 pattern with a batched JOIN, and (6) expose the scores block from `db/__init__.py`.

The dual-backend constraint (SQLite local dev, PostgreSQL production) is the main complexity driver. Every function in `db/scores.py` must handle both backends using the established `_BACKEND`, `_ph()`, `_jp()`, `_conn()` pattern from Phase 1. The PostgreSQL advisory lock for multi-worker safety has a critical session-vs-transaction-level nuance: `pg_try_advisory_lock(42)` is session-level and must be explicitly released with `pg_advisory_unlock(42)` — it is NOT automatically released on transaction commit. The pattern from CONTEXT.md ("lock released when connection closes") relies on connection pool return to release it, which works because psycopg2's `ThreadedConnectionPool.putconn()` returns the connection to the pool without closing it. This means the lock could theoretically persist across requests. The safer explicit pattern is to use `pg_try_advisory_xact_lock(42)` which auto-releases on transaction commit/rollback.

APScheduler 3.x (current: 3.11.2) is the confirmed library. It is not yet in `requirements.txt` and must be added. The critical Gunicorn multi-worker problem is real: each Gunicorn worker will start its own `BackgroundScheduler`, causing duplicate job runs. The PostgreSQL advisory lock approach in CONTEXT.md is the correct resolution for the production case.

**Primary recommendation:** Add `apscheduler>=3.10,<4` to `requirements.txt`. Use `BackgroundScheduler` started at module level in `app.py` with `daemon=True`. Use `pg_try_advisory_xact_lock(42)` (transaction-level, not session-level) to avoid requiring an explicit unlock call.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| APScheduler | 3.11.2 (latest 3.x) | Background job scheduling | Mature, no broker required, thread-safe `BackgroundScheduler`, works inside Flask/Gunicorn; 4.x is async-only and incompatible with sync psycopg2 |
| psycopg2-binary | >=2.9.0 (already in requirements.txt) | PostgreSQL advisory lock execution | Already in stack; `pg_try_advisory_xact_lock` executed via normal cursor |
| json (stdlib) | stdlib | JSONB serialization for indicator_json | Already used throughout db/ package via `_jp()` helper |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| datetime (stdlib) | stdlib | ISO 8601 UTC timestamp generation for `computed_at` | `datetime.utcnow().isoformat() + 'Z'` or `datetime.now(timezone.utc).isoformat()` |
| threading (stdlib) | stdlib | APScheduler uses internally | No direct use needed; BackgroundScheduler manages its own threads |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| APScheduler 3.x | APScheduler 4.x | 4.x is async-first; incompatible with sync psycopg2 and existing Flask setup |
| APScheduler 3.x | Celery + Redis | Requires a new Railway service (Redis); adds operational cost; overkill for 2 jobs |
| APScheduler 3.x | Flask-APScheduler | Thin wrapper; adds a dependency; official docs recommend direct APScheduler for simple cases |
| pg_try_advisory_xact_lock | pg_try_advisory_lock (session) | Session-level lock requires explicit pg_advisory_unlock; transaction-level auto-releases on commit — simpler |

**Installation:**
```bash
pip install "apscheduler>=3.10,<4"
```

Add to `requirements.txt`:
```
apscheduler>=3.10,<4
```

---

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
db/
└── scores.py          # FILL IN: init_scores_tables, upsert_vessel_score,
                       #   get_vessel_score, get_all_vessel_scores,
                       #   mark_risk_scores_stale, append_score_history,
                       #   prune_score_history, archive_old_ais_positions
db/__init__.py         # Uncomment scores block (add 8 re-exports)
db/schema.py           # Call init_scores_tables() from init_db()
screening.py           # Extract compute_vessel_score(); add staleness fallback
app.py                 # Wire APScheduler; start scheduler after db.init_db()
requirements.txt       # Add apscheduler>=3.10,<4
```

### Pattern 1: Dual-Backend DDL for vessel_scores

**What:** Follow the established `_init_postgres` / `_init_sqlite` split already in `db/schema.py`. Add `init_scores_tables()` in `db/scores.py` and call it from `init_db()` in `db/schema.py`.

**When to use:** Any new table that must work on both backends.

**Example (db/scores.py):**
```python
# Source: Phase 1 db/schema.py pattern (established in codebase)
from .connection import _BACKEND, _conn, _ph, _jp

SCORE_STALENESS_MINUTES = 30
SCHEDULER_ADVISORY_LOCK_ID = 42

def init_scores_tables() -> None:
    """Create vessel_scores and vessel_score_history tables (idempotent)."""
    with _conn() as conn:
        c = conn.cursor()
        if _BACKEND == "postgres":
            _init_scores_postgres(c)
        else:
            _init_scores_sqlite(c)

def _init_scores_postgres(c) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_scores (
            imo_number      VARCHAR(20) PRIMARY KEY,
            composite_score INTEGER      NOT NULL DEFAULT 0,
            is_sanctioned   SMALLINT     NOT NULL DEFAULT 0,
            indicator_json  JSONB        NOT NULL DEFAULT '{}',
            computed_at     TIMESTAMPTZ  NOT NULL,
            is_stale        SMALLINT     NOT NULL DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_score_history (
            id              BIGSERIAL PRIMARY KEY,
            imo_number      VARCHAR(20) NOT NULL,
            composite_score INTEGER     NOT NULL,
            is_sanctioned   SMALLINT    NOT NULL DEFAULT 0,
            computed_at     TIMESTAMPTZ NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_vsh_imo ON vessel_score_history(imo_number)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vsh_at  ON vessel_score_history(computed_at DESC)")

def _init_scores_sqlite(c) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_scores (
            imo_number      TEXT PRIMARY KEY,
            composite_score INTEGER NOT NULL DEFAULT 0,
            is_sanctioned   INTEGER NOT NULL DEFAULT 0,
            indicator_json  TEXT    NOT NULL DEFAULT '{}',
            computed_at     TEXT    NOT NULL,
            is_stale        INTEGER NOT NULL DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vessel_score_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            imo_number      TEXT    NOT NULL,
            composite_score INTEGER NOT NULL,
            is_sanctioned   INTEGER NOT NULL DEFAULT 0,
            computed_at     TEXT    NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_vsh_imo ON vessel_score_history(imo_number)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vsh_at  ON vessel_score_history(computed_at DESC)")
```

### Pattern 2: Dual-Backend UPSERT for vessel_scores

**What:** PostgreSQL has `ON CONFLICT DO UPDATE`. SQLite supports the same syntax since 3.24. Use it — no `INSERT OR REPLACE` which would reset defaults.

**Example:**
```python
# Source: Phase 1 db/vessels.py upsert pattern + PostgreSQL ON CONFLICT syntax
def upsert_vessel_score(imo: str, score_data: dict) -> None:
    """
    Insert or update a vessel_scores row.
    score_data keys: composite_score, is_sanctioned, indicator_json (dict), computed_at (str)
    """
    import json as _json
    from datetime import timezone, datetime
    p  = "?" if _BACKEND == "sqlite" else "%s"
    jp = _jp()  # includes ::jsonb cast for postgres
    computed_at = score_data.get("computed_at") or datetime.now(timezone.utc).isoformat()

    with _conn() as conn:
        c = conn.cursor()
        c.execute(f"""
            INSERT INTO vessel_scores
                (imo_number, composite_score, is_sanctioned, indicator_json, computed_at, is_stale)
            VALUES ({p}, {p}, {p}, {jp}, {p}, 0)
            ON CONFLICT (imo_number) DO UPDATE SET
                composite_score = EXCLUDED.composite_score,
                is_sanctioned   = EXCLUDED.is_sanctioned,
                indicator_json  = EXCLUDED.indicator_json,
                computed_at     = EXCLUDED.computed_at,
                is_stale        = 0
        """, (
            imo,
            score_data["composite_score"],
            int(score_data.get("is_sanctioned", False)),
            _json.dumps(score_data["indicator_json"]),
            computed_at,
        ))
```

### Pattern 3: APScheduler BackgroundScheduler in app.py

**What:** Instantiate `BackgroundScheduler` after `db.init_db()`, add jobs, start. Wrap with `daemon=True` so it doesn't block shutdown.

**Example:**
```python
# Source: APScheduler 3.x official user guide
# https://apscheduler.readthedocs.io/en/3.x/userguide.html
from apscheduler.schedulers.background import BackgroundScheduler

# After db.init_db() in app.py:
_scheduler = BackgroundScheduler(daemon=True)
_scheduler.add_job(
    refresh_all_scores_job,
    trigger='interval',
    minutes=15,
    id='score_refresh',
    replace_existing=True,
)
_scheduler.add_job(
    archive_ais_job,
    trigger='cron',
    hour=3,
    id='ais_archive',
    replace_existing=True,
)
_scheduler.add_job(
    prune_history_job,
    trigger='cron',
    hour=3,
    minute=5,
    id='history_prune',
    replace_existing=True,
)
_scheduler.start()
```

### Pattern 4: PostgreSQL Advisory Lock (transaction-level) in Scheduler Job

**What:** `pg_try_advisory_xact_lock(N)` — acquires a transaction-scoped advisory lock. Auto-releases on transaction commit or rollback. No explicit unlock needed. Preferred over session-level `pg_try_advisory_lock` because the connection goes back to the pool with no lingering lock state.

**Critical distinction:** CONTEXT.md shows `pg_try_advisory_lock(42)` (session-level). Recommend `pg_try_advisory_xact_lock(42)` instead. Both return boolean; difference is auto-release semantics.

```python
# Source: PostgreSQL docs https://www.postgresql.org/docs/current/explicit-locking.html
SCHEDULER_ADVISORY_LOCK_ID = 42

def refresh_all_scores_job() -> None:
    """APScheduler entry-point. Uses advisory lock to prevent duplicate runs across workers."""
    if _BACKEND == "postgres":
        with _conn() as conn:
            c = conn.cursor()
            c.execute("SELECT pg_try_advisory_xact_lock(%s)", (SCHEDULER_ADVISORY_LOCK_ID,))
            if not c.fetchone()[0]:
                return  # another worker already holds the lock
            _do_refresh_all_scores()
            # Lock auto-released on transaction commit (end of 'with _conn()' block)
    else:
        # SQLite: no locking needed; single process
        _do_refresh_all_scores()
```

### Pattern 5: Extracting compute_vessel_score() from screening.py

**What:** `screen_vessel_detail()` contains the full composite score formula inline. Extract it into a standalone function that accepts `imo: str` and returns `dict` with `composite_score`, `is_sanctioned`, `indicator_json`, `computed_at`.

**Key implementation constraint:** The existing formula queries multiple db functions using MMSI as the primary key for AIS signals (dark_periods, sts_events, ais_anomalies), but `vessel_scores` is keyed by `imo_number`. The function must resolve MMSI from the vessel record before querying AIS findings tables.

```python
# screening.py — extracted compute function
def compute_vessel_score(imo: str) -> dict:
    """
    Compute composite risk score and indicator breakdown for a vessel.
    Returns dict with: composite_score, is_sanctioned, indicator_json, computed_at
    Called by: APScheduler refresh job AND staleness fallback in screen_vessel_detail()
    """
    from datetime import timezone, datetime
    # ... resolve vessel, mmsi, flag, etc. (same logic as screen_vessel_detail) ...
    # ... build indicator_json with all 31 indicators ...
    return {
        "composite_score": risk_score,
        "is_sanctioned":   bool(processed_hits),
        "indicator_json":  indicator_json,   # dict: {IND1: {pts, fired, fired_at?}, ...}
        "computed_at":     datetime.now(timezone.utc).isoformat(),
    }
```

### Pattern 6: Staleness Check in screening.py

**What:** Before computing on-demand, check if a fresh score is cached. Recompute and persist if stale or missing.

```python
# screening.py — staleness fallback
def score_is_stale(score_row: dict, minutes: int = SCORE_STALENESS_MINUTES) -> bool:
    """Return True if score is older than `minutes` or if is_stale flag is set."""
    from datetime import timezone, datetime, timedelta
    if score_row.get("is_stale"):
        return True
    computed_at_str = score_row.get("computed_at")
    if not computed_at_str:
        return True
    try:
        computed_at = datetime.fromisoformat(computed_at_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - computed_at > timedelta(minutes=minutes)
    except (ValueError, TypeError):
        return True

def screen_vessel_detail(imo: str) -> schemas.VesselDetail:
    imo_clean = re.sub(r"\D", "", imo)
    score_row = db.get_vessel_score(imo_clean)
    if score_row is None or score_is_stale(score_row):
        fresh = compute_vessel_score(imo_clean)
        db.upsert_vessel_score(imo_clean, fresh)
        score_row = fresh
    # ... build VesselDetail using score_row ...
```

### Pattern 7: Dashboard Batch Query (N+1 Elimination)

**What:** Replace any per-vessel SELECT loop in the dashboard listing endpoint with a single JOIN between `vessel_scores` and `vessels_canonical`.

```sql
-- Source: CONTEXT.md — locked decision
SELECT
    vs.imo_number,
    vs.composite_score,
    vs.is_sanctioned,
    vs.computed_at,
    vc.entity_name   AS vessel_name,
    vc.flag_normalized AS flag_state,
    vc.vessel_type,
    av.last_seen
FROM vessel_scores vs
JOIN vessels_canonical vc USING (imo_number)
LEFT JOIN ais_vessels av ON vc.mmsi = av.mmsi
ORDER BY vs.composite_score DESC
```

Exposed as `get_all_vessel_scores()` in `db/scores.py`.

### Pattern 8: Score Invalidation Hook in ingest path

**What:** After `upsert_sanctions_entries()` in `db/vessels.py` (or the ingest endpoint in `app.py`), call `mark_risk_scores_stale()` for affected IMOs.

**Where to add it:** The cleanest hook is in `app.py` `_run_ingest()` after a successful `db.upsert_sanctions_entries()` call, since that is where IMOs are already available.

```python
# app.py _run_ingest() — after upsert_sanctions_entries
affected_imos = [e.get("imo_number") for e in entries if e.get("imo_number")]
if affected_imos:
    db.mark_risk_scores_stale(affected_imos)
```

### Anti-Patterns to Avoid

- **Session-level advisory lock without explicit unlock:** `pg_try_advisory_lock` is session-scoped; if the job function raises an exception and the connection is returned to the pool, the lock stays held until that connection is reused and `pg_advisory_unlock` is called. Use `pg_try_advisory_xact_lock` instead.
- **Starting BackgroundScheduler before `init_db()`:** Tables must exist before the first job fires. Start the scheduler after `db.init_db()`.
- **Starting BackgroundScheduler in module-level code that runs at import time:** Gunicorn imports `app.py` in the master process before forking; if the scheduler starts at import time, all workers inherit it. Wrap in `if __name__ == '__main__':` guard or in an app factory pattern. Safest: start the scheduler at the bottom of the module-level `app.py` setup block (after `db.init_db()`), not inside an `if __name__ == '__main__':` block — this ensures it starts in the worker process, not the master.
- **JSON decode in every read:** `indicator_json` is stored as TEXT in SQLite. `get_vessel_score()` must `json.loads()` the field before returning. In PostgreSQL with JSONB, psycopg2 returns a dict automatically. Normalize the output to always return a dict.
- **Computing fired_at from scoring formula only:** `fired_at` for each indicator comes from the most recent detection record in the findings tables (e.g. `dark_periods.gap_start`, `sts_events.event_ts`). The `compute_vessel_score()` function must query these timestamps — it cannot reconstruct them from the formula alone.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Background job scheduling | Custom threading.Timer loop or cron subprocess | APScheduler 3.x BackgroundScheduler | Thread management, missed-fire handling, cron expression parsing, graceful shutdown — all handled |
| Advisory lock management | Custom locking table in DB | `pg_try_advisory_xact_lock()` | Zero-table-scan; atomic; PostgreSQL built-in; auto-release |
| JSON serialization for JSONB | Custom text escaping | `json.dumps()` + `_jp()` helper | `_jp()` already in codebase; adds `::jsonb` cast for PG automatically |
| UPSERT logic | SELECT + INSERT OR UPDATE branches | `ON CONFLICT (imo_number) DO UPDATE SET` | Atomic; both PG and SQLite 3.24+ support this syntax |
| Staleness timestamp parsing | Custom time string parsing | `datetime.fromisoformat()` (Python 3.11+ handles 'Z') | Built-in stdlib; no extra deps |

**Key insight:** All the hard scheduling, locking, and persistence problems have solved, well-tested library solutions. The custom work in Phase 2 is the domain logic: correctly assembling all 31 indicators with their timestamps and mapping them to the pre-determined formula.

---

## Common Pitfalls

### Pitfall 1: Advisory Lock Scope Confusion (Session vs Transaction)

**What goes wrong:** Using `pg_try_advisory_lock(42)` (session-level) in a job that gets a connection from a pool. If the job raises an exception, the connection is returned to the pool (not closed), and the advisory lock persists on that connection. The next job run gets a different connection and acquires the lock fine — but the first connection still holds it. Eventually the pool is exhausted or duplicate runs happen.

**Why it happens:** Session-level advisory locks are not released on transaction commit; they're tied to the connection lifetime.

**How to avoid:** Use `pg_try_advisory_xact_lock(42)` instead. It auto-releases when the transaction commits or rolls back — which happens at the end of every `with _conn() as conn:` block in this codebase.

**Warning signs:** Score refresh appearing to run twice within a short window; "lock already held" log messages.

### Pitfall 2: MMSI vs IMO Key Mismatch in compute_vessel_score()

**What goes wrong:** `vessel_scores` is keyed by `imo_number`, but the AIS findings tables (`dark_periods`, `sts_events`, `ais_anomalies`, `loitering_events`, `port_calls`) are keyed by `mmsi`. The compute function must resolve the vessel's MMSI from either `vessels_canonical.mmsi` or `ais_vessels.mmsi` before querying findings.

**Why it happens:** The original `screen_vessel_detail()` resolves MMSI mid-function. When extracting `compute_vessel_score(imo)`, this MMSI resolution step must be carried over.

**How to avoid:** At the top of `compute_vessel_score()`, call `db.get_vessel(imo)` then `db.get_ais_vessel_by_imo(imo)` as fallback, exactly as `screen_vessel_detail()` does. If MMSI is still None, AIS indicators contribute 0 pts.

**Warning signs:** All vessels getting 0 for IND1/IND7/IND8/IND9/IND10/IND29 despite having known AIS signals.

### Pitfall 3: indicator_json TEXT vs JSONB Read Path

**What goes wrong:** PostgreSQL with `JSONB` column returns a Python dict directly from psycopg2 RealDictCursor. SQLite TEXT column returns a string. If `get_vessel_score()` doesn't normalize the output, callers that access `score_row["indicator_json"]["IND1"]` will crash on SQLite with a TypeError.

**Why it happens:** Dual-backend inconsistency in type returned by cursor.

**How to avoid:** In `get_vessel_score()`, always parse: `row["indicator_json"] = json.loads(row["indicator_json"]) if isinstance(row["indicator_json"], str) else row["indicator_json"]`.

**Warning signs:** Local dev (SQLite) crashes with `TypeError: string indices must be integers` when accessing indicator_json keys.

### Pitfall 4: APScheduler Starting in Gunicorn Master Process

**What goes wrong:** If `BackgroundScheduler.start()` is called at module level (outside an if-guard), Gunicorn's master process starts the scheduler when it imports the module. Forked workers then each inherit a copy of the thread, which may fire duplicate jobs or have broken database connections.

**Why it happens:** Gunicorn imports the WSGI app module in the master before forking workers.

**How to avoid:** The advisory lock (Pattern 4) handles duplicate-run prevention. Additionally, verify the scheduler is started at module level (not in `if __name__ == '__main__':`) so it runs in each worker — the lock prevents both from executing the job body. The duplicate schedulers are expected and handled.

**Warning signs:** Log output showing "score refresh job" firing more than once per 15-minute window for the same batch of vessels.

### Pitfall 5: Stale is_stale Flag Not Cleared on Upsert

**What goes wrong:** `mark_risk_scores_stale()` sets `is_stale = 1`. If `upsert_vessel_score()` does not explicitly reset `is_stale = 0` in its `ON CONFLICT DO UPDATE SET`, stale rows stay stale forever.

**Why it happens:** UPSERT only sets what you explicitly tell it to.

**How to avoid:** In the `ON CONFLICT DO UPDATE SET` clause, always include `is_stale = 0` (as shown in Pattern 2 above).

**Warning signs:** Vessel profiles always recomputing on every request even after a successful scheduler refresh.

### Pitfall 6: datetime.utcnow() vs timezone-aware datetime

**What goes wrong:** `datetime.utcnow()` returns a naive datetime (no tzinfo). When parsed back with `datetime.fromisoformat()`, it won't compare correctly with timezone-aware datetimes. The staleness check can fail silently or raise TypeError.

**Why it happens:** Python datetime is naive by default; ISO 8601 with 'Z' suffix needs explicit handling.

**How to avoid:** Always use `datetime.now(timezone.utc).isoformat()` for `computed_at`. In Python 3.11+, `fromisoformat()` handles the 'Z' suffix. For Python 3.10 compatibility, use `.rstrip('Z')` before parsing and `.replace(tzinfo=timezone.utc)` after.

**Warning signs:** `score_is_stale()` always returns True (treating naive timestamps as very old) or raises `ValueError: Invalid isoformat string`.

---

## Code Examples

Verified patterns from official sources and established codebase patterns:

### APScheduler 3.x BackgroundScheduler Setup

```python
# Source: https://apscheduler.readthedocs.io/en/3.x/userguide.html
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(my_job, 'interval', minutes=15, id='my_job', replace_existing=True)
scheduler.add_job(daily_job, 'cron', hour=3, id='daily_job', replace_existing=True)
scheduler.start()
# scheduler runs in background thread; application continues
```

### PostgreSQL Transaction-Level Advisory Lock

```python
# Source: https://www.postgresql.org/docs/current/explicit-locking.html
# Section: 13.3.5. Advisory Locks
# pg_try_advisory_xact_lock: transaction-scope, auto-releases on commit/rollback

with _conn() as conn:  # commits at end of with block
    c = conn.cursor()
    c.execute("SELECT pg_try_advisory_xact_lock(%s)", (42,))
    if not c.fetchone()[0]:
        return  # lock not acquired; another worker is running
    # ... do work ...
    # lock released automatically when transaction commits
```

### get_all_vessel_scores() — Dashboard Batch Query

```python
# Source: CONTEXT.md locked decision + Phase 1 db/vessels.py _rows() pattern
def get_all_vessel_scores() -> list[dict]:
    """Single JOIN query for the vessel ranking endpoint. No N+1."""
    import json as _json
    p = "?" if _BACKEND == "sqlite" else "%s"
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT
                vs.imo_number,
                vs.composite_score,
                vs.is_sanctioned,
                vs.computed_at,
                vs.is_stale,
                vc.entity_name    AS vessel_name,
                vc.flag_normalized AS flag_state,
                vc.vessel_type,
                av.last_seen
            FROM vessel_scores vs
            JOIN vessels_canonical vc USING (imo_number)
            LEFT JOIN ais_vessels av ON vc.mmsi = av.mmsi
            ORDER BY vs.composite_score DESC
        """)
        rows = _rows(c)
    # Normalize indicator_json to dict on SQLite
    for row in rows:
        if isinstance(row.get("indicator_json"), str):
            row["indicator_json"] = _json.loads(row["indicator_json"])
    return rows
```

### mark_risk_scores_stale()

```python
def mark_risk_scores_stale(imo_numbers: list[str]) -> int:
    """Set is_stale=1 for the given IMO numbers. Returns count of rows updated."""
    if not imo_numbers:
        return 0
    p = "?" if _BACKEND == "sqlite" else "%s"
    placeholders = ", ".join([p] * len(imo_numbers))
    with _conn() as conn:
        c = conn.cursor()
        c.execute(
            f"UPDATE vessel_scores SET is_stale = 1 WHERE imo_number IN ({placeholders})",
            tuple(imo_numbers),
        )
        return c.rowcount
```

### prune_score_history() and archive_old_ais_positions()

```python
def prune_score_history(days: int = 90) -> int:
    """Delete vessel_score_history rows older than `days`."""
    if _BACKEND == "postgres":
        cutoff_expr = f"NOW() - INTERVAL '{days} days'"
        sql = f"DELETE FROM vessel_score_history WHERE computed_at < {cutoff_expr}"
        with _conn() as conn:
            c = conn.cursor()
            c.execute(sql)
            return c.rowcount
    else:
        sql = "DELETE FROM vessel_score_history WHERE computed_at < datetime('now', ?)"
        with _conn() as conn:
            c = conn.cursor()
            c.execute(sql, (f"-{days} days",))
            return c.rowcount

def archive_old_ais_positions(days: int = 90) -> int:
    """Delete ais_positions rows older than `days`."""
    if _BACKEND == "postgres":
        sql = f"DELETE FROM ais_positions WHERE position_ts < NOW() - INTERVAL '{days} days'"
        with _conn() as conn:
            c = conn.cursor()
            c.execute(sql)
            return c.rowcount
    else:
        sql = "DELETE FROM ais_positions WHERE position_ts < datetime('now', ?)"
        with _conn() as conn:
            c = conn.cursor()
            c.execute(sql, (f"-{days} days",))
            return c.rowcount
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| On-demand score compute in `screen_vessel_detail()` | Pre-computed score read from `vessel_scores`; compute only on staleness/miss | Phase 2 | Dashboard N+1 eliminated; profile load latency reduced |
| APScheduler 4.x (async-only) | APScheduler 3.x (sync, thread-based) | 4.x released 2024 | 3.x is still the right choice for sync Flask+psycopg2 stack |
| `datetime.utcnow()` (deprecated Python 3.12+) | `datetime.now(timezone.utc)` | Python 3.12 | Avoid DeprecationWarning; use timezone-aware datetimes |

**Deprecated/outdated:**
- `datetime.utcnow()`: Deprecated since Python 3.12. This project's Railway environment may run 3.11 or 3.12; use `datetime.now(timezone.utc)` throughout Phase 2 code.
- `pg_try_advisory_lock` (session-level) for pooled connections: Technically valid but requires matching `pg_advisory_unlock`. Prefer `pg_try_advisory_xact_lock` for connection-pool scenarios.

---

## Open Questions

1. **Advisory lock: session vs transaction level (minor)**
   - What we know: CONTEXT.md specifies `pg_try_advisory_lock(42)` (session-level). Research shows transaction-level (`pg_try_advisory_xact_lock`) is safer for pooled connections.
   - What's unclear: Whether the pool return pattern in this codebase actually releases the connection fully (closing it) or just returns it. `ThreadedConnectionPool.putconn()` keeps the connection alive.
   - Recommendation: Use `pg_try_advisory_xact_lock(42)` in implementation. This is strictly safer and preserves the CONTEXT.md intent (one worker runs the job). If the planner/executor prefers the CONTEXT.md session-level form, add an explicit `pg_advisory_unlock(42)` in a `finally` block.

2. **fired_at timestamp source for each indicator (requires code audit)**
   - What we know: Each indicator's `fired_at` should come from the most recent detection record. The findings tables all have a timestamp column (`gap_start`, `event_ts`, `loiter_start`, `arrival_ts`).
   - What's unclear: Some indicators (IND17 flag risk, IND15 flag hopping, IND23 vessel age) don't have a specific detection timestamp — they're derived from static vessel data. These should have no `fired_at` key even if fired.
   - Recommendation: Indicators derived from static vessel attributes (IND17, IND15, IND23, IND16, IND21) use only `{pts, fired: true}` — no `fired_at`. AIS signal indicators (IND1, IND7, IND8, IND9, IND10, IND29, IND31) carry `fired_at` from the most recent matching findings row.

3. **Bulk refresh strategy: all vessels or score-keyed vessels only**
   - What we know: The scheduler refreshes all vessels every 15 minutes. `get_all_vessel_scores()` returns vessels already in `vessel_scores`. New vessels enter only via the staleness fallback in `screen_vessel_detail()`.
   - What's unclear: Should the scheduler also score vessels in `vessels_canonical` that have no `vessel_scores` row yet?
   - Recommendation: Scheduler refreshes only existing `vessel_scores` rows (`SELECT imo_number FROM vessel_scores`). New vessels get scored on first profile view (staleness fallback inserts them). This is simpler and the dashboard `get_all_vessel_scores()` JOIN naturally excludes unscored vessels (which is fine for Phase 5 ranking table — only vessels that have been viewed appear).

---

## Validation Architecture

`nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | none (discovered via `tests/` directory convention) |
| Quick run command | `pytest tests/test_scores.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-1 | `vessel_scores` table created by `init_scores_tables()` | unit | `pytest tests/test_scores.py::test_init_scores_tables -x` | Wave 0 |
| DB-1 | `upsert_vessel_score()` inserts and updates correctly | unit | `pytest tests/test_scores.py::test_upsert_vessel_score -x` | Wave 0 |
| DB-1 | `get_vessel_score()` returns dict with indicator_json as dict | unit | `pytest tests/test_scores.py::test_get_vessel_score -x` | Wave 0 |
| DB-2 | `append_score_history()` inserts a history row | unit | `pytest tests/test_scores.py::test_append_score_history -x` | Wave 0 |
| DB-2 | `prune_score_history()` deletes rows older than 90 days | unit | `pytest tests/test_scores.py::test_prune_score_history -x` | Wave 0 |
| DB-4 | `score_is_stale()` returns True for age >30 min | unit | `pytest tests/test_scores.py::test_score_is_stale_age -x` | Wave 0 |
| DB-4 | `score_is_stale()` returns True when `is_stale=1` | unit | `pytest tests/test_scores.py::test_score_is_stale_flag -x` | Wave 0 |
| DB-5 | `mark_risk_scores_stale()` sets is_stale=1 for given IMOs | unit | `pytest tests/test_scores.py::test_mark_risk_scores_stale -x` | Wave 0 |
| DB-5 | `upsert_vessel_score()` resets is_stale=0 | unit | `pytest tests/test_scores.py::test_upsert_clears_stale -x` | Wave 0 |
| INF-1 | `get_all_vessel_scores()` returns rows without N+1 | unit | `pytest tests/test_scores.py::test_get_all_vessel_scores -x` | Wave 0 |
| INF-2 | `archive_old_ais_positions()` deletes old rows, keeps recent | unit | `pytest tests/test_scores.py::test_archive_old_ais_positions -x` | Wave 0 |
| DB-1 | Scores block re-exported from `db/__init__.py` | unit | `pytest tests/test_db_package.py::test_all_public_functions_exported -x` | Exists (needs update) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_scores.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- `tests/test_scores.py` — covers all DB-1, DB-2, DB-4, DB-5, INF-1, INF-2 unit tests listed above. Uses `tmp_path` fixture + `monkeypatch.setenv("DATABASE_URL", "")` for SQLite isolation (same pattern as `test_db_package.py::test_import_and_init`).
- `tests/test_db_package.py` — existing file needs `PUBLIC_FUNCTIONS` list updated to include the 8 new scores functions once they are exported.
- Framework: already installed (`pytest>=8.0` in requirements.txt, pytest present in `.venv`).

*(No conftest changes needed — existing conftest.py already sets `DATABASE_URL=''` for all tests.)*

---

## Sources

### Primary (HIGH confidence)

- `db/connection.py`, `db/schema.py`, `db/vessels.py`, `db/scores.py` — established dual-backend patterns; Phase 1 implementation is ground truth for Phase 2 code style
- `screening.py` — source of `compute_vessel_score()` extraction target; lines 164-356 contain the full formula
- `02-CONTEXT.md` — locked decisions; authoritative for schema, staleness behavior, scheduler schedule
- [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — BackgroundScheduler, trigger types, add_job API
- [PostgreSQL 18 Explicit Locking docs](https://www.postgresql.org/docs/current/explicit-locking.html) — advisory lock types, session vs transaction scope

### Secondary (MEDIUM confidence)

- [APScheduler PyPI page](https://pypi.org/project/APScheduler/) — version 3.11.2 confirmed as current 3.x release
- [APScheduler FAQ](https://apscheduler.readthedocs.io/en/3.x/faq.html) — multi-worker / shared job store warning
- [PostgreSQL Advisory Locks guide](https://medium.com/thefreshwrites/advisory-locks-in-postgres-1f993647d061) — session vs transaction distinction confirmed

### Tertiary (LOW confidence)

- [Stack Overflow: single worker advisory lock pattern](https://kiwix.ounapuu.ee/content/stackoverflow.com_en_all_2023-11/questions/16053364) — community pattern for APScheduler + multi-worker; confirms advisory lock approach

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — APScheduler 3.x confirmed; all other dependencies already in codebase
- Architecture: HIGH — dual-backend patterns established from Phase 1; only new domain is APScheduler integration
- Pitfalls: HIGH — advisory lock scope issue is well-documented in PostgreSQL official docs; MMSI/IMO key mismatch is a direct observation from existing code; datetime issue is Python stdlib behavior

**Research date:** 2026-03-04
**Valid until:** 2026-06-04 (90 days; APScheduler 3.x is stable; PostgreSQL advisory lock semantics are stable)
