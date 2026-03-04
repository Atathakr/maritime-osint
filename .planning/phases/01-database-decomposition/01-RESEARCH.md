# Phase 1: Database Decomposition - Research

**Researched:** 2026-03-04
**Domain:** Python package decomposition — monolithic db.py to db/ package
**Confidence:** HIGH (all findings verified against live source code)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Incremental extraction** — one sub-module at a time; db.py deleted only at the very end
- **Done signal per step:** `python app.py` starts without errors and the dashboard loads
- **One git commit per sub-module** (e.g. `refactor(db): extract connection.py`)
- **Final step: Railway smoke-deploy** as the phase completion gate
- **SECRET_KEY + APP_PASSWORD both enforced** via `sys.exit(1)` with friendly one-liner message, after `load_dotenv()`, before Flask config
  - `"[maritime-osint] SECRET_KEY is required. Set it in your environment or .env file. See .env.example."`
  - `"[maritime-osint] APP_PASSWORD is required. Set it in your environment or .env file. See .env.example."`
- **Module names (user-confirmed):** `connection.py`, `schema.py`, `vessels.py`, `sanctions.py`, `ais.py`, `findings.py`, `scores.py`
  - `findings.py` covers detection results (dark_periods, sts_transfers, loitering_reports, spoofing_events, port_calls)
  - `scores.py` is a placeholder stub only in Phase 1 (filled in Phase 2)

### Claude's Discretion
- Exact function grouping within each sub-module (which helpers belong where)
- Whether reconcile.py utilities land in vessels.py or a separate reconcile.py inside db/
- Implementation of re-export inventory audit

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DB-3 | db.py decomposed into db/ package with `__init__.py` re-exporting all public functions; all existing callers (`import db; db.fn()`) unchanged | Full function inventory below; call-site audit complete; re-export pattern documented |
| INF-3 | Unused Anthropic SDK removed from requirements.txt; no import errors | Confirmed unused — zero `import anthropic` or `from anthropic` anywhere in codebase |
| INF-4 | SECRET_KEY loaded from environment; app fails with clear error at startup if not set | Current handling in app.py line 30 documented; replacement pattern specified |
</phase_requirements>

---

## Summary

`db.py` is a 2,835-line single-file database layer that must become a `db/` package. The Python package-with-re-exports pattern is the only safe approach — all 10+ callers use `import db; db.fn()` and must not change. The `__init__.py` becomes the sole public API surface; all sub-modules are implementation details.

Two callers (`loitering.py` and `ports.py`) bypass the public API and access private internals directly: `db._BACKEND`, `db._conn()`, `db._cursor()`, and `db._rows()`. These private helpers must also be re-exported from `__init__.py` to avoid breaking those callers — or the callers must be updated to use a new public helper. This is the highest-risk integration point not called out in prior research.

The `reconcile.py` module calls three functions that belong conceptually to sanctions/vessels CRUD (`find_imo_collisions`, `find_mmsi_imo_collisions`, `merge_canonical`, `rebuild_all_source_tags`). These live in `db.py` under the canonical vessel registry section and belong in `db/sanctions.py` or a dedicated `db/reconcile.py` inside `db/`. The choice is Claude's discretion.

**Primary recommendation:** Create `db/__init__.py` first with ALL re-exports (public + the private helpers used by loitering.py and ports.py), verify app starts, then extract sub-modules one at a time. Never let `__init__.py` fall out of sync with the extracted functions.

---

## Standard Stack

### Core Pattern: Python Package with Re-Exports

| Mechanism | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| `db/__init__.py` | stdlib | Public API surface — only file callers see | Zero caller changes; standard Python package pattern |
| `db/connection.py` | stdlib | `_conn()`, `_BACKEND`, helpers — single source of truth | Dual-backend abstraction must not be duplicated |
| Per-domain sub-modules | stdlib | Isolate CRUD by table domain | Independent testability; clear ownership |

### No New Libraries Required

This phase adds zero new dependencies. All mechanisms are stdlib Python packaging.

**Installation:** None needed.

---

## Architecture Patterns

### Recommended Package Structure

```
db/
├── __init__.py       # Re-exports ALL public + semi-private callables
├── connection.py     # _init_backend(), _conn(), _ph(), _ilike(), _jp(),
│                     # _cursor(), _rows(), _row(), _get_pool(), _sqlite_path(),
│                     # _BACKEND (module-level), _DB_URL, _POOL
├── schema.py         # init_db(), _init_postgres(), _init_sqlite(),
│                     # _migrate_vessels_canonical()
├── vessels.py        # vessels_canonical CRUD:
│                     #   upsert_sanctions_entries(), get_sanctions_entries(),
│                     #   get_sanctions_counts(), get_vessels(), get_vessel(),
│                     #   get_vessel_count(), get_vessel_memberships(),
│                     #   get_vessel_ownership(), get_vessel_flag_history(),
│                     #   get_ais_vessel_by_imo(), search_sanctions_by_imo(),
│                     #   search_sanctions_by_mmsi(), search_sanctions_by_name(),
│                     #   _screen_canonical() [private helper]
├── sanctions.py      # Reconciliation utilities:
│                     #   find_imo_collisions(), find_mmsi_imo_collisions(),
│                     #   merge_canonical(), rebuild_all_source_tags()
│                     # (OR: these move to db/reconcile.py — see note)
├── ais.py            # ais_positions + ais_vessels CRUD:
│                     #   insert_ais_positions(), upsert_ais_vessel(),
│                     #   update_ais_vessel_position(), get_ais_vessels(),
│                     #   get_recent_positions(), find_ais_gaps(),
│                     #   get_consecutive_ais_pairs(), get_ais_positions(),
│                     #   get_active_mmsis(), get_vessel_track(),
│                     #   find_sts_candidates()
├── findings.py       # Detection results CRUD:
│                     #   upsert_dark_periods(), get_dark_periods(),
│                     #   upsert_sts_events(), get_sts_events(),
│                     #   get_sts_zone_count(), upsert_speed_anomalies(),
│                     #   upsert_loitering_events(), get_loitering_summary(),
│                     #   get_speed_anomaly_summary(), upsert_port_calls(),
│                     #   get_port_call_summary(), upsert_psc_detentions(),
│                     #   get_psc_detentions(), get_vessel_indicator_summary()
├── scores.py         # Placeholder stub only (Phase 2 fills this)
└── (optional)
    # db/ingest_log.py OR inline in vessels.py:
    #   log_ingest_start(), log_ingest_complete(), get_ingest_log()
    # db/stats.py OR inline in vessels.py:
    #   get_stats(), get_map_vessels_raw()
```

**Note on grouping choices (Claude's discretion):**
- `find_imo_collisions`, `find_mmsi_imo_collisions`, `merge_canonical`, `rebuild_all_source_tags` are called exclusively from `reconcile.py` (not from any other caller). They could go in `db/sanctions.py` (co-located with the data they operate on) or a dedicated `db/reconcile.py`. The latter makes the internal boundary explicit. Recommendation: `db/sanctions.py` keeps the package at 7 files matching the user-confirmed names; `db/reconcile.py` is the alternative if the reconciliation logic grows.
- `log_ingest_start`, `log_ingest_complete`, `get_ingest_log` touch the `ingest_log` table — no strong domain owner. Recommend grouping in a light `db/stats.py` alongside `get_stats()` and `get_map_vessels_raw()`, or placing in `vessels.py` as ingest infrastructure.

### Pattern 1: Create __init__.py First, Extract Second

**What:** Write the full `__init__.py` re-export list before touching any sub-module. The first commit is `db/__init__.py` that imports everything from `connection.py` (which is a copy of the full `db.py`). Subsequent commits move code from `connection.py` into domain files and update `__init__.py` imports.

**Why:** If `__init__.py` is written incrementally alongside extraction, a missed function goes undetected until a route exercises it. Writing it first from the complete function inventory ensures no gaps.

```python
# db/__init__.py — complete re-export list (after full extraction)
# noqa: F401 on all imports suppresses "imported but unused" linting

from .connection import (                           # noqa: F401
    _conn, _cursor, _rows, _row,                   # semi-private: loitering.py, ports.py use these
    _BACKEND, _ph, _ilike, _jp,                    # semi-private: loitering.py, ports.py use _BACKEND
    _get_pool, _sqlite_path, _init_backend,         # internal init
)
from .schema import init_db                         # noqa: F401
from .vessels import (                              # noqa: F401
    upsert_sanctions_entries, get_sanctions_entries,
    get_sanctions_counts, get_vessels, get_vessel,
    get_vessel_count, get_vessel_memberships,
    get_vessel_ownership, get_vessel_flag_history,
    get_ais_vessel_by_imo,
    search_sanctions_by_imo, search_sanctions_by_mmsi, search_sanctions_by_name,
)
from .sanctions import (                            # noqa: F401
    find_imo_collisions, find_mmsi_imo_collisions,
    merge_canonical, rebuild_all_source_tags,
)
from .ais import (                                  # noqa: F401
    insert_ais_positions, upsert_ais_vessel,
    update_ais_vessel_position, get_ais_vessels,
    get_recent_positions, find_ais_gaps,
    get_consecutive_ais_pairs, get_ais_positions,
    get_active_mmsis, get_vessel_track,
    find_sts_candidates,
)
from .findings import (                             # noqa: F401
    upsert_dark_periods, get_dark_periods,
    upsert_sts_events, get_sts_events, get_sts_zone_count,
    upsert_speed_anomalies, get_speed_anomaly_summary,
    upsert_loitering_events, get_loitering_summary,
    upsert_port_calls, get_port_call_summary,
    upsert_psc_detentions, get_psc_detentions,
    get_vessel_indicator_summary,
)
from .scores import (                               # noqa: F401
    # Phase 1: stub only; Phase 2 populates
)
# Ingest log + stats (wherever they land):
from .vessels import (                              # noqa: F401
    log_ingest_start, log_ingest_complete, get_ingest_log,
    get_stats, get_map_vessels_raw,
)
```

### Pattern 2: connection.py is the Sole Backend Authority

**What:** `connection.py` owns `_BACKEND`, `_DB_URL`, `_POOL`, `_init_backend()`, and all SQL helper functions. No other sub-module redefines placeholder logic or opens connections independently.

**The critical constraint — module-level evaluation:**

```python
# db.py line 105 — evaluated ONCE at import time
_P = "%s" if _BACKEND == "postgres" else "?"   # module-level constant
```

This constant is evaluated when `db.py` is first imported. In the package, `connection.py` is imported first (by `__init__.py`), so `_init_backend()` runs before any other sub-module is loaded. This ordering is preserved by the import chain — do NOT define `_P` as a module-level constant in any sub-module. Use `_ph()` or `_ilike()` function calls instead (which read `_BACKEND` at call time, not import time).

```python
# connection.py — CORRECT pattern
_P = "%s" if _BACKEND == "postgres" else "?"   # OK: connection.py imports first

# vessels.py — WRONG anti-pattern
_P = "%s" if _BACKEND == "postgres" else "?"   # BAD: _BACKEND not yet set when sub-module loads
```

Every sub-module that needs a placeholder does:
```python
from .connection import _ph, _ilike, _jp, _conn, _cursor, _rows, _row, _BACKEND
```

### Pattern 3: Incremental Extraction Sequence

```
Step 0: Create db/ directory, write db/__init__.py that does:
         from .connection import *  (temporary — everything in one place)
         Copy entire db.py content into db/connection.py
         DELETE db.py
         Verify: python app.py starts; dashboard loads
         Commit: "refactor(db): create db/ package (all in connection.py)"

Step 1: Extract db/schema.py
         Move: init_db(), _init_postgres(), _init_sqlite(), _migrate_vessels_canonical()
         Update __init__.py: from .schema import init_db  (remove from .connection import)
         Verify: python app.py starts
         Commit: "refactor(db): extract schema.py"

Step 2: Extract db/vessels.py
         Move: upsert_sanctions_entries(), get_sanctions_entries(), get_sanctions_counts(),
               get_vessels(), get_vessel(), get_vessel_count(), get_vessel_memberships(),
               get_vessel_ownership(), get_vessel_flag_history(), get_ais_vessel_by_imo(),
               search_sanctions_by_imo(), search_sanctions_by_mmsi(),
               search_sanctions_by_name(), _screen_canonical()
         Update __init__.py re-exports
         Verify: python app.py starts
         Commit: "refactor(db): extract vessels.py"

Step 3: Extract db/sanctions.py
         Move: find_imo_collisions(), find_mmsi_imo_collisions(),
               merge_canonical(), rebuild_all_source_tags()
         Update __init__.py
         Commit: "refactor(db): extract sanctions.py"

Step 4: Extract db/ais.py
         Move: insert_ais_positions(), upsert_ais_vessel(), update_ais_vessel_position(),
               get_ais_vessels(), get_recent_positions(), find_ais_gaps(),
               get_consecutive_ais_pairs(), get_ais_positions(), get_active_mmsis(),
               get_vessel_track(), find_sts_candidates()
         Update __init__.py
         Commit: "refactor(db): extract ais.py"

Step 5: Extract db/findings.py
         Move: upsert_dark_periods(), get_dark_periods(),
               upsert_sts_events(), get_sts_events(), get_sts_zone_count(),
               upsert_speed_anomalies(), get_speed_anomaly_summary(),
               upsert_loitering_events(), get_loitering_summary(),
               upsert_port_calls(), get_port_call_summary(),
               upsert_psc_detentions(), get_psc_detentions(),
               get_vessel_indicator_summary()
         Update __init__.py
         Commit: "refactor(db): extract findings.py"

Step 6: Create db/scores.py stub
         Content: module docstring + TODO comment only (no functions)
         Commit: "refactor(db): add scores.py stub"

Step 7: Extract remaining functions into connection.py housekeeping OR stats module
         Remaining: log_ingest_start(), log_ingest_complete(), get_ingest_log(),
                    get_stats(), get_map_vessels_raw()
         Verify connection.py contains ONLY connection/backend/SQL helpers
         Commit: "refactor(db): connection.py cleanup — isolate infrastructure"

Step 8: Remove db.py (already gone from Step 0)
         SECRET_KEY + APP_PASSWORD enforcement in app.py
         Remove anthropic from requirements.txt AND pyproject.toml
         Commit: "feat(inf): enforce SECRET_KEY/APP_PASSWORD at startup"
         Commit: "chore(inf): remove unused anthropic SDK"

Final: Railway smoke-deploy
```

### Anti-Patterns to Avoid

- **Defining `_P` as module-level in sub-modules:** evaluated before `_init_backend()` runs in sub-module context; use `_ph()` instead
- **Moving `normalize.py` inside `db/`:** creates two divergent copies; it stays at project root, all sub-modules `import normalize` from root
- **Nested `_conn()` calls:** inner commit happens before outer function finishes; helper functions that are called by other db functions should accept a `conn` parameter rather than opening their own
- **Writing `__init__.py` incrementally alongside extraction:** a missed function surfaces as `AttributeError` only at request time on less-used routes

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dual-backend SQL | Custom per-file backend detect | `connection.py` as single source | _P evaluated at import time; duplication will diverge |
| Backward-compatible import API | Updating 10+ call sites | `__init__.py` re-exports | All callers use `import db; db.fn()` — no caller changes needed |

---

## Full Public Function Inventory

Complete audit of `db.py` — all functions that must appear in `__init__.py`:

### connection.py (internal helpers — re-exported for loitering.py / ports.py)
| Function/Name | Type | Used by |
|---------------|------|---------|
| `_BACKEND` | module constant | loitering.py (line 210, 213), ports.py (line 118, 121) |
| `_conn()` | context manager | loitering.py (line 219), ports.py (line 127), all sub-modules |
| `_cursor()` | helper | loitering.py (line 220), ports.py (line 128) |
| `_rows()` | helper | loitering.py (line 231), ports.py (line 138) |
| `_row()` | helper | internal sub-module use |
| `_ph()` | helper | all sub-modules needing placeholders |
| `_ilike()` | helper | all sub-modules needing case-insensitive LIKE |
| `_jp()` | helper | JSON parameter placeholder for JSONB |
| `_init_backend()` | init | called at module load in connection.py |
| `_get_pool()` | init | internal connection.py |
| `_sqlite_path()` | helper | internal connection.py |

### schema.py
| Function | Caller |
|----------|--------|
| `init_db()` | app.py line 32 |

### vessels.py
| Function | Caller |
|----------|--------|
| `upsert_sanctions_entries()` | app.py line 184 |
| `get_sanctions_entries()` | app.py line 137 |
| `get_sanctions_counts()` | app.py line 151 |
| `get_vessels()` | app.py line 159 |
| `get_vessel()` | app.py line 170, screening.py line 187 |
| `get_vessel_count()` | internal (get_stats) |
| `get_vessel_memberships()` | screening.py line 147 (via _screen_canonical) |
| `get_vessel_ownership()` | screening.py lines 79, 147, 200 |
| `get_vessel_flag_history()` | screening.py lines 148, 201, 230 |
| `get_ais_vessel_by_imo()` | app.py line 1295, screening.py lines 191, 305 |
| `search_sanctions_by_imo()` | app.py line 173, screening.py line 126, dark_periods.py line 102 |
| `search_sanctions_by_mmsi()` | screening.py line 129, dark_periods.py line 100, sts_detection.py lines 176-177 |
| `search_sanctions_by_name()` | screening.py lines 91, 131, 135 |

### sanctions.py (reconciliation utilities)
| Function | Caller |
|----------|--------|
| `find_imo_collisions()` | reconcile.py line 61 |
| `find_mmsi_imo_collisions()` | reconcile.py line 85 |
| `merge_canonical()` | reconcile.py lines 70, 91 |
| `rebuild_all_source_tags()` | reconcile.py line 41 |

### ais.py
| Function | Caller |
|----------|--------|
| `insert_ais_positions()` | noaa_ingest.py lines 141, 150 |
| `upsert_ais_vessel()` | ais_listener.py (assumed) |
| `update_ais_vessel_position()` | ais_listener.py (assumed) |
| `get_ais_vessels()` | app.py line 311 |
| `get_recent_positions()` | app.py line 300 |
| `find_ais_gaps()` | dark_periods.py line 63 |
| `get_consecutive_ais_pairs()` | spoofing.py line 60 |
| `get_ais_positions()` | app.py line 300 |
| `get_active_mmsis()` | app.py line 348 |
| `get_vessel_track()` | app.py line 324 |
| `find_sts_candidates()` | sts_detection.py line 142 |

### findings.py
| Function | Caller |
|----------|--------|
| `upsert_dark_periods()` | dark_periods.py line 128 |
| `get_dark_periods()` | app.py line 363 |
| `upsert_sts_events()` | sts_detection.py line 210 |
| `get_sts_events()` | app.py line 441 |
| `get_sts_zone_count()` | screening.py (via get_vessel_indicator_summary) |
| `upsert_speed_anomalies()` | spoofing.py line 119 |
| `get_speed_anomaly_summary()` | screening.py line 247 (via get_vessel_indicator_summary) |
| `upsert_loitering_events()` | loitering.py line 287 |
| `get_loitering_summary()` | screening.py line 247 (via get_vessel_indicator_summary) |
| `upsert_port_calls()` | ports.py line 302 |
| `get_port_call_summary()` | screening.py line 247 (via get_vessel_indicator_summary) |
| `upsert_psc_detentions()` | app.py line 241 |
| `get_psc_detentions()` | screening.py line 315 |
| `get_vessel_indicator_summary()` | screening.py line 247 |

### Ingest log + stats (placement TBD, recommend vessels.py or dedicated stats.py)
| Function | Caller |
|----------|--------|
| `log_ingest_start()` | app.py lines 181, 238, 391 |
| `log_ingest_complete()` | app.py lines 185, 199, 242, 251, 395, 403 |
| `get_ingest_log()` | app.py line 258 |
| `get_stats()` | app.py line 102 |
| `get_map_vessels_raw()` | map_data.py line 81 |

### scores.py (Phase 1: stub only)
Empty module with docstring and TODO. No functions to export in Phase 1.

---

## Common Pitfalls

### Pitfall 1: loitering.py and ports.py Access Private db Internals
**What goes wrong:** These two modules bypass the public API and call `db._BACKEND`, `db._conn()`, `db._cursor()`, `db._rows()` directly.
**Why it happens:** They contain custom SQL queries with geometry/time logic that doesn't fit a generic helper function.
**How to avoid:** Re-export these private helpers from `__init__.py` (they work fine via `db._conn()` after the package conversion because `db._conn` resolves through `__init__.py`). No caller changes needed.
**Warning signs:** After conversion, `loitering.py` or `ports.py` raise `AttributeError: module 'db' has no attribute '_conn'` — missing re-export.

### Pitfall 2: Missing Re-Export Surfaces Only at Request Time
**What goes wrong:** A function not re-exported in `__init__.py` doesn't fail at startup — it fails as `AttributeError` when the route is first exercised.
**Why it happens:** Python modules load lazily; attribute access happens at call time.
**How to avoid:** Write the complete `__init__.py` re-export list BEFORE extraction, cross-checked against the function inventory above.
**Warning signs:** App starts cleanly but specific routes return 500 errors in production.

### Pitfall 3: _P Evaluated Before _init_backend() in Sub-Modules
**What goes wrong:** `_P = "%s" if _BACKEND == "postgres" else "?"` at sub-module level evaluates when the sub-module is first imported. If `_BACKEND` hasn't been set by `connection.py` yet, it defaults to `"sqlite"` on Railway PostgreSQL — causing `ProgrammingError: syntax error at or near '?'`.
**Why it happens:** Module-level statements run at import time; import order matters.
**How to avoid:** No sub-module defines `_P` at module level. All use `_ph()` or read `_BACKEND` inside function bodies. The CONTEXT.md correctly identifies this at line 64.
**Warning signs:** Local SQLite tests pass; Railway PostgreSQL returns SQL syntax errors.

### Pitfall 4: normalize.py Must Stay at Project Root
**What goes wrong:** If `normalize.py` is copied into `db/normalize.py`, both exist. Edits to one don't propagate.
**How to avoid:** `normalize.py` stays at project root. All `db/` sub-modules do `import normalize` (not `from . import normalize`).

### Pitfall 5: secrets.token_hex(32) Currently Masks Missing SECRET_KEY
**What goes wrong:** `app.py` line 30 is `app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)`. The `or` clause silently generates a new key on every restart — sessions are invalidated on every Railway deploy, but no error is raised.
**Current line 30:** `app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)`
**Replacement pattern:**
```python
# After load_dotenv(), before Flask config:
import sys
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    print("[maritime-osint] SECRET_KEY is required. Set it in your environment or .env file. See .env.example.")
    sys.exit(1)
_app_password = os.getenv("APP_PASSWORD")
if not _app_password:
    print("[maritime-osint] APP_PASSWORD is required. Set it in your environment or .env file. See .env.example.")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = _secret_key
APP_PASSWORD = _app_password
```
**Warning signs:** App running on Railway with no SECRET_KEY set but no startup error — sessions reset on every deploy.

### Pitfall 6: anthropic in BOTH requirements.txt AND pyproject.toml
**What goes wrong:** Removing from only `requirements.txt` leaves `pyproject.toml` line 10 still declaring `anthropic>=0.40.0`. Railway Nixpacks may use either file.
**How to avoid:** Remove from BOTH files in the same commit.

---

## Code Examples

### scores.py stub (Phase 1 placeholder)
```python
# db/scores.py
"""
Vessel risk score persistence — placeholder for Phase 2.

Phase 2 will add:
  - vessel_scores table (mmsi, composite_score, indicator_json, computed_at)
  - vessel_score_history table (append-only, 90-day retention)
  - upsert_vessel_score(), get_vessel_score() functions

TODO (Phase 2): implement pre-computed score CRUD
"""
```

### connection.py structure
```python
# db/connection.py
"""Backend detection, connection management, and SQL helpers."""

import json
import os
import sqlite3
from contextlib import contextmanager

import normalize  # project root — not db/normalize.py

# ── Backend detection ─────────────────────────────────────────────────────

_DB_URL: str = ""
_BACKEND: str = "sqlite"
_POOL = None


def _init_backend() -> None:
    global _DB_URL, _BACKEND
    _DB_URL = os.getenv("DATABASE_URL", "")
    _BACKEND = "postgres" if _DB_URL.startswith(("postgresql://", "postgres://")) else "sqlite"


_init_backend()

# ... _sqlite_path(), _get_pool(), _conn(), _cursor(), _rows(), _row() ...
# ... _P (module-level constant — OK here, evaluated after _init_backend()) ...
# ... _ph(), _ilike(), _jp() ...
```

### Cross-module import pattern in sub-modules
```python
# db/vessels.py — correct import pattern
from .connection import _BACKEND, _conn, _cursor, _rows, _row, _ph, _ilike, _jp
import json
import normalize  # project root
```

### SECRET_KEY enforcement in app.py
```python
import sys
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    print("[maritime-osint] SECRET_KEY is required. Set it in your environment or .env file. See .env.example.")
    sys.exit(1)
_app_password = os.getenv("APP_PASSWORD")
if not _app_password:
    print("[maritime-osint] APP_PASSWORD is required. Set it in your environment or .env file. See .env.example.")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = _secret_key
APP_PASSWORD = _app_password
```

---

## Validation Architecture

`nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed) |
| Config file | None — see Wave 0 |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |
| Install command | `pip install pytest` |

**Current state:** No `tests/` directory exists. No test files exist. pytest is not installed. This phase creates the test infrastructure from scratch (Wave 0 gap).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-3 | `import db; db.init_db()` works after conversion | smoke | `python -m pytest tests/test_db_package.py::test_import_and_init -x` | Wave 0 |
| DB-3 | All public functions accessible via `db.<fn>` | unit | `python -m pytest tests/test_db_package.py::test_all_public_functions_exported -x` | Wave 0 |
| DB-3 | `db._BACKEND`, `db._conn`, `db._cursor`, `db._rows` accessible (loitering.py, ports.py compat) | unit | `python -m pytest tests/test_db_package.py::test_private_helpers_exported -x` | Wave 0 |
| INF-3 | No `import anthropic` anywhere in project | static | `python -m pytest tests/test_inf3_anthropic.py -x` | Wave 0 |
| INF-4 | `app.py` exits with code 1 + message when SECRET_KEY missing | unit | `python -m pytest tests/test_inf4_startup.py::test_missing_secret_key -x` | Wave 0 |
| INF-4 | `app.py` exits with code 1 + message when APP_PASSWORD missing | unit | `python -m pytest tests/test_inf4_startup.py::test_missing_app_password -x` | Wave 0 |

### Key Test Patterns

**test_db_package.py — import and re-export verification:**
```python
# tests/test_db_package.py
import os
os.environ["DATABASE_URL"] = ""  # Force SQLite; must precede any db import

import db

PUBLIC_FUNCTIONS = [
    # schema
    "init_db",
    # vessels
    "upsert_sanctions_entries", "get_sanctions_entries", "get_sanctions_counts",
    "get_vessels", "get_vessel", "get_vessel_count",
    "get_vessel_memberships", "get_vessel_ownership", "get_vessel_flag_history",
    "get_ais_vessel_by_imo",
    "search_sanctions_by_imo", "search_sanctions_by_mmsi", "search_sanctions_by_name",
    # sanctions/reconcile
    "find_imo_collisions", "find_mmsi_imo_collisions",
    "merge_canonical", "rebuild_all_source_tags",
    # ais
    "insert_ais_positions", "upsert_ais_vessel", "update_ais_vessel_position",
    "get_ais_vessels", "get_recent_positions", "find_ais_gaps",
    "get_consecutive_ais_pairs", "get_ais_positions", "get_active_mmsis",
    "get_vessel_track", "find_sts_candidates",
    # findings
    "upsert_dark_periods", "get_dark_periods",
    "upsert_sts_events", "get_sts_events", "get_sts_zone_count",
    "upsert_speed_anomalies", "get_speed_anomaly_summary",
    "upsert_loitering_events", "get_loitering_summary",
    "upsert_port_calls", "get_port_call_summary",
    "upsert_psc_detentions", "get_psc_detentions",
    "get_vessel_indicator_summary",
    # ingest log + stats
    "log_ingest_start", "log_ingest_complete", "get_ingest_log",
    "get_stats", "get_map_vessels_raw",
]

SEMI_PRIVATE = ["_BACKEND", "_conn", "_cursor", "_rows", "_row"]

def test_all_public_functions_exported():
    for fn in PUBLIC_FUNCTIONS:
        assert hasattr(db, fn), f"db.{fn} missing from __init__.py"

def test_private_helpers_exported():
    for name in SEMI_PRIVATE:
        assert hasattr(db, name), f"db.{name} missing — loitering.py/ports.py use it"

def test_backend_is_sqlite():
    assert db._BACKEND == "sqlite", "Expected sqlite when DATABASE_URL=''"

def test_import_and_init(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    db._init_backend()
    db.init_db()  # Should not raise
```

**test_inf4_startup.py — startup enforcement:**
```python
# tests/test_inf4_startup.py
import subprocess, sys

def test_missing_secret_key():
    env = {"PATH": "/usr/bin:/bin", "APP_PASSWORD": "test"}  # No SECRET_KEY
    result = subprocess.run([sys.executable, "app.py"], capture_output=True, env=env,
                            cwd=".")
    assert result.returncode == 1
    assert b"SECRET_KEY is required" in result.stdout

def test_missing_app_password():
    env = {"PATH": "/usr/bin:/bin", "SECRET_KEY": "test-secret"}  # No APP_PASSWORD
    result = subprocess.run([sys.executable, "app.py"], capture_output=True, env=env,
                            cwd=".")
    assert result.returncode == 1
    assert b"APP_PASSWORD is required" in result.stdout
```

**test_inf3_anthropic.py — SDK removal:**
```python
# tests/test_inf3_anthropic.py
import pathlib, re

def test_anthropic_not_in_requirements():
    req = pathlib.Path("requirements.txt").read_text()
    assert "anthropic" not in req

def test_anthropic_not_in_pyproject():
    pyp = pathlib.Path("pyproject.toml").read_text()
    assert "anthropic" not in pyp

def test_no_anthropic_imports():
    src_files = list(pathlib.Path(".").glob("*.py"))
    for f in src_files:
        if ".venv" in str(f):
            continue
        content = f.read_text()
        assert "import anthropic" not in content, f"{f} imports anthropic"
        assert "from anthropic" not in content, f"{f} imports from anthropic"
```

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_db_package.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps (must exist before implementation begins)

- [ ] `tests/` directory
- [ ] `tests/__init__.py` — empty
- [ ] `tests/conftest.py` — sets `DATABASE_URL=""` before imports
- [ ] `tests/test_db_package.py` — covers DB-3 import/re-export verification
- [ ] `tests/test_inf3_anthropic.py` — covers INF-3 SDK removal
- [ ] `tests/test_inf4_startup.py` — covers INF-4 startup enforcement
- [ ] Framework install: `pip install pytest` (add to requirements-dev.txt or pyproject.toml `[dev]` extras)

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Monolithic `db.py` | `db/` package with `__init__.py` re-exports | Zero caller changes; domain isolation; independent testability |
| Silent `secrets.token_hex` fallback | `sys.exit(1)` with friendly message | Sessions survive Railway redeploys; no silent security degradation |
| `anthropic>=0.40.0` in deps | Removed | Faster Railway builds; smaller slug; cleaner dependency surface |

---

## Open Questions

1. **Where do ingest log and stats functions live?**
   - What we know: `log_ingest_start`, `log_ingest_complete`, `get_ingest_log`, `get_stats`, `get_map_vessels_raw` don't belong cleanly to any domain module
   - What's unclear: planner's preference
   - Recommendation: Add a `db/stats.py` sub-module for `get_stats()` and `get_map_vessels_raw()`; put ingest log functions in `vessels.py` as ingest infrastructure, OR create a thin `db/ingest_log.py` — both work; choose during planning

2. **Should loitering.py and ports.py be refactored to avoid private access?**
   - What we know: They call `db._conn()`, `db._cursor()`, `db._rows()`, `db._BACKEND` directly for custom geo/time queries
   - What's unclear: whether Phase 1 is the right time to add public wrappers for these queries
   - Recommendation: Phase 1 just re-exports the private helpers (zero behavior change); Phase 2 or a future cleanup phase can introduce public query helpers. Flagged for planner awareness.

3. **reconcile.py functions in sanctions.py or db/reconcile.py?**
   - What we know: `find_imo_collisions`, `find_mmsi_imo_collisions`, `merge_canonical`, `rebuild_all_source_tags` are called only from `reconcile.py`
   - Recommendation: Put in `db/sanctions.py` to match the 7-module user-confirmed package layout. If the reconciliation logic grows, extract to `db/reconcile.py` in a future phase.

---

## Sources

### Primary (HIGH confidence)
- Live `db.py` — direct source read (lines 1–2836); all function names and line numbers verified
- Live `app.py` — direct source read; `db.` call sites at lines 32, 102, 137, 151, 159, 170, 173, 181, 184–199, 238–251, 258, 300, 311, 324, 348, 363, 391–403, 441
- Live `loitering.py` — private db access at lines 210, 213, 219, 220, 231
- Live `ports.py` — private db access at lines 118, 121, 127, 128, 138
- Live `reconcile.py` — call sites: find_imo_collisions (61), find_mmsi_imo_collisions (85), merge_canonical (70, 91), rebuild_all_source_tags (41)
- `.planning/research/ARCHITECTURE.md` — db decomposition pattern (Pattern 2, p. 199–257)
- `.planning/research/PITFALLS.md` — Pitfall B1 (_P), B2 (missing re-exports), B3 (circular), B5 (normalize.py)
- `pyproject.toml` — anthropic>=0.40.0 at line 10; ruff SLF001 rule suppressed (explains why linting doesn't catch private access)
- `requirements.txt` — anthropic>=0.40.0 at line 4

### Secondary (MEDIUM confidence)
- `.planning/codebase/CONCERNS.md` — anthropic SDK unused, confirmed at line 280

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all patterns verified against live source code
- Function inventory: HIGH — grepped all public/private functions from db.py; verified call sites in all 10 callers
- Private access discovery: HIGH — loitering.py and ports.py access confirmed via grep
- Anthropic SDK: HIGH — zero `import anthropic` anywhere in .py files; in both requirements.txt and pyproject.toml
- Pitfalls: HIGH — inherited from PITFALLS.md (codebase-confirmed) + new private access discovery

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain — no external API dependencies)
