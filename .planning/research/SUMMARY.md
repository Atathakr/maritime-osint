# Research Summary — maritime-osint Production Maturity Pass

**Project:** maritime-osint
**Domain:** Maritime threat intelligence platform — Flask + PostgreSQL, solo-operator Railway deployment
**Researched:** 2026-03-03
**Confidence:** HIGH (db decomposition, security libs, testing patterns), MEDIUM (APScheduler multi-worker behavior, Flask-Limiter PostgreSQL URI format)

---

## Executive Summary

The maritime-osint platform has a sound detection and ingestion foundation but has reached a structural inflection point. Three independent problems — a 2,835-line `db.py` monolith, risk scores computed on-demand per request, and no test coverage on the detection modules — have reached the point where adding any new capability risks cascading failures. This milestone is a deliberate structural pass before the platform becomes harder to change than it is to rewrite.

The recommended approach is to sequence the four work areas by dependency, not by apparent urgency. Database decomposition must come first because every other area builds on it: pre-computed scores need a new `db/scores.py` module, tests need `db/schema.py` to initialize in-memory SQLite fixtures, and the security hardening needs a clean, stable API surface to know what to exempt from CSRF. The instinct to start with security (visible, testable in browser) or frontend (immediately impressive) is precisely backwards — those layers depend on correct data infrastructure underneath them.

The single most dangerous risk in this milestone is what the pitfalls research calls "silent breakage at request time." Every major change in this pass — the db package re-export surface, CSRF exemptions, rate-limit storage backend, and mock patch targets after the split — can appear to work in local development while silently failing in production for less-frequently-exercised routes. The mitigation strategy is the same in each case: write verification artifacts (full re-export inventory, conftest DATABASE_URL override, CSP in report-only mode, mock call-count assertions) before the behavior change lands.

---

## Key Findings

### Stack: Four Targeted Additions to a Fixed Base

The base stack (Python 3.11, Flask 3.1, PostgreSQL, Railway, Gunicorn) does not change. This milestone adds exactly four library groups:

**New production dependencies:**
- **APScheduler 3.x** — in-process scheduled score refresh every 15 minutes; runs inside the existing Gunicorn process with no new services. Stay on 3.x (4.x is a 2024 major rewrite with API changes).
- **Flask-Limiter 3.5.x** — rate limiting on `/login`; must use `storage_uri=DATABASE_URL` (PostgreSQL), not the default in-memory storage which resets on every deploy and divides by worker count.
- **Flask-WTF 1.2.x** — CSRF protection on `/login` form only; all `/api/*` routes must be explicitly exempted.
- **flask-talisman 1.1.x** — security headers (CSP, HSTS, X-Frame-Options); set `force_https=False` on Railway (TLS terminates at the edge proxy, not Gunicorn).

**New dev dependencies:**
- **pytest 8.x + pytest-mock 3.12.x + pytest-cov 5.x** — test infrastructure for detection modules; no async test framework needed for this milestone.

**What was explicitly ruled out:** Celery + Redis (overkill for one periodic task), PostgreSQL triggers (can't call Python detection logic), `threading.Timer` (no visibility or error handling), Redis for rate-limit storage (adds a Railway service for a problem PostgreSQL already solves), and `pytest-asyncio` (defer until AIS listener refactoring).

See `STACK.md` for full version pinning and alternatives rationale.

---

### Features: The Dashboard Has a Credibility Problem

The platform's core failure mode is invisible to the developer but fatal to the analyst user: the dashboard does not yet surface the data it has computed. An analyst opening the tool today cannot answer "which vessel is highest risk?" without running SQL queries directly.

**Must have (P0 — analyst credibility blockers):**
- **F1: Vessel ranking table** — sortable by composite score descending, paginated, <500ms load time; requires pre-computed scores (depends on database area)
- **F2: Risk score as number** — numeric score (0-99) displayed everywhere alongside the existing label; labels alone fail audit defensibility
- **F3: Data freshness stamps** — AIS last seen, sanctions screened, score computed-at on every vessel view; stale scores (>2h) flagged visually; requires `computed_at` field from database area
- **F4: Indicator point-contribution breakdown** — which of the 31 indicators fired, points each contributed, timestamp of detection; requires `indicator_breakdown JSONB` stored alongside composite score

**Should have (P1 — production-ready):**
- **F5: Score explanation narrative** — auto-generated plain-English summary from indicator breakdown (depends on F4)
- **F6: Risk-colored table rows** — visual tier breaks in ranked list (depends on F1)
- **F7: Vessel permalink** — stable `/vessel/<imo>` URL for sharing and investigation notes
- **F8: CSV export** — from filtered ranking table; standard analyst workflow requirement

**Defer (P2):**
- **F9: Global search bar** — API exists (`/api/screen`); P2 is dashboard-native access
- **F10: AIS track replay** — high frontend effort; AIS data already stored; defer until P0/P1 are live

**Critical dependency chain:** F1, F3, and F4 all depend on the database area delivering pre-computed scores with `computed_at` and `indicator_breakdown JSONB`. Frontend work should not begin until the database area is complete.

See `FEATURES.md` for acceptance criteria per feature.

---

### Architecture: Four Structural Improvements, Layered Model Preserved

The existing Flask layered pipeline is sound. This pass adds a security layer and a background scheduling layer without breaking the layer model. The major structural changes are:

**New `db/` package (replaces `db.py` monolith):**

```
db/
├── __init__.py    -- public API re-exports; callers never change
├── connection.py  -- _conn(), _ph(), _ilike(), backend detection
├── schema.py      -- init_db(), all CREATE TABLE DDL
├── vessels.py     -- vessels_canonical CRUD
├── sanctions.py   -- sanctions_entries CRUD
├── ais.py         -- ais_positions, ais_vessel_static CRUD
├── detection.py   -- detection result CRUD
└── scores.py      -- vessel_scores, vessel_score_history CRUD (NEW)
```

**Key rule:** Sub-modules import only from `connection.py`. No sub-module imports another sub-module. Circular imports are prevented by design.

**New `vessel_scores` table (replaces on-demand computation):**
- Schema: `(mmsi PK, composite_score, is_sanctioned, indicator_json JSONB, computed_at TIMESTAMPTZ)`
- Indexed on `composite_score DESC` for fast ranking queries
- Companion `vessel_score_history` table (append-only, 90-day retention) for trend visibility
- Staleness fallback in `screening.py`: if score >30 min old and scheduler hasn't run, compute on demand and upsert

**New `security.py` module:**
- Single `init_security(app)` call at app creation; not per-route decorators
- Handles Flask-Limiter, CSRFProtect, and Talisman initialization in one place
- Keeps security policy visible and consistently applied to future routes

**Detection module refactoring for testability:**
- Extract `detect(positions: list[dict]) -> list[dict]` as pure function alongside existing `run_detection(mmsi)`
- Tests call `detect()` directly with synthetic fixtures; no database required for unit tests
- `run_detection()` becomes a thin wrapper: fetch positions from DB, call `detect()`, persist results

**Suggested build order from ARCHITECTURE.md:**

```
Phase 1: db/ decomposition  (zero behavior change; foundation for all else)
    |
Phase 2: pre-computed scores    Phase 3: detection tests  (these can run in parallel)
    |                               |
    +------------- Phase 4: security hardening + frontend UX ---------------+
```

See `ARCHITECTURE.md` for complete component boundary table and anti-patterns.

---

### Critical Pitfalls

Research identified 7 critical pitfalls and 9 moderate pitfalls. The most dangerous share a common property: they pass in local development and fail silently in production.

**1. Flask-Limiter in-memory storage (A1 + A4 together) — login rate limiting provides false security**
Default `Limiter()` stores counters in memory: resets on every Railway deploy, divided by Gunicorn worker count. Additionally, `get_remote_address` behind Railway's proxy reads the proxy IP, not the client IP — one user's attempts block all users.
Prevention: `storage_uri=DATABASE_URL` at construction + `ProxyFix(app.wsgi_app, x_for=1)` before `Limiter()`. Both must be set together.

**2. flask-talisman CSP silently kills the dashboard (A2)**
Default CSP blocks all inline `<script>` tags. The dashboard uses Jinja2 templates with inline scripts for charts and map data. Breakage is browser-side only — Flask logs show nothing. Analysts lose the dashboard entirely.
Prevention: Audit all templates for inline scripts first. Deploy in `content_security_policy_report_only=True` mode on Railway. Check browser console. Move inline JS to `static/` files before enabling enforcement.

**3. CSRF protection breaks all JSON API endpoints (A3)**
`CSRFProtect(app)` applied globally silently returns 400 on all `/api/*` POSTs. Scheduled ingests stop. Sanctions lists go stale. No log error indicates the cause.
Prevention: Explicitly exempt all `/api/*` routes. Apply CSRF only to `/login` HTML form.

**4. `_P` placeholder evaluated at module load — db package split breaks PostgreSQL silently (B1)**
`_P = "%s" if _BACKEND == "postgres" else "?"` is a module-level constant. Sub-modules that duplicate this logic evaluate it at their own import time, before `_init_backend()` runs. SQLite `?` reaches psycopg2 in production as `ProgrammingError`. Local SQLite dev continues to work.
Prevention: Keep `_ph()`, `_ilike()`, `_conn()` exclusively in `db/connection.py`. No sub-module defines its own placeholder logic.

**5. Missing re-exports in `db/__init__.py` fail at request time, not startup (B2)**
`AttributeError` on less-used routes in production, not at startup. Routes not exercised in smoke testing appear healthy.
Prevention: Build the complete re-export inventory from `grep "db\."` across all callers before splitting. Verify `__init__.py` re-exports every function found.

**6. Risk scores stored without version or staleness tracking (C1 + C2 together)**
When `risk_config.py` changes, stored scores instantly become wrong but look valid. When a new OFAC ingest adds a vessel to the SDN list, the pre-sanction score persists until the next scheduled recompute.
Prevention: Store `computed_at` on every score row (already in the schema pattern). Add `mark_risk_scores_stale()` call at the end of every ingest function. Show freshness metadata in the UI.

**7. Detection tests referencing hardcoded values miss threshold boundary logic (D1 + D2 together)**
Tests with `gap_hours=25` pass when `CRITICAL_HOURS=24` but also pass when the comparison is accidentally inverted. CI environments with `DATABASE_URL` set will connect detection fixture tests to PostgreSQL instead of in-memory SQLite.
Prevention: Reference constants in fixtures (`gap_hours = dark_periods.CRITICAL_HOURS + 0.1`). Write boundary tests at `threshold - 0.1` (must NOT trigger) and `threshold + 0.1` (must trigger). Set `os.environ["DATABASE_URL"] = ""` in `conftest.py` before any `import db`.

See `PITFALLS.md` for the complete 16-pitfall inventory with per-pitfall warning signs.

---

## Implications for Roadmap

### Phase 1: Database Decomposition

**Rationale:** Foundation work. Zero behavior change. Every other phase benefits: pre-computed scores need `db/scores.py`, tests need `db/schema.py` for fixtures, security hardening needs a stable re-export surface to audit for mock targets. Doing this last means doing it under pressure while other things are breaking.

**Delivers:**
- `db/` package with 8 focused modules replacing the 2,835-line monolith
- `db/__init__.py` re-export surface that all callers continue using unchanged
- Clean separation: connection, schema, vessels, sanctions, ais, detection, scores

**Avoids:**
- Pitfall B1 (`_P` module-load order) — mitigated by keeping all backend logic in `connection.py`
- Pitfall B2 (missing re-exports) — mitigated by auditing callers before splitting
- Pitfall B3 (circular imports) — mitigated by the sub-module import rule
- Pitfall B4 (nested `_conn()` transactions) — mitigated during extraction by passing `conn` parameters
- Pitfall B5 (`normalize.py` duplication) — keep at project root

**Key constraint:** Migrate incrementally — one sub-module at a time — running existing tests (once they exist) after each extraction. Do not do a big-bang split.

**Research flag:** Standard patterns. No additional research needed.

---

### Phase 2: Pre-Computed Risk Scores

**Rationale:** Unblocks the entire frontend. The vessel ranking table (F1), freshness stamps (F3), and indicator breakdown (F4) are all blocked until scores are pre-computed and stored with `computed_at` and `indicator_json`. This is also the phase with the highest concentration of subtle production bugs (C1, C2, C3).

**Delivers:**
- `vessel_scores` table with `(mmsi, composite_score, is_sanctioned, indicator_json JSONB, computed_at)`
- `vessel_score_history` table with 90-day retention policy
- APScheduler job refreshing all scores every 15 minutes (in-process, no new services)
- Staleness fallback in `screening.py` for scores >30 minutes old
- `mark_risk_scores_stale()` calls added to all ingest functions

**Uses:** APScheduler 3.x (new), `db/scores.py` (from Phase 1)

**Avoids:**
- Pitfall C1 (no version tracking) — store `computed_at`, implement staleness fallback
- Pitfall C2 (no invalidation after ingest) — `mark_risk_scores_stale()` at end of every ingest function
- Pitfall C3 (AIS flush race) — filter `position_ts < NOW() - interval '1 minute'` in score recompute
- Pitfall C4 (unbounded history table) — retention policy created at table creation time

**Implementation note (from STACK.md):** The ARCHITECTURE.md recommends a `vessel_scores` table populated by Python (not a PostgreSQL materialized view) because composite scoring requires Python logic — haversine distance, ownership-chain fuzzy matching, configurable thresholds from `risk_config.py` — none of which are expressible as SQL.

**APScheduler + Gunicorn:** With 2 workers, both start APScheduler instances, causing double-refresh. Use a PostgreSQL advisory lock inside the refresh function to skip if another worker is already refreshing, or reduce to 1 Gunicorn worker on the Railway hobby tier.

**Research flag:** No additional research needed. APScheduler 3.x patterns are well-established.

---

### Phase 3: Detection Test Coverage

**Rationale:** Can run in parallel with Phase 2. Tests provide a safety net for Phase 4 (security changes touch `app.py` and affect routes the security libraries will wrap). Having coverage before security hardening reduces the risk of silent regressions. Also: the db decomposition from Phase 1 enables `init_db(conn)` in `conftest.py` for in-memory SQLite fixtures.

**Delivers:**
- Pure `detect(positions)` function extracted from each of the 5 detection modules
- `tests/conftest.py` with in-memory SQLite fixture and environment guards
- `tests/fixtures/ais_factory.py` with position sequence generators
- Test suites for dark_periods, sts_detection, loitering, spoofing, screening
- Coverage targets: 80% dark_periods/STS, 75% loitering/spoofing, 70% screening

**Uses:** pytest 8.x, pytest-mock 3.12.x, pytest-cov 5.x (new)

**Avoids:**
- Pitfall D1 (hardcoded thresholds) — fixtures reference module constants, boundary tests at `threshold ± epsilon`
- Pitfall D2 (CI DATABASE_URL) — `conftest.py` clears `DATABASE_URL` before any `import db`
- Pitfall D3 (large fixtures) — maximum 10 position rows per unit test; perf tests in `tests/perf/`
- Pitfall D4 (mock scope after split) — verify patch targets against new `db.*` re-export surface; add `assert mock.call_count > 0`
- Pitfall D5 (AIS listener auto-start) — `conftest.py` clears `AISSTREAM_API_KEY` before `from app import app`

**Research flag:** Standard patterns. pytest fixture patterns are well-documented.

---

### Phase 4: Security Hardening + Frontend UX

**Rationale:** Comes last because it requires all prior phases to be complete. Security hardening needs the stable `db/` surface (Phase 1) and the test safety net (Phase 3). The analyst-facing dashboard features (F1, F3, F4) need pre-computed scores (Phase 2). This phase has the highest visible surface area but the most hidden failure modes.

**Delivers — Security:**
- New `security.py` with `init_security(app)` encapsulating all three security libraries
- Flask-Limiter on `/login` with PostgreSQL storage backend and ProxyFix middleware
- CSRFProtect on `/login` only; all `/api/*` routes explicitly exempted
- flask-talisman with CSP tuned for Leaflet CDN (unpkg.com + OSM tiles) and `force_https=False`
- HSTS starting at `max_age=300`, increased after verification
- 7 CodeQL false positives formally dismissed with documented rationale
- `SECRET_KEY` enforced via `os.environ["SECRET_KEY"]` (KeyError on missing, not auto-generated)

**Delivers — Frontend:**
- Vessel ranking table (F1): sortable by score, paginated, <500ms using `vessel_scores` index
- Risk scores as numbers everywhere (F2): integer score alongside label in table, profile, map popup
- Data freshness stamps (F3): "AIS last seen: 3h ago", "Score computed: 18 min ago" on all vessel views
- Indicator breakdown (F4): per-indicator points and timestamps from `indicator_json JSONB`
- Score narrative (F5): auto-generated from F4 breakdown
- Risk-colored table rows (F6)
- Vessel permalink (F7): stable `/vessel/<imo>` route
- CSV export (F8): from filtered ranking table

**Uses:** Flask-Limiter 3.5.x, Flask-WTF 1.2.x, flask-talisman 1.1.x (all new)

**Avoids:**
- Pitfall A1 (in-memory rate limit storage) — `storage_uri=DATABASE_URL` at construction
- Pitfall A2 (CSP kills dashboard) — template audit and report-only mode before enforcement
- Pitfall A3 (CSRF breaks API) — explicit exemption of all `/api/*` routes
- Pitfall A4 (proxy IP collapse) — ProxyFix before Limiter initialization
- Pitfall A5 (HSTS lockout) — start at `max_age=300`

**Research flag:** CSP template audit is implementation-time work, not research. No additional pre-phase research needed. Verify Flask-Limiter PostgreSQL URI format against Railway `DATABASE_URL` format during implementation (MEDIUM confidence item from STACK.md).

---

### Phase Ordering Rationale (Cross-Cutting)

Three dependency chains drive the ordering:

**Data before display:** F1, F3, F4 (analyst credibility features) require pre-computed scores with `computed_at` and `indicator_json JSONB`. The dashboard cannot deliver its value proposition until the database delivers these fields. Starting with frontend would produce a performance-limited UI that needs to be rebuilt.

**Foundation before feature:** The db package split is pure refactoring with zero behavior change, making it the safest phase to do first. It creates the `db/scores.py` module that Phase 2 needs, the `db/schema.py` module that Phase 3 test fixtures need, and a clean, auditable re-export surface that Phase 4 mock-patching depends on.

**Safety net before security:** Phase 3 tests exist before Phase 4 security changes touch `app.py`. Security middleware applied incorrectly can silently break routes. Having tests that exercise those routes (including the `AISSTREAM_API_KEY` and `DATABASE_URL` guards) means the breakage is caught before a Railway deploy.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (3 of 4 areas) / MEDIUM (1 of 4) | Flask-WTF, flask-talisman, pytest selections are definitive. Flask-Limiter PostgreSQL storage URI format needs implementation-time verification against Railway `DATABASE_URL` format. APScheduler 3.x is stable; multi-worker advisory lock pattern is an implementation detail. |
| Features | HIGH | Analyst credibility requirements (ranking table, numeric scores, freshness stamps, indicator breakdown) are established patterns in the maritime OSINT domain (Windward, Pole Star, Sayari all lead with ranked vessel lists). Feature priority matrix has clear dependency ordering. |
| Architecture | HIGH (db decomposition, security layer, test patterns) / MEDIUM (APScheduler version import path) | Python package + re-export pattern is definitive. `detect(positions)` pure function extraction is standard. Security layer centralization in `security.py` is well-established. APScheduler version compatibility should be verified at install time. |
| Pitfalls | HIGH (B, C, D areas) / MEDIUM (A area) | B, C, D pitfalls confirmed against actual codebase: `_P` at line 105, no `computed_at` on scores, threshold constants at module level, auto-start at `app.py` lines 37-39. A-area pitfalls (Railway proxy behavior, TLS termination) based on training knowledge — verify with test deploy. |

**Overall confidence: HIGH**

The research is grounded in the actual codebase structure (specific line numbers, confirmed function names, confirmed import patterns). The only MEDIUM-confidence items are library-to-Railway integration details that require a test deploy to verify — they do not affect the phase structure or ordering decisions.

---

### Gaps to Address During Implementation

**Flask-Limiter PostgreSQL URI format:** Railway's `DATABASE_URL` uses the `postgres://` scheme. Some versions of the `limits` library's PostgreSQL backend require `postgresql://`. Verify during Phase 4 implementation before assuming it works.

**APScheduler double-refresh in Gunicorn multi-worker:** STACK.md notes that 2 Gunicorn workers both start APScheduler instances, causing double-refresh every 15 minutes. This is harmless (CONCURRENTLY refresh is idempotent) but wastes CPU. Decide during Phase 2 implementation: PostgreSQL advisory lock inside `refresh_risk_scores()`, or reduce to 1 Gunicorn worker on hobby tier.

**Detection function `db_conn` injection:** STACK.md notes that the current `run_detection()` signatures may not accept a `db_conn` parameter for test injection. The ARCHITECTURE.md pattern (`detect(positions)` pure function) sidesteps this entirely. Confirm during Phase 3 that each detection module can be refactored to expose a pure function without breaking the production `run_detection()` call path.

**CSP inline script audit scope:** ARCHITECTURE.md flags `{{ data | tojson }}` inside `<script>` tags as a CSP-breaking pattern. The number of templates containing this pattern is unknown. Do this audit as the first task of Phase 4 to size the work before committing to a sprint.

**Local SQLite dev story:** PROJECT.md flags the 213MB local SQLite file with WAL fragments as an unresolved concern. The dual-backend is the primary driver of `db.py` complexity. This milestone preserves the dual-backend (explicitly in scope constraints), but the Phase 1 db decomposition creates a natural checkpoint to assess whether to deprecate it in the next milestone.

---

## Sources

All findings are grounded in direct analysis of the codebase at the time of research (2026-03-03) combined with training knowledge of the Flask, PostgreSQL, and pytest ecosystems. No external searches were performed (tools unavailable at research time). Confidence ratings reflect this.

**Codebase-confirmed findings (HIGH confidence):**
- `db.py` is 2,835 lines; `_P` module-level constant at line 105; `import normalize` at line 16
- All callers use `import db; db.function()` pattern (confirmed across app.py, screening.py, dark_periods.py, loitering.py, sts_detection.py, spoofing.py, reconcile.py, ingest.py, noaa_ingest.py, ports.py)
- Threshold constants at module level in `dark_periods.py` and `loitering.py`
- AIS listener auto-start at `app.py` lines 37-39 when `AISSTREAM_API_KEY` is set
- No `computed_at` or `indicator_json` fields on any current risk score storage
- No ingest functions call score invalidation after completing

**Ecosystem patterns (HIGH confidence):**
- Flask-WTF, flask-talisman, pytest 8.x — canonical, well-maintained, Flask 3.x compatible
- Python package + `__init__.py` re-export pattern — standard, no edge cases
- `detect(positions)` pure function extraction — standard algorithmic refactoring

**Railway-specific behavior (MEDIUM confidence — verify with test deploy):**
- `force_https=False` in flask-talisman required for Railway TLS termination at edge proxy
- Flask-Limiter PostgreSQL storage URI format compatibility with Railway `DATABASE_URL` scheme
- ProxyFix `x_for=1` depth for Railway proxy headers

---
*Research completed: 2026-03-03*
*Ready for roadmap: yes*
