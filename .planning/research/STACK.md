# Technology Stack — Additions Research

**Project:** maritime-osint (maturity pass milestone)
**Researched:** 2026-03-03
**Scope:** Four targeted additions to the existing Flask + PostgreSQL stack. The base stack (Python 3.11, Flask 3.1, PostgreSQL, Railway, Gunicorn) is fixed — this document covers only what needs to be added.

---

## Area 1: Pre-Computed Risk Scores

### Recommendation: PostgreSQL Materialized View + APScheduler Refresh

**Approach:** Add a `vessel_risk_scores` materialized view that stores pre-computed composite risk scores per vessel, refreshed on a schedule (every 15–30 minutes) via APScheduler running inside the existing Gunicorn process.

### Why Not Triggers

PostgreSQL triggers fire synchronously on every INSERT/UPDATE in `ais_positions` and detection result tables. At AIS stream ingestion rates (50-position batches, continuous), this means risk score recomputation happens thousands of times per hour. The score formula pulls from 11+ tables and aggregates with a weighted sum. A trigger that re-runs this cross-table aggregation on every AIS insert turns a bulk-write operation into a serial bottleneck.

**Verdict on triggers:** Do not use. Wrong granularity for a multi-source aggregation score.

### Why Not a Dedicated Background Worker Process

Running a separate Celery worker, RQ worker, or dedicated Python process requires a Redis broker, separate Railway service, and operational overhead that does not fit the solo-operator Railway hobby-tier constraint. All detection results are already persisted to the database — there is no job to queue, only a periodic refresh.

**Verdict on dedicated workers:** Overcomplicated for this use case.

### Why Materialized View + APScheduler

PostgreSQL materialized views store the result of a query physically on disk. `REFRESH MATERIALIZED VIEW CONCURRENTLY vessel_risk_scores` recomputes from the already-persisted detection result tables without touching the hot write path. Reads against the view are instant (indexed table scan). APScheduler provides in-process scheduling within the existing Gunicorn process — zero new services, zero new dependencies beyond the library itself.

**Concurrency note:** `CONCURRENTLY` requires a unique index on the view. Use `UNIQUE INDEX ON vessel_risk_scores (mmsi)`. This allows refreshes to run without locking reads.

### Libraries

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| APScheduler | `>=3.10.0,<4.0.0` | In-process scheduled refresh | Runs inside Gunicorn, no broker, no extra services. Version 3.x has stable API; 4.x is a major rewrite — stay on 3.x. |

**What NOT to use:**
- Celery — requires Redis broker, separate worker process, overbuilt for a single periodic task
- `threading.Timer` — no visibility, no persistence across restarts, no error handling
- PostgreSQL `pg_cron` extension — not available on Railway's managed PostgreSQL

### Schema Pattern

```sql
CREATE MATERIALIZED VIEW vessel_risk_scores AS
SELECT
    vc.mmsi,
    vc.canonical_id,
    vc.entity_name,
    LEAST(
        COALESCE(dp.score, 0) + COALESCE(sts.score, 0) + COALESCE(loi.score, 0)
        + COALESCE(spoof.score, 0) + COALESCE(ports.score, 0) + COALESCE(flag.score, 0)
        + COALESCE(age.score, 0) + COALESCE(psc.score, 0),
        99
    ) AS composite_risk_score,
    NOW() AS computed_at
FROM vessels_canonical vc
LEFT JOIN (...) dp ON dp.mmsi = vc.mmsi
-- other indicator subqueries
WITH DATA;

CREATE UNIQUE INDEX ON vessel_risk_scores (mmsi);
```

### Refresh Pattern

```python
from apscheduler.schedulers.background import BackgroundScheduler

def refresh_risk_scores():
    with db._conn() as conn:
        conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY vessel_risk_scores")

scheduler = BackgroundScheduler()
scheduler.add_job(refresh_risk_scores, "interval", minutes=15)
scheduler.start()
```

Initialize in `app.py` startup, after `db.init_db()`. Guard with `if os.getenv("DATABASE_URL")` so it does not run against SQLite in local dev.

Risk score history: append to a `risk_score_history` table on each refresh — one row per (mmsi, computed_at, composite_risk_score). INSERT SELECT from the view after each refresh. Enables trend visualization at negligible cost.

**Confidence:** HIGH — PostgreSQL materialized views with CONCURRENTLY refresh are an officially documented pattern. APScheduler 3.x is production-stable.

---

## Area 2: Python Module Decomposition (db.py Monolith)

### Recommendation: Vertical Slice by Responsibility Into a db/ Package

Split the 2,835-line `db.py` into six focused modules under a `db/` package:

| Module | Contents | Approx Lines |
|--------|----------|-------------|
| `db/connection.py` | Connection pool, `_conn()` context manager, `_ph()` / `_ilike()` helpers, backend detection | ~150 |
| `db/schema.py` | `init_db()`, all `CREATE TABLE` / `CREATE INDEX` DDL, migrations | ~400 |
| `db/ingest.py` | `upsert_sanctions()`, `upsert_ais_positions()`, `upsert_ais_vessel_static()`, ingest log | ~600 |
| `db/detection.py` | `insert_dark_period()`, `insert_sts_transfer()`, `insert_loitering()`, `insert_spoofing()`, `insert_port_call()`, detection result queries | ~700 |
| `db/screening.py` | `get_vessel_by_canonical_id()`, `search_vessels()`, `get_vessel_ownership()`, `get_sanctions_memberships()`, `get_batch_vessel_ownership()` | ~500 |
| `db/reconcile.py` | `merge_canonical()`, `rebuild_source_tags()`, reconciliation utilities | ~300 |

A thin `db/__init__.py` re-exports the entire public API so all existing callers (`screening.py`, `ingest.py`, detection modules) continue using `import db` and `db.upsert_sanctions()` without modification.

### Why Vertical Slices, Not Horizontal Layers

Vertical slices (by data flow stage) keep related logic co-located. `ingest.py` only touches `db.ingest`, detection modules only touch `db.detection`. A horizontal split (e.g., "all SELECTs in one file, all INSERTs in another") would mix unrelated concerns and force readers to navigate two files to understand one operation.

### No New Libraries Required

Pure refactoring. The existing `sqlite3`, `psycopg2-binary`, and `threading.local` usage moves unchanged. The `__init__.py` re-export pattern ensures zero caller-site changes.

### Migration Pattern

1. Create `db/` package with `__init__.py`
2. Move functions starting with `connection.py` (leaf node, no internal db dependencies)
3. Update `__init__.py` to re-export after each file migration
4. Verify caller imports still work at each step
5. Delete original `db.py` when all functions are migrated and verified

**Confidence:** HIGH — standard Python package decomposition, no external dependencies.

---

## Area 3: Flask Security Hardening

### 3a. Rate Limiting — Flask-Limiter

**Recommendation:** `Flask-Limiter 3.x` with PostgreSQL storage backend.

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| Flask-Limiter | `>=3.5.0,<4.0.0` | Per-endpoint rate limiting | Native Flask integration, supports multiple storage backends, actively maintained. |

**Storage backend:** Use `storage_uri` pointing to the Railway `DATABASE_URL`. Flask-Limiter stores rate-limit counters in a `limits` table in PostgreSQL. No Redis required.

**What NOT to use:**
- In-memory storage (default) — broken with Gunicorn multi-worker: each worker has an independent counter, so limits are divided by worker count
- Redis — adds a new Railway service for a problem already solvable with existing PostgreSQL

**Usage pattern:**

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    storage_uri=os.environ["DATABASE_URL"],
    default_limits=[]
)

@app.post("/login")
@limiter.limit("5 per minute")
def login():
    ...
```

Apply only to `/login` POST. Do not apply a blanket limit to API endpoints — the dashboard's polling would trigger it.

**Confidence:** MEDIUM — Flask-Limiter 3.x with PostgreSQL storage is documented. The connection URI format accepted by the `limits` PostgreSQL backend should be verified against the Railway `DATABASE_URL` format during implementation.

### 3b. CSRF Protection — Flask-WTF

**Recommendation:** `Flask-WTF 1.x`.

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| Flask-WTF | `>=1.2.0,<2.0.0` | CSRF protection | Standard Flask CSRF extension; handles token generation, rotation, expiry; compatible with Flask 3.x. |

**Scope:** Apply to `/login` POST and `/logout` POST. Exempt `/api/*` JSON endpoints — modern browsers enforce SameSite=Lax by default and do not send cross-origin requests with session cookies for JSON content type.

```python
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)
# In login.html: <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

@csrf.exempt
@app.post("/api/screen")
def screen_post():
    ...
```

**What NOT to use:**
- Flask-SeaSurf — less actively maintained than Flask-WTF
- Rolling HMAC token manually — error-prone; Flask-WTF handles rotation and expiry correctly

**Confidence:** HIGH — Flask-WTF is the canonical Flask CSRF library, compatible with Flask 3.x.

### 3c. Security Headers — flask-talisman

**Recommendation:** `flask-talisman 1.x`.

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| flask-talisman | `>=1.1.0,<2.0.0` | HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy | Single-call setup; sensible defaults; actively maintained. |

**Critical configuration for Railway:**

```python
from flask_talisman import Talisman

csp = {
    "default-src": "'self'",
    "script-src": ["'self'", "https://unpkg.com", "https://cdnjs.cloudflare.com"],
    "style-src": ["'self'", "https://unpkg.com", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "https://*.tile.openstreetmap.org"],
    "connect-src": ["'self'"],
}

Talisman(app, content_security_policy=csp, force_https=False)
```

Set `force_https=False` — Railway terminates TLS at the load balancer and passes HTTP to Gunicorn. Setting `force_https=True` causes redirect loops.

The `'unsafe-inline'` in `style-src` is a temporary placeholder until inline styles in dashboard templates are moved to `static/`. Remove it once templates are clean.

**Confidence:** HIGH — flask-talisman is the standard Flask security headers library. The `force_https=False` requirement for Railway is a known configuration for Railway-deployed Flask apps.

### Security Installation

```bash
pip install "Flask-Limiter>=3.5.0,<4.0.0" "Flask-WTF>=1.2.0,<2.0.0" "flask-talisman>=1.1.0,<2.0.0"
```

---

## Area 4: Test Coverage for Detection Logic

### Recommendation: pytest + pytest-mock + in-memory SQLite fixtures

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| pytest | `>=8.0.0,<9.0.0` | Test runner | Universal Python test runner; parametrize, fixture scoping, markers. 8.x is current stable. |
| pytest-mock | `>=3.12.0,<4.0.0` | `mocker` fixture | Wraps `unittest.mock`; cleaner syntax inside pytest fixtures. |
| pytest-cov | `>=5.0.0,<6.0.0` | Coverage reporting | `--cov` flag; HTML and text reports; integrates directly with pytest. |

**What NOT to use:**
- `pytest-asyncio` — not needed for the detection modules targeted (dark_periods, sts_detection, loitering, spoofing). Defer async test infrastructure until `ais_listener.py` refactoring is in scope.
- `factory_boy` — overkill; plain Python fixture functions in `conftest.py` are sufficient for the fixture volume here.
- `hypothesis` — valid for Haversine boundary properties but introduces friction; start with explicit parametrize cases.

### Detection Logic Test Strategy

The four detection modules follow a consistent pattern: query `ais_positions`, run an algorithm, return a result list. Tests should:

1. **Inject known AIS sequences via in-memory SQLite**, not mocked functions. This tests the full algorithm including the SQL query layer.
2. **Parametrize at threshold boundaries** — gap exactly at 2h for dark periods, distance exactly at STS detection radius.
3. **Leverage the existing dual-backend as an asset** — the SQLite path in `db.py` makes in-process test databases trivial with no Docker or network required.

**conftest.py pattern:**

```python
import pytest
import sqlite3
from db.schema import init_db

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()
```

**Detection unit test pattern:**

```python
from datetime import datetime, timezone, timedelta
import pytest
from dark_periods import run_detection

@pytest.mark.parametrize("gap_hours,expect_detection", [
    (1.9, False),   # Below 2h threshold
    (2.0, True),    # Exactly at threshold
    (12.0, True),   # Well above threshold
])
def test_dark_period_gap_threshold(db_conn, gap_hours, expect_detection):
    mmsi = "123456789"
    base_ts = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    db_conn.execute(
        "INSERT INTO ais_positions (mmsi, lat, lon, sog, position_ts) VALUES (?, ?, ?, ?, ?)",
        (mmsi, 25.0, 55.0, 12.0, base_ts.isoformat())
    )
    db_conn.execute(
        "INSERT INTO ais_positions (mmsi, lat, lon, sog, position_ts) VALUES (?, ?, ?, ?, ?)",
        (mmsi, 25.1, 55.1, 12.0, (base_ts + timedelta(hours=gap_hours)).isoformat())
    )
    db_conn.commit()

    results = run_detection(mmsi, db_conn=db_conn)
    assert (len(results) >= 1) == expect_detection
```

**Note:** This pattern requires detection functions to accept an optional `db_conn` parameter for test injection. If the current `run_detection()` signatures do not support this, a thin adapter or dependency injection pattern is needed during the test coverage phase.

### Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| `dark_periods.py` | 80% | Haversine + risk zone classification must be covered |
| `sts_detection.py` | 80% | Proximity math must be unit-tested |
| `loitering.py` | 75% | Simpler logic; focus on time-window edge cases |
| `spoofing.py` | 75% | SOG threshold logic is straightforward |
| `screening.py` | 70% | IMO/MMSI/name match branches; confidence label logic |
| `db/` modules | 60% | Integration-tested via detection tests |

### Test Installation

```bash
pip install -D "pytest>=8.0.0,<9.0.0" "pytest-mock>=3.12.0,<4.0.0" "pytest-cov>=5.0.0,<6.0.0"
```

---

## Consolidated Dependencies

**requirements.txt additions:**
```
Flask-Limiter>=3.5.0,<4.0.0
Flask-WTF>=1.2.0,<2.0.0
flask-talisman>=1.1.0,<2.0.0
APScheduler>=3.10.0,<4.0.0
```

**Dev / test dependencies (requirements-dev.txt or pyproject.toml extras):**
```
pytest>=8.0.0,<9.0.0
pytest-mock>=3.12.0,<4.0.0
pytest-cov>=5.0.0,<6.0.0
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Risk score scheduling | APScheduler 3.x in-process | Celery + Redis | Requires broker service; overbuilt for one periodic task |
| Risk score mechanism | Materialized view + scheduled refresh | PostgreSQL triggers | Trigger on every AIS insert runs 11-table aggregation; write-path bottleneck |
| Risk score mechanism | Materialized view + scheduled refresh | Compute on-demand (status quo) | Every dashboard load runs 11+ aggregation queries; doesn't scale |
| Rate limit storage | PostgreSQL (existing) | Redis | Adds new Railway service and cost |
| Rate limiting library | Flask-Limiter 3.x | Manual `@before_request` counter | Error-prone; lacks sliding window; no per-route config |
| CSRF library | Flask-WTF 1.x | Flask-SeaSurf | Flask-SeaSurf is less actively maintained |
| Security headers | flask-talisman 1.x | Manual `after_request` hooks | Verbose; skips edge cases on redirect and error responses |
| Test runner | pytest 8.x | unittest (stdlib) | pytest has better parametrize, fixture scoping, and plugin ecosystem |
| Test mocking | pytest-mock | unittest.mock directly | pytest-mock wraps unittest.mock; same capability, cleaner fixture syntax |

---

## Interaction Notes

**APScheduler + Gunicorn workers:** With 2 Gunicorn workers, both will start APScheduler instances, causing double-refresh. The `CONCURRENTLY` refresh is idempotent so this is harmless, but wasteful. Resolution: either reduce to 1 worker on the Railway hobby tier, or use a PostgreSQL advisory lock inside `refresh_risk_scores()` to skip if another worker is already refreshing.

**Flask-WTF + Flask-Limiter:** Both use `app.secret_key`. Ensure `SECRET_KEY` is loaded from the environment before initializing either extension.

**flask-talisman in development:** Disable or relax CSP in `app.debug` mode to avoid breaking template iteration with strict CSP violations.

---

*Research: 2026-03-03. Confidence: HIGH for all library selections except Flask-Limiter PostgreSQL storage URI format (MEDIUM — verify driver compatibility with Railway DATABASE_URL format during implementation).*
