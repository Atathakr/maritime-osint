# Domain Pitfalls

**Domain:** Flask + PostgreSQL maritime intelligence application — production maturity hardening
**Researched:** 2026-03-03
**Confidence:** MEDIUM — verified against codebase structure; library-specific claims based on training knowledge (August 2025 cutoff).

---

## Area Index

| ID | Area | Severity |
|----|------|----------|
| A | Flask security hardening (flask-limiter, flask-wtf, flask-talisman) | Critical + Moderate |
| B | Splitting monolithic db.py | Critical + Moderate |
| C | Pre-computed risk scores / caching | Critical + Moderate |
| D | Retroactive test coverage for detection logic | Critical + Moderate |

---

## Critical Pitfalls

### Pitfall A1: flask-limiter uses in-memory storage by default — resets on every deploy
**Area:** A

flask-limiter's default storage is an in-memory dict that resets on every process start. Railway redeploys reset all counters. Gunicorn's 2 workers each have independent counters, so an attacker gets `5 attempts × 2 workers = 10 attempts per window` with no cross-worker coordination. This provides false security confidence — the rate limit appears to work in local development.

**Prevention:** Specify `storage_uri=os.getenv("DATABASE_URL")` at `Limiter()` construction. Railway's PostgreSQL plugin is already available.

**Warning signs:** `Limiter(app, storage_uri=None)`, Gunicorn with `--workers > 1`, rate limits resetting after `railway up`.

---

### Pitfall A2: flask-talisman CSP blocks inline JavaScript and kills the dashboard
**Area:** A

Default CSP is `default-src 'self'` which blocks all inline `<script>` tags and inline event handlers. The dashboard uses Jinja2 templates with inline scripts for charts and map data. The breakage is completely invisible in Flask logs — it's a browser-side enforcement failure. Analysts lose the dashboard entirely.

**Prevention:** (1) Audit every template for inline scripts first. (2) Start with `content_security_policy_report_only=True` on Railway and check browser console. (3) Move all inline JS to `static/` files before enabling enforcement.

**Warning signs:** Any `<script>` tag in templates containing actual JavaScript, any `{{ data | tojson }}` inside a `<script>` tag, any `onclick=` attributes.

---

### Pitfall A3: CSRF protection breaks all JSON API endpoints
**Area:** A

`CSRFProtect(app)` applied globally validates tokens on every POST. The app has 15+ `/api/*` endpoints called programmatically — `/api/ingest/ofac`, `/api/screen`, `/api/dark-periods/detect`, etc. These will all return 400 silently. Scheduled ingests stop working. Sanctions lists go stale without any log error.

**Prevention:** Exempt all `/api/*` routes with `@csrf.exempt`, or apply `CSRFProtect` only to the login form via `WTF_CSRF_CHECK_DEFAULT = False` with selective `@csrf.protect`.

**Warning signs:** `CSRFProtect(app)` in `app.py` without `@csrf.exempt` decorators, ingest logs showing no entries after the change.

---

### Pitfall B1: `_P` evaluated at module load — splitting breaks the dual-backend silently
**Area:** B

`db.py` line 105: `_P = "%s" if _BACKEND == "postgres" else "?"` is a module-level constant. When `db.py` is split into a package, sub-modules that need `_P` will evaluate it at their own import time, potentially before `_init_backend()` has run. SQLite `?` gets sent to psycopg2 on production PostgreSQL, causing `ProgrammingError: syntax error at or near '?'`. Local SQLite development continues to work, masking the breakage.

**Prevention:** Create `db/_backend.py` (or `db/connection.py`) as the single source of truth containing `_init_backend()`, `_BACKEND`, `_ph()`, `_ilike()`, `_conn()`. All other sub-modules import only from `db.connection`.

**Warning signs:** Sub-module defining `p = "?" if backend == "sqlite" else "%s"` independently, tests pass locally but fail on Railway.

---

### Pitfall B2: Callers use `import db` — missing re-exports break routes silently at request time
**Area:** B

All callers — `app.py`, `screening.py`, `dark_periods.py`, `loitering.py`, `sts_detection.py`, `spoofing.py`, `reconcile.py`, `ingest.py`, `noaa_ingest.py`, `ports.py` — use `import db; db.some_function()`. Converting `db.py` to a package requires `db/__init__.py` to re-export every function. Missing re-exports don't fail at startup — they fail as `AttributeError` at the first request that exercises that route. Less-used routes break silently in production.

**Prevention:** Write `db/__init__.py` first (re-importing everything), before splitting. Run `grep -r "db\." app.py screening.py dark_periods.py loitering.py sts_detection.py spoofing.py reconcile.py ingest.py noaa_ingest.py ports.py` to build the complete re-export inventory.

**Warning signs:** `__init__.py` shorter than 20 lines when original `db.py` exported 30+ functions, new 500 errors on endpoints not exercised in smoke testing.

---

### Pitfall C1: Risk scores stored without version tracking — stale scores indistinguishable from fresh
**Area:** C

When `risk_config.py` changes (flag tier weights, `IND23_AGE_THRESHOLD`, `IND21_OWNER_SANCTION`), stored scores instantly become wrong but look valid. A vessel that should score CRITICAL after Panama moves to Tier 2 continues showing its pre-change score.

**Prevention:** Store `risk_score_version` (a hash of `risk_config.py` constants) alongside `risk_score`. Invalidate scores on version mismatch. Alternatively, store `risk_score_computed_at` with a configurable TTL.

**Warning signs:** `risk_score` column added without `risk_score_version` or `risk_score_computed_at`, no mechanism to detect scoring-config changes.

---

### Pitfall D1: Detection thresholds are module-level constants — tests validate current values, not boundary logic
**Area:** D

`dark_periods.py` defines `DARK_THRESHOLD_HOURS = 2.0`, `HIGH_RISK_HOURS = 6.0`, `CRITICAL_HOURS = 24.0` as module-level constants. Tests that use hardcoded fixture values (`gap_hours=25`) pass when `CRITICAL_HOURS=24` but will still pass if `CRITICAL_HOURS` is changed to 36. A refactored comparison that inverts a boundary (`>=` to `>`) won't be caught by tests that only test well-above-threshold values.

**Prevention:** Fixtures must reference the constants: `gap_hours = dark_periods.CRITICAL_HOURS + 0.1`. Write explicit boundary tests at `threshold - 0.1` (must NOT trigger) and `threshold + 0.1` (must trigger).

**Warning signs:** Test fixtures with hardcoded numeric values like `gap_hours=25`, no test cases at `threshold - epsilon`.

---

## Moderate Pitfalls

### Pitfall A4: Rate limiting by IP fails behind Railway's reverse proxy
**Area:** A

Railway proxies requests; `request.remote_addr` is always the proxy's IP. All users share one rate limit counter. One user's 5 login attempts locks out everyone.

**Prevention:** Add `ProxyFix` middleware: `app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)`.

**Warning signs:** `Limiter(key_func=get_remote_address)` without ProxyFix, rate limit blocking all users simultaneously.

---

### Pitfall A5: HSTS with long max-age on Railway subdomain causes permanent lockout on domain change
**Area:** A

`strict_transport_security_max_age=31536000` on day one means a year-long lockout if the Railway domain changes or cert expires.

**Prevention:** Start with `max_age=300`, verify, then gradually increase. Never set `preload=True` unintentionally.

---

### Pitfall B3: Circular import — `db/detection.py` cannot import from `dark_periods.py`
**Area:** B

`dark_periods.py` imports `db`; `loitering.py` imports `HIGH_RISK_ZONES` from `dark_periods`. If `db/detection.py` tries to import zone constants from `dark_periods.py`, a circular import cycle is created.

**Prevention:** Extract all shared domain constants (`HIGH_RISK_ZONES`, thresholds) to a standalone `constants.py` that neither `db/` nor detection modules import from each other.

**Warning signs:** `db/detection.py` containing `from dark_periods import HIGH_RISK_ZONES`, `ImportError` at startup after the split.

---

### Pitfall B4: Nested `_conn()` calls create implicit nested transactions
**Area:** B

`_conn()` commits on exit. If a function in `db/ingestion.py` calls a helper from `db/detection.py` which also opens `_conn()`, the inner commit happens before the outer function finishes. On PostgreSQL: constraint violations or partial writes. On SQLite: `database is locked`.

**Prevention:** Internal DB helper functions must accept a `conn` parameter rather than opening their own connection.

---

### Pitfall C2: No score invalidation after ingestion — newly-sanctioned vessels keep old scores
**Area:** C

When a new OFAC ingest adds a vessel to the SDN list, the pre-computed score doesn't update until the next scheduled recompute. The dashboard shows a pre-sanction score during the gap.

**Prevention:** Add `db.mark_risk_scores_stale()` at the end of every ingest function. Show score freshness metadata in the dashboard UI.

**Warning signs:** Ingest functions with no score invalidation call, no `risk_score_stale` column.

---

### Pitfall C3: Race condition between AIS listener flush and score recompute job
**Area:** C

The AIS listener buffers 50 positions before flushing (`BUFFER_SIZE = 50`). A score recompute reading `ais_positions` mid-flush excludes the buffered positions. Next recompute scores jump up, appearing as a scoring anomaly.

**Prevention:** Score recomputes must filter `position_ts < NOW() - interval '1 minute'` to exclude in-flight positions.

---

### Pitfall D2: CI has `DATABASE_URL` set — SQLite fixtures connect to PostgreSQL instead
**Area:** D

`_init_backend()` reads `DATABASE_URL` from the environment. CI environments inheriting Railway secrets will have `DATABASE_URL` set. Tests populating SQLite fixtures will fail with `psycopg2.OperationalError: could not connect to server`.

**Prevention:** `conftest.py` must set `os.environ["DATABASE_URL"] = ""` before any `import db`. Add `assert db._BACKEND == "sqlite"` as first assertion in SQLite-fixture tests.

---

### Pitfall D3: Large detection test fixtures exhaust memory or time out in CI
**Area:** D

A test inserting 100,000 position rows to "simulate realistic conditions" will time out or OOM in CI, leading developers to delete it. Unit test fixtures use the minimum rows to trigger each code path (2-10 rows per MMSI). Performance tests live in `tests/perf/` and run manually only.

---

### Pitfall D4: `unittest.mock.patch` target scope changes after db.py split
**Area:** D

After the db.py split, if `get_vessel_ownership` moves to `db.screening_queries` but is re-exported from `db.__init__`, the patch target `"db.get_vessel_ownership"` remains correct — but only if `__init__.py` re-exports it. If not re-exported, the patch silently has no effect and the real database is called.

**Prevention:** After the split, add `assert mock.call_count > 0` in every test that mocks a DB function. Re-verify all patch targets.

---

### Pitfall D5: Tests that import `app.py` auto-start the AIS listener if `AISSTREAM_API_KEY` is set
**Area:** D

`app.py` auto-starts the AIS listener on import when `AISSTREAM_API_KEY` is set. CI environments with the key set will start WebSocket connections to aisstream.io during test runs.

**Prevention:** Unset `AISSTREAM_API_KEY` in `conftest.py` before any `from app import app`.

---

## Minor Pitfalls

### Pitfall A6: Talisman `force_https` redirects break Railway's health check
**Area:** A

Railway health checks call `/health` over HTTP. If `force_https=True` returns 301, some configurations treat redirects as failures and cycle the container.

**Prevention:** Apply `force_https=False` globally (correct Railway config) or exempt `/health` explicitly.

---

### Pitfall B5: `normalize.py` must not be moved inside `db/`
**Area:** B

`db.py` line 16 imports `normalize`. If `normalize.py` is copied into `db/normalize.py` during the split, two divergent versions exist.

**Prevention:** `normalize.py` stays at project root. All `db/` sub-modules `import normalize` from the root.

---

### Pitfall C4: Risk score history table grows unbounded like `ais_positions`
**Area:** C

Daily recomputes × 5,000 vessels = 1.8M rows/year. Railway hobby tier storage will be exhausted.

**Prevention:** Create the retention policy (`DELETE WHERE computed_at < NOW() - INTERVAL '90 days'`) at the same time as creating the table.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Add flask-limiter to `/login` | A1 (in-memory resets), A4 (proxy IP collapse) | PostgreSQL storage backend; add ProxyFix |
| Add flask-talisman | A2 (CSP kills inline scripts) | Audit templates; start in report-only mode |
| Add CSRF protection | A3 (breaks all JSON API endpoints) | Exempt `/api/*` routes explicitly |
| Split db.py into package | B1 (`_P` import order), B2 (missing re-exports), B3 (circular imports) | Create `db/connection.py` first; write `__init__.py` before splitting |
| Add risk score columns | C1 (no version tracking), C2 (no invalidation after ingest) | Add `risk_score_version` and `risk_score_stale` on day one |
| Write detection tests | D1 (threshold coupling), D2 (backend mismatch in CI), D4 (mock scope) | Reference constants in fixtures; override `DATABASE_URL` in conftest |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Flask security hardening (A) | MEDIUM | Codebase-confirmed: inline auth, multi-worker Gunicorn, API-heavy route pattern all present |
| db.py splitting (B) | HIGH | `_P` at line 105 confirmed, `import normalize` at line 16 confirmed, `import db` in all callers confirmed |
| Pre-computed risk scores (C) | HIGH | No `risk_score_computed_at` visible, no invalidation triggers in ingest functions, AIS listener buffer pattern confirmed |
| Retroactive testing (D) | HIGH | Threshold constants at module level confirmed in `dark_periods.py` and `loitering.py`, auto-start pattern at `app.py` lines 37-39 confirmed |

---

*Pitfalls audit: 2026-03-03*
