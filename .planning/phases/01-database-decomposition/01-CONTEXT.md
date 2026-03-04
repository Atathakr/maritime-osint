# Phase 1: Database Decomposition - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert `db.py` (2,835 lines) into a `db/` package that all callers use identically via `import db; db.fn()`. Enforce `SECRET_KEY` (and `APP_PASSWORD`) from environment variables with a friendly startup error. Remove the unused Anthropic SDK from `requirements.txt`. Zero observable behavior change — no new features, no schema changes.

</domain>

<decisions>
## Implementation Decisions

### Migration strategy
- **Incremental extraction** — extract one sub-module at a time, not all at once
- After each extraction, `db/__init__.py` re-exports it and the app starts cleanly
- **Done signal per step:** `python app.py` starts without errors and the dashboard loads
- **One git commit per sub-module** — e.g. `refactor(db): extract connection.py`, `refactor(db): extract vessels.py`
- `db.py` is deleted only at the very end, after all sub-modules are extracted and verified
- **Final step: Railway smoke-deploy** — after local verification passes, trigger a Railway deploy as the phase completion gate

### SECRET_KEY failure mode
- **Crash with friendly message** at startup — not a silent warning, not a KeyError
- Check runs in `app.py` immediately after `load_dotenv()`, before any Flask config
- **Enforce both `SECRET_KEY` and `APP_PASSWORD`** in the same check block
- **Message format:** one-liner with fix instruction
  - `"[maritime-osint] SECRET_KEY is required. Set it in your environment or .env file. See .env.example."`
  - `"[maritime-osint] APP_PASSWORD is required. Set it in your environment or .env file. See .env.example."`
- Use `sys.exit(1)` after printing the message

### db/ package structure and module names
The full package layout (user-confirmed naming):

```
db/
├── __init__.py       # Re-exports all public functions — only file callers see
├── connection.py     # Backend detection, _conn(), _ph(), _ilike(), _jp(), pool management
├── schema.py         # init_db(), all CREATE TABLE / CREATE INDEX DDL
├── vessels.py        # vessels_canonical CRUD
├── sanctions.py      # sanctions_entries, sanctions_memberships CRUD
├── ais.py            # ais_positions, ais_vessel_static CRUD
├── findings.py       # Detection results CRUD (dark_periods, sts_transfers, loitering_reports, spoofing_events, port_calls)
└── scores.py         # Placeholder stub only in Phase 1 (Phase 2 fills in vessel_scores schema)
```

- **`findings.py`** chosen for detection results — OSINT terminology, avoids collision with behavioral detector modules (`dark_periods.py`, `sts_detection.py`)
- **`vessels.py`** — matches table name (`vessels_canonical`), predictable
- **`ais.py`** — covers both `ais_positions` and `ais_vessel_static`
- **`scores.py`** — created as placeholder stub in Phase 1 (module docstring + TODO), filled in Phase 2

### Claude's Discretion
- Exact function grouping within each sub-module (which helpers belong where)
- Whether `reconcile.py` utilities land in `vessels.py` or a separate `reconcile.py` inside db/
- Implementation of re-export inventory audit (grep approach or manual scan)

</decisions>

<code_context>
## Existing Code Insights

### Critical Constraints
- `_P = "%s" if _BACKEND == "postgres" else "?"` at `db.py` line 105 is a module-level constant evaluated at import time — **must stay in `connection.py` only**; no sub-module should redefine placeholder logic independently (PITFALL B1)
- `import normalize` at `db.py` line 16 — `normalize.py` stays at project root, not moved into `db/`; all `db/` sub-modules import normalize from project root
- `# ── Section Name ──` separator pattern used throughout `db.py` — preserve in sub-modules for consistency

### Caller Pattern (all 10+ callers)
All callers use `import db; db.some_function()` — no `from db import fn` or `import db.submodule`:
- `app.py`, `screening.py`, `dark_periods.py`, `loitering.py`, `sts_detection.py`, `spoofing.py`, `reconcile.py`, `ingest.py`, `noaa_ingest.py`, `ports.py`

`db/__init__.py` must re-export every public function. Missing re-exports surface as `AttributeError` only at request time on less-used routes (PITFALL B2).

### Re-export Pattern
No `__all__` used in codebase — relies on naming convention (`_leading_underscore` = private). `__init__.py` re-exports should follow:
```python
from .connection import _conn, _ph, _ilike, init_db  # noqa: F401
from .vessels import get_vessel_by_imo, upsert_canonical, ...  # noqa: F401
```

### Integration Points
- `app.py` — calls `db.init_db()` at startup; this must work via `db/__init__.py` → `db/schema.py`
- `screening.py` — heaviest consumer; calls vessel, sanctions, and AIS queries
- Detection modules — each calls `db.insert_*` for their results (now routed to `db/findings.py`)

</code_context>

<specifics>
## Specific Ideas

- Incremental approach mirrors how GSD plans are structured — each extraction is one plan, committed independently
- The Railway smoke-deploy as final Phase 1 gate gives confidence before Phase 2 adds the APScheduler and new `vessel_scores` table on top of the refactored package

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-database-decomposition*
*Context gathered: 2026-03-04*
