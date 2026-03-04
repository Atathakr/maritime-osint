---
phase: 01-database-decomposition
plan: 02
subsystem: database
tags: [sqlite, postgres, db-package, python-package, extraction, refactor]

# Dependency graph
requires:
  - phase: 01-database-decomposition
    plan: 01
    provides: "db/ skeleton with connection.py, commented __init__.py import blocks"
provides:
  - "db/schema.py: init_db(), _init_postgres(), _init_sqlite(), _migrate_vessels_canonical() — all DDL"
  - "db/vessels.py: vessels_canonical CRUD, screening, ingest log, stats, map data (18 public + 1 private)"
  - "db/sanctions.py: reconciliation utilities find_imo_collisions, find_mmsi_imo_collisions, merge_canonical, rebuild_all_source_tags"
  - "db/ais.py: AIS CRUD, position queries, gap detection, STS candidate detection (11 functions)"
  - "db/findings.py: detection results CRUD for dark periods, STS, speed anomalies, loitering, port calls, PSC, indicator summary (13 functions)"
  - "db/scores.py: Phase 2 placeholder stub (no functions)"
  - "db/__init__.py: fully active re-export surface — all 56 public + 5 private helpers accessible via import db; db.fn()"
affects: [plan-03, phase-2, phase-3, phase-4, phase-5]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Incremental extraction — one sub-module per commit, app importable after each step"
    - "No _P at module level in sub-modules — all use p = '?' if _BACKEND == 'sqlite' else '%s' inside function bodies"
    - "normalize.py imported from project root in sub-modules that need it (not from .)"
    - "Intra-package deps: sanctions.py imports get_vessel_memberships from .vessels"

key-files:
  created:
    - db/schema.py
    - db/vessels.py
    - db/sanctions.py
    - db/ais.py
    - db/findings.py
    - db/scores.py
  modified:
    - db/__init__.py

key-decisions:
  - "normalize.py stays at project root — imported as 'import normalize' in sub-modules (vessels.py, sanctions.py)"
  - "sanctions.py imports get_vessel_memberships from .vessels (intra-package dep) — avoids code duplication for rebuild_all_source_tags"
  - "scores.py is stub only — no functions, no __init__.py export block — Phase 2 fills in"
  - "p = '...' placeholder pattern kept inline in function bodies (not replaced with _ph() calls) to match original db.py style"

patterns-established:
  - "Intra-package imports: from .vessels import fn — acceptable for same-layer dependencies"
  - "Stub pattern: module docstring + TODO comments, no code, scores block in __init__.py stays commented"

requirements-completed: [DB-3]

# Metrics
duration: ~11min
completed: 2026-03-04
---

# Phase 1 / Plan 02: Summary

**db/ package fully extracted — 56 public functions + 5 private helpers accessible via `import db; db.fn()` across 6 domain sub-modules (schema, vessels, sanctions, ais, findings, scores stub)**

## Performance

- **Duration:** ~11 min
- **Completed:** 2026-03-04
- **Tasks:** 2 (schema/vessels/sanctions + ais/findings/scores)
- **Files created:** 6 (schema.py, vessels.py, sanctions.py, ais.py, findings.py, scores.py)
- **Files modified:** 1 (db/__init__.py — all blocks now active)

## Accomplishments

- Extracted all 5 domain sub-modules from db.py incrementally, one commit per sub-module
- All 56 public functions now accessible via `import db; db.fn()` — zero caller changes required
- All 4 DB-3 pytest tests pass: test_all_public_functions_exported, test_private_helpers_exported, test_backend_is_sqlite, test_import_and_init
- db/__init__.py has no commented-out import blocks (except scores placeholder — by design)
- No sub-module defines `_P` at module level — all use inline `p = "?"  if _BACKEND == "sqlite" else "%s"` at function call time
- db.py still present at project root (deletion deferred to plan 01-03)

## Task Commits

Each step committed atomically:

1. **schema.py extraction** — `f1b5b02` (refactor)
2. **vessels.py extraction** — `c6161a7` (refactor)
3. **sanctions.py extraction** — `2aa0a9f` (refactor)
4. **ais.py extraction** — `2d69c6f` (refactor)
5. **findings.py extraction** — `7bc14e2` (refactor)
6. **scores.py stub** — `f6945b0` (refactor)

## Files Created/Modified

- `db/schema.py` — All DDL: init_db(), _init_postgres(), _init_sqlite(), _migrate_vessels_canonical()
- `db/vessels.py` — Vessels CRUD, screening queries (_screen_canonical private), ingest log, stats, map data
- `db/sanctions.py` — Reconciliation: find_imo_collisions, find_mmsi_imo_collisions, merge_canonical, rebuild_all_source_tags
- `db/ais.py` — AIS positions and vessel static CRUD, gap detection, STS candidates
- `db/findings.py` — Detection results: dark periods, STS events, speed anomalies, loitering, port calls, PSC, indicator summary
- `db/scores.py` — Stub only (Phase 2 placeholder, no functions)
- `db/__init__.py` — All import blocks active (schema, vessels, sanctions, ais, findings); scores block kept commented

## Decisions Made

- `sanctions.py` imports `get_vessel_memberships` from `.vessels` — intra-package dependency needed by `rebuild_all_source_tags`; acceptable because sanctions is at the same db/ layer, not circular
- Kept inline `p = "?" if _BACKEND == "sqlite" else "%s"` pattern in function bodies (matching original db.py style) rather than replacing with `_ph()` calls — preserves verbatim copy intention
- `scores.py` scores block in `__init__.py` left commented with Phase 2 note — no functions to export in Phase 1

## Deviations from Plan

None — plan executed exactly as written. All 6 sub-modules extracted and committed in the specified sequence.

## Issues Encountered

None — extraction was straightforward. The only observation: `test_anthropic_not_in_requirements`, `test_anthropic_not_in_pyproject`, `test_no_anthropic_imports` (INF-3) already pass without Plan 01-03 intervention — anthropic SDK was already absent. The INF-4 startup enforcement tests (test_missing_secret_key, test_missing_app_password) fail as expected — Plan 01-03 work.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `db/` package is fully extracted; all public + semi-private APIs accessible via `import db; db.fn()`
- Plan 01-03 can begin immediately: delete db.py, enforce SECRET_KEY/APP_PASSWORD, confirm INF-3 removal
- Phase 2 can build on db/scores.py stub to add vessel_scores table DDL and CRUD
- Phase 3 detection tests can import directly from `db` with confidence the package is stable

---
*Phase: 01-database-decomposition*
*Completed: 2026-03-04*
