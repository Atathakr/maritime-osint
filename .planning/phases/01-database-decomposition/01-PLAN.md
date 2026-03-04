---
phase: 01-database-decomposition
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_db_package.py
  - tests/test_inf4_startup.py
  - tests/test_inf3_anthropic.py
  - requirements.txt
  - db/__init__.py
  - db/connection.py
autonomous: true
requirements: [DB-3]
must_haves:
  truths:
    - "tests/ directory exists with all four test files before any code change begins"
    - "python -m pytest tests/ -x -q passes (tests fail with ImportError until db/ is created — but the test *files* exist and pytest discovers them)"
    - "db/ package directory exists with __init__.py and connection.py"
    - "db/__init__.py re-exports all 56 public functions + 5 private helpers listed in the function inventory"
    - "import db; db.init_db() works without error when DATABASE_URL is empty (SQLite fallback)"
    - "db._BACKEND, db._conn, db._cursor, db._rows, db._row are accessible (loitering.py / ports.py compat)"
    - "db.py still exists at the end of this plan — deletion happens only in plan 01-03 after all sub-modules are extracted"
  artifacts:
    - path: "tests/__init__.py"
      provides: "empty package marker"
    - path: "tests/conftest.py"
      provides: "DATABASE_URL='' guard before any db import"
    - path: "tests/test_db_package.py"
      provides: "DB-3 import/re-export verification — test_import_and_init, test_all_public_functions_exported, test_private_helpers_exported, test_backend_is_sqlite"
    - path: "tests/test_inf4_startup.py"
      provides: "INF-4 startup enforcement — test_missing_secret_key, test_missing_app_password"
    - path: "tests/test_inf3_anthropic.py"
      provides: "INF-3 SDK removal — test_anthropic_not_in_requirements, test_anthropic_not_in_pyproject, test_no_anthropic_imports"
    - path: "db/__init__.py"
      provides: "complete re-export surface for all callers"
    - path: "db/connection.py"
      provides: "_BACKEND detection, _conn(), _ph(), _ilike(), _jp(), _cursor(), _rows(), _row(), pool management"
  key_links:
    - from: "db/__init__.py"
      to: "db/connection.py"
      via: "from .connection import ..."
      pattern: "from \\.connection import"
    - from: "loitering.py"
      to: "db._conn / db._BACKEND"
      via: "__init__.py re-export"
      pattern: "db\\._conn|db\\._BACKEND"
    - from: "tests/conftest.py"
      to: "DATABASE_URL env var"
      via: "os.environ assignment before any import"
      pattern: "DATABASE_URL"
---

<objective>
Create the test infrastructure (Wave 0), audit all db.fn() call sites, and create the db/ package skeleton — with db/__init__.py containing the complete re-export inventory and db/connection.py containing the full backend/connection layer extracted from db.py.

Purpose: The test infrastructure must exist before any code change so every subsequent extraction is immediately verifiable. The complete __init__.py re-export list is written from the full function inventory (not incrementally) to prevent silent gaps that only surface as AttributeError at request time in production.

Output: tests/ directory with four test files; db/ package with __init__.py (complete re-export surface) and connection.py (full connection layer). db.py still exists — it is NOT deleted in this plan.
</objective>

<execution_context>
@C:/Users/ardal/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/ardal/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@C:/Users/ardal/OneDrive/Desktop/Claude Projects/maritime-osint/.planning/PROJECT.md
@C:/Users/ardal/OneDrive/Desktop/Claude Projects/maritime-osint/.planning/ROADMAP.md
@C:/Users/ardal/OneDrive/Desktop/Claude Projects/maritime-osint/.planning/phases/01-database-decomposition/01-CONTEXT.md
@C:/Users/ardal/OneDrive/Desktop/Claude Projects/maritime-osint/.planning/phases/01-database-decomposition/01-RESEARCH.md
@C:/Users/ardal/OneDrive/Desktop/Claude Projects/maritime-osint/.planning/phases/01-database-decomposition/01-VALIDATION.md

<interfaces>
<!-- Key constraints the executor needs. Extracted from RESEARCH.md + CONTEXT.md. -->

## Caller pattern (all 10+ callers)
All callers use `import db; db.fn()` — no from-imports, no submodule access (except
loitering.py and ports.py which also access private helpers):

  app.py, screening.py, dark_periods.py, loitering.py, sts_detection.py,
  spoofing.py, reconcile.py, ingest.py, noaa_ingest.py, ports.py

## Private helpers required in __init__.py (loitering.py + ports.py use these)
  db._BACKEND   — loitering.py lines 210, 213; ports.py lines 118, 121
  db._conn()    — loitering.py line 219; ports.py line 127
  db._cursor()  — loitering.py line 220; ports.py line 128
  db._rows()    — loitering.py line 231; ports.py line 138
  db._row()     — internal use

## Critical: _P must NOT be defined as module-level in sub-modules
  db.py line 105: _P = "%s" if _BACKEND == "postgres" else "?"
  This is evaluated at import time. It belongs ONLY in connection.py.
  Sub-modules must call _ph() instead — never define their own _P.

## normalize.py stays at project root
  db.py line 16: import normalize
  normalize.py is NOT moved into db/. Sub-modules do: import normalize

## connection.py owns these names
  _DB_URL, _BACKEND, _POOL (module-level state)
  _init_backend(), _sqlite_path(), _get_pool()
  _conn() (contextmanager), _cursor(), _rows(), _row()
  _ph(), _ilike(), _jp()
  _P = "%s" if _BACKEND == "postgres" else "?"  (OK here — connection.py loads first)

## Complete public function inventory (56 functions + 5 private helpers)
  schema:   init_db
  vessels:  upsert_sanctions_entries, get_sanctions_entries, get_sanctions_counts,
            get_vessels, get_vessel, get_vessel_count, get_vessel_memberships,
            get_vessel_ownership, get_vessel_flag_history, get_ais_vessel_by_imo,
            search_sanctions_by_imo, search_sanctions_by_mmsi, search_sanctions_by_name
  sanctions: find_imo_collisions, find_mmsi_imo_collisions, merge_canonical, rebuild_all_source_tags
  ais:      insert_ais_positions, upsert_ais_vessel, update_ais_vessel_position,
            get_ais_vessels, get_recent_positions, find_ais_gaps,
            get_consecutive_ais_pairs, get_ais_positions, get_active_mmsis,
            get_vessel_track, find_sts_candidates
  findings: upsert_dark_periods, get_dark_periods,
            upsert_sts_events, get_sts_events, get_sts_zone_count,
            upsert_speed_anomalies, get_speed_anomaly_summary,
            upsert_loitering_events, get_loitering_summary,
            upsert_port_calls, get_port_call_summary,
            upsert_psc_detentions, get_psc_detentions, get_vessel_indicator_summary
  vessels (ingest log + stats, placed here — Claude's discretion):
            log_ingest_start, log_ingest_complete, get_ingest_log,
            get_stats, get_map_vessels_raw
  scores:   (Phase 1 stub — no functions exported)
  private:  _BACKEND, _conn, _cursor, _rows, _row
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task W0: Create test infrastructure (Wave 0 — must run before any code change)</name>
  <files>
    tests/__init__.py
    tests/conftest.py
    tests/test_db_package.py
    tests/test_inf4_startup.py
    tests/test_inf3_anthropic.py
    requirements.txt
  </files>
  <action>
Create the tests/ directory and all test files from scratch. Install pytest. These files contain the validation contract for the entire phase — they must exist and be discovered by pytest before any db/ code is written.

1. Create tests/__init__.py — empty file (package marker).

2. Create tests/conftest.py:
```python
# tests/conftest.py
"""
Phase 1 conftest — set DATABASE_URL before any db import.
This prevents tests from accidentally connecting to a real PostgreSQL instance.
"""
import os

# Must be set before any db import anywhere in the test session.
os.environ.setdefault("DATABASE_URL", "")
```

3. Create tests/test_db_package.py with the exact code from RESEARCH.md "Key Test Patterns" section:
```python
# tests/test_db_package.py
"""DB-3 — verify db/ package re-exports all public functions and private helpers."""
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

4. Create tests/test_inf4_startup.py with the exact code from RESEARCH.md:
```python
# tests/test_inf4_startup.py
"""INF-4 — verify app.py exits with code 1 and friendly message when env vars missing."""
import subprocess
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_missing_secret_key():
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "APP_PASSWORD": "test"}
    result = subprocess.run(
        [sys.executable, "app.py"],
        capture_output=True,
        env=env,
        cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert b"SECRET_KEY is required" in output, (
        f"Expected 'SECRET_KEY is required' in output, got: {output!r}"
    )

def test_missing_app_password():
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SECRET_KEY": "test-secret"}
    result = subprocess.run(
        [sys.executable, "app.py"],
        capture_output=True,
        env=env,
        cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert b"APP_PASSWORD is required" in output, (
        f"Expected 'APP_PASSWORD is required' in output, got: {output!r}"
    )
```

5. Create tests/test_inf3_anthropic.py with the exact code from RESEARCH.md:
```python
# tests/test_inf3_anthropic.py
"""INF-3 — verify anthropic SDK is not in requirements or source files."""
import pathlib
import os

_PROJECT_ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_anthropic_not_in_requirements():
    req = (_PROJECT_ROOT / "requirements.txt").read_text()
    assert "anthropic" not in req, "anthropic found in requirements.txt — remove it"

def test_anthropic_not_in_pyproject():
    pyp = (_PROJECT_ROOT / "pyproject.toml").read_text()
    assert "anthropic" not in pyp, "anthropic found in pyproject.toml — remove it"

def test_no_anthropic_imports():
    src_files = list(_PROJECT_ROOT.glob("*.py"))
    for f in src_files:
        if ".venv" in str(f) or "site-packages" in str(f):
            continue
        content = f.read_text(errors="ignore")
        assert "import anthropic" not in content, f"{f} contains 'import anthropic'"
        assert "from anthropic" not in content, f"{f} contains 'from anthropic'"
```

6. Add pytest to requirements.txt. Read the current requirements.txt first, then append `pytest>=8.0` on a new line (do not remove anything). Also add a comment line `# --- dev / test ---` before the pytest line if it doesn't already exist.

7. Install pytest: `pip install pytest` (or `pip install pytest>=8.0`).

After creating all files, run pytest in collection-only mode to confirm test files are discovered (they will fail to import db until db/ is created — that is expected at this stage):
`python -m pytest tests/ --collect-only -q`

Expected output: 7+ test items collected (or collection errors about missing `db` module — both are acceptable at this stage; the files exist and pytest finds them).

Commit: `git add tests/ requirements.txt && git commit -m "test(phase-1): add Wave 0 test infrastructure"`
  </action>
  <verify>
    <automated>python -m pytest tests/ --collect-only -q 2>&1 | head -30</automated>
  </verify>
  <done>
    - tests/__init__.py, tests/conftest.py, tests/test_db_package.py, tests/test_inf4_startup.py, tests/test_inf3_anthropic.py all exist
    - pytest discovers 7+ test items (collection may show ImportError for db — acceptable)
    - pytest is installed and runnable
    - Wave 0 test infrastructure committed to git
  </done>
</task>

<task type="auto">
  <name>Task 1: Create db/ skeleton — audit call sites, write __init__.py with complete re-export inventory, extract connection.py</name>
  <files>
    db/__init__.py
    db/connection.py
  </files>
  <action>
Create the db/ package with the complete re-export surface in __init__.py, then extract connection.py from db.py. db.py is NOT deleted in this task.

**Step 1 — Audit call sites (read-only, no file changes)**

Read db.py (2,835 lines) and confirm every public function that appears in the PUBLIC_FUNCTIONS list above is actually defined in db.py. Cross-check by grepping for each function name. Note any discrepancies before proceeding.

Also grep all 10 callers for `db._` to confirm the private helpers used:
- loitering.py: db._BACKEND, db._conn, db._cursor, db._rows
- ports.py: db._BACKEND, db._conn, db._cursor, db._rows

Record any functions found in callers but NOT in the PUBLIC_FUNCTIONS list — these must be added to the re-export inventory before writing __init__.py.

**Step 2 — Create db/__init__.py with COMPLETE re-export inventory**

Write db/__init__.py now, before extracting any code. The re-exports point to sub-modules that do not yet exist — that is intentional. The imports will become valid as sub-modules are created in plan 01-02.

For NOW (plan 01-01), write __init__.py to import everything from connection.py only (since connection.py is the only sub-module being created in this plan). The full re-export block for other sub-modules is written as commented-out stubs so the final shape is visible:

```python
# db/__init__.py
"""
Maritime OSINT database package.

Public API: all callers use `import db; db.fn()` — this file is the only
surface they see. Sub-modules are implementation details.

Re-export pattern: `from .submodule import fn  # noqa: F401`
The noqa suppresses "imported but unused" linting — these are intentional
re-exports, not dead imports.
"""

# ── Connection layer (available immediately — connection.py extracted in plan 01-01) ──
from .connection import (  # noqa: F401
    # Private helpers — re-exported for loitering.py and ports.py compatibility
    # (these callers access db._conn, db._BACKEND, etc. directly)
    _BACKEND,
    _conn,
    _cursor,
    _rows,
    _row,
    # SQL helpers used by sub-modules
    _ph,
    _ilike,
    _jp,
    # Init function (called by connection.py internally; exposed for test_import_and_init)
    _init_backend,
    # Internal pool helpers (not called by callers directly, but safe to expose)
    _get_pool,
    _sqlite_path,
)

# ── Schema (extracted in plan 01-02, step 1) ──
from .schema import init_db  # noqa: F401

# ── Vessels CRUD (extracted in plan 01-02, step 2) ──
from .vessels import (  # noqa: F401
    upsert_sanctions_entries,
    get_sanctions_entries,
    get_sanctions_counts,
    get_vessels,
    get_vessel,
    get_vessel_count,
    get_vessel_memberships,
    get_vessel_ownership,
    get_vessel_flag_history,
    get_ais_vessel_by_imo,
    search_sanctions_by_imo,
    search_sanctions_by_mmsi,
    search_sanctions_by_name,
    # Ingest log + stats (Claude's discretion: placed in vessels.py)
    log_ingest_start,
    log_ingest_complete,
    get_ingest_log,
    get_stats,
    get_map_vessels_raw,
)

# ── Sanctions / reconcile utilities (extracted in plan 01-02, step 3) ──
from .sanctions import (  # noqa: F401
    find_imo_collisions,
    find_mmsi_imo_collisions,
    merge_canonical,
    rebuild_all_source_tags,
)

# ── AIS CRUD (extracted in plan 01-02, step 4) ──
from .ais import (  # noqa: F401
    insert_ais_positions,
    upsert_ais_vessel,
    update_ais_vessel_position,
    get_ais_vessels,
    get_recent_positions,
    find_ais_gaps,
    get_consecutive_ais_pairs,
    get_ais_positions,
    get_active_mmsis,
    get_vessel_track,
    find_sts_candidates,
)

# ── Findings / detection results CRUD (extracted in plan 01-02, step 5) ──
from .findings import (  # noqa: F401
    upsert_dark_periods,
    get_dark_periods,
    upsert_sts_events,
    get_sts_events,
    get_sts_zone_count,
    upsert_speed_anomalies,
    get_speed_anomaly_summary,
    upsert_loitering_events,
    get_loitering_summary,
    upsert_port_calls,
    get_port_call_summary,
    upsert_psc_detentions,
    get_psc_detentions,
    get_vessel_indicator_summary,
)

# ── Scores (Phase 1: stub module only — no functions exported yet) ──
# Phase 2 will add: upsert_vessel_score, get_vessel_score, mark_scores_stale
# from .scores import (...)  # noqa: F401 — uncomment in Phase 2
```

IMPORTANT: The imports from .schema, .vessels, .sanctions, .ais, .findings will cause ImportError until those sub-modules are created in plan 01-02. That is acceptable — plan 01-01 only needs connection.py to work. The full __init__.py is written now so there is no risk of forgetting a function later.

Wait — actually, writing the full __init__.py now will break `import db` until all sub-modules exist. To avoid breaking `python app.py` smoke-test after this plan, write __init__.py in two stages:

STAGE A (this plan): Only import from connection.py. Stub the other imports as comments.
STAGE B (plan 01-02, after each sub-module is extracted): Uncomment each import block.

Revise the __init__.py so that in plan 01-01, only connection.py imports are active. All other import blocks are present but commented out with `# PLAN 01-02:` prefix:

```python
# db/__init__.py
"""
Maritime OSINT database package — public re-export surface.

All callers use `import db; db.fn()`. This file is the only module they see.
Sub-modules are implementation details extracted incrementally (plans 01-01 through 01-02).

noqa: F401 suppresses "imported but unused" for intentional re-exports.
"""

# ── Connection layer ──────────────────────────────────────────────────────────
# Extracted: plan 01-01
# Private helpers re-exported for loitering.py and ports.py (use db._conn, db._BACKEND etc.)
from .connection import (  # noqa: F401
    _BACKEND,
    _conn,
    _cursor,
    _rows,
    _row,
    _ph,
    _ilike,
    _jp,
    _init_backend,
    _get_pool,
    _sqlite_path,
)

# ── Schema ────────────────────────────────────────────────────────────────────
# PLAN 01-02 step 1: uncomment after extracting schema.py
# from .schema import init_db  # noqa: F401

# ── Vessels CRUD ──────────────────────────────────────────────────────────────
# PLAN 01-02 step 2: uncomment after extracting vessels.py
# from .vessels import (  # noqa: F401
#     upsert_sanctions_entries, get_sanctions_entries, get_sanctions_counts,
#     get_vessels, get_vessel, get_vessel_count,
#     get_vessel_memberships, get_vessel_ownership, get_vessel_flag_history,
#     get_ais_vessel_by_imo,
#     search_sanctions_by_imo, search_sanctions_by_mmsi, search_sanctions_by_name,
#     log_ingest_start, log_ingest_complete, get_ingest_log,
#     get_stats, get_map_vessels_raw,
# )

# ── Sanctions / reconcile ─────────────────────────────────────────────────────
# PLAN 01-02 step 3: uncomment after extracting sanctions.py
# from .sanctions import (  # noqa: F401
#     find_imo_collisions, find_mmsi_imo_collisions,
#     merge_canonical, rebuild_all_source_tags,
# )

# ── AIS CRUD ──────────────────────────────────────────────────────────────────
# PLAN 01-02 step 4: uncomment after extracting ais.py
# from .ais import (  # noqa: F401
#     insert_ais_positions, upsert_ais_vessel, update_ais_vessel_position,
#     get_ais_vessels, get_recent_positions, find_ais_gaps,
#     get_consecutive_ais_pairs, get_ais_positions, get_active_mmsis,
#     get_vessel_track, find_sts_candidates,
# )

# ── Findings / detection results ──────────────────────────────────────────────
# PLAN 01-02 step 5: uncomment after extracting findings.py
# from .findings import (  # noqa: F401
#     upsert_dark_periods, get_dark_periods,
#     upsert_sts_events, get_sts_events, get_sts_zone_count,
#     upsert_speed_anomalies, get_speed_anomaly_summary,
#     upsert_loitering_events, get_loitering_summary,
#     upsert_port_calls, get_port_call_summary,
#     upsert_psc_detentions, get_psc_detentions,
#     get_vessel_indicator_summary,
# )

# ── Scores (Phase 2 placeholder) ──────────────────────────────────────────────
# PLAN 01-02 step 6: stub created; no functions exported in Phase 1
# from .scores import (...)  # noqa: F401 — Phase 2 will populate
```

**Step 3 — Extract connection.py from db.py**

Read db.py and identify the connection/backend section. Extract into db/connection.py ONLY the following:

- Module docstring
- All imports needed by the connection layer (os, sqlite3, json, contextlib, threading, psycopg2/psycopg2-binary if imported, etc.)
- `import normalize` (project root — stays as `import normalize`, not `from . import normalize`)
- `_DB_URL`, `_BACKEND`, `_POOL` module-level variables
- `_init_backend()` function
- `_sqlite_path()` function
- `_get_pool()` function
- `_conn()` context manager
- `_cursor()` helper
- `_rows()` helper
- `_row()` helper
- `_P = "%s" if _BACKEND == "postgres" else "?"` module-level constant (ONLY here — not in sub-modules)
- `_ph()` function
- `_ilike()` function
- `_jp()` function
- The `_init_backend()` call at module level (runs at import time)

Preserve the `# ── Section Name ──` separator pattern from db.py.

Do NOT move any schema DDL, CRUD functions, or init_db() into connection.py. Those stay in db.py until extracted in plan 01-02.

**Step 4 — Smoke-test**

Run `python app.py` from the project root (with SECRET_KEY and APP_PASSWORD set in environment or .env). Confirm it starts without errors. The app still imports from db.py (not the db/ package yet — db.py has not been deleted). This is correct at this stage.

IMPORTANT: At the end of plan 01-01, both `db.py` (old monolith) AND `db/` (new package) exist simultaneously. Python will prefer the `db/` package over `db.py` when both are present because packages take precedence over modules with the same name. Verify this doesn't cause conflicts: run `python -c "import db; print(db.__file__)"` — it should show `db/__init__.py`, not `db.py`.

**Step 5 — Commit**

```
git add db/ && git commit -m "refactor(db): create db/ package skeleton (connection.py extracted)"
```

The commit message follows the one-commit-per-sub-module pattern from CONTEXT.md.
  </action>
  <verify>
    <automated>python -m pytest tests/test_db_package.py::test_private_helpers_exported tests/test_db_package.py::test_backend_is_sqlite -x -q</automated>
  </verify>
  <done>
    - db/__init__.py exists with complete commented re-export inventory (connection.py imports active, all others commented with PLAN 01-02 labels)
    - db/connection.py exists with all backend/connection logic extracted from db.py
    - db.py still exists (not deleted)
    - python -c "import db; print(db.__file__)" prints db/__init__.py path
    - test_private_helpers_exported passes (db._BACKEND, db._conn, db._cursor, db._rows, db._row all accessible)
    - test_backend_is_sqlite passes (db._BACKEND == "sqlite" when DATABASE_URL="")
    - Committed with message "refactor(db): create db/ package skeleton (connection.py extracted)"
  </done>
</task>

</tasks>

<verification>
After both tasks complete:

1. pytest collection: `python -m pytest tests/ --collect-only -q` — all 7+ tests discovered
2. Re-export surface: `python -m pytest tests/test_db_package.py::test_private_helpers_exported tests/test_db_package.py::test_backend_is_sqlite -x -q` — both pass
3. Package identity: `python -c "import db; print(db.__file__)"` — prints path ending in `db/__init__.py`
4. db.py presence: db.py still exists at project root (not deleted)
5. Git log: two commits visible — Wave 0 test infrastructure commit + connection.py extraction commit
</verification>

<success_criteria>
Plan 01-01 is complete when:
- tests/ directory contains 5 files (__init__.py, conftest.py, test_db_package.py, test_inf4_startup.py, test_inf3_anthropic.py)
- pytest is installed and runs without error
- db/__init__.py exists with the complete (mostly-commented) re-export inventory
- db/connection.py exists with all backend/connection logic
- db._BACKEND, db._conn, db._cursor, db._rows, db._row are accessible via `import db`
- db.py is still present (deletion deferred to plan 01-03)
- Two commits in git history for this plan
</success_criteria>

<output>
After completion, create `.planning/phases/01-database-decomposition/01-01-SUMMARY.md` with:
- What was created (test infrastructure files + db/ skeleton)
- Connection layer functions extracted into connection.py
- Re-export inventory shape in __init__.py (active vs commented blocks)
- Any discrepancies found during the call-site audit
- Verification commands that passed
</output>