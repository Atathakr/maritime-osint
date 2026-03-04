# Architecture Patterns

**Domain:** Flask + PostgreSQL maritime threat intelligence platform — maturity pass
**Researched:** 2026-03-03
**Research mode:** Ecosystem (four specific architectural concerns)
**Confidence note:** External search tools unavailable. All findings from training data (cutoff August 2025) cross-validated against existing codebase context. Confidence levels reflect this.

---

## Recommended Architecture

The existing architecture is a sound layered pipeline. This maturity pass adds four structural improvements without breaking the layer model:

```
┌─────────────────────────────────────────────────┐
│  Presentation (dashboard.html, app.js, map.js)  │
└────────────────────┬────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────┐
│  Security Layer (NEW)                           │
│  flask-limiter (rate limiting on /login)        │
│  flask-wtf CSRFProtect (state-changing routes)  │
│  flask-talisman (security headers)              │
│  Sits in app.py init, before route handlers     │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  API / Route Handler (app.py)                   │
└────────────┬───────────────────┬────────────────┘
             │                   │
┌────────────▼──────┐   ┌────────▼───────────────┐
│ Screening &       │   │ Detection Modules       │
│ Risk Scoring      │   │ dark_periods.py         │
│ (screening.py)    │   │ sts_detection.py        │
│ Reads pre-        │   │ loitering.py            │
│ computed scores   │   │ spoofing.py / ports.py  │
└────────────┬──────┘   └────────┬───────────────┘
             │                   │
┌────────────▼───────────────────▼───────────────┐
│  Persistence Layer (db/ package — REFACTORED)   │
│  db/__init__.py  ← public API, re-exports all   │
│  db/connection.py ← pool, _conn(), backends     │
│  db/schema.py    ← init_db(), CREATE TABLE      │
│  db/vessels.py / sanctions.py / ais.py          │
│  db/detection.py / scores.py (NEW)              │
└────────────────────────────────────────────────┘
             │
┌────────────▼───────────────────────────────────┐
│  Background Score Refresh (NEW)                 │
│  APScheduler BackgroundScheduler                │
│  Runs every 15 min: recompute + upsert scores   │
└────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `app.py` routes | HTTP routing, auth, request validation, JSON marshaling | Security layer (wraps), `screening.py`, `db/`, detection modules |
| Security layer | Rate limiting, CSRF, security headers — applied at app creation | Wraps `app` object; transparent to route handlers |
| `screening.py` | Vessel search, risk profile assembly; reads pre-computed score from `vessel_scores` | `db/` (read), `risk_config.py`, detection modules (on-demand fallback only) |
| Detection modules (5 files) | Each owns one behavioral indicator; runs detection, persists results | `db/ais.py` (read positions), `db/detection.py` (write results), `risk_config.py` |
| `db/` package | Unified persistence interface; hides SQLite vs PostgreSQL | `psycopg2` / `sqlite3`; called by all upper layers |
| `db/scores.py` | Pre-computed composite score table — upsert and read | Written by APScheduler job; read by `screening.py` and map endpoint |
| APScheduler job | Periodically recomputes all vessel scores in batch | `db/` (read + write), `screening.py` score computation logic |
| `ais_listener.py` | WebSocket consumer; buffers + persists live AIS positions | `db/ais.py` (write), `schemas.py` (validation) |
| `schemas.py` | Pydantic models at all external boundaries | `app.py`, `ais_listener.py`, `ingest.py`; no DB access |
| `risk_config.py` / `normalize.py` | Configuration and pure utilities — no I/O | Read-only; used by all modules |

---

## Data Flow

### Pre-Computed Score Write Path (NEW)

```
APScheduler fires (every 15 min)
  → fetch all vessel MMSIs from db/vessels.py
  → for each vessel: call detection modules → aggregate score
  → upsert into vessel_scores (mmsi, composite_score, computed_at, indicator_breakdown JSONB)
  → insert into vessel_score_history (append-only; delete rows >90 days old)
```

### Score Read Path (CHANGED from on-demand to cached)

```
GET /api/screen/<imo>
  → screening.compute_profile(imo)
  → db/scores.get_vessel_score(mmsi)     ← single indexed read, <5ms
  → if score missing or stale (>30 min): compute on demand, upsert score
  → return profile with cached score + indicator_breakdown JSON
```

### Module Decomposition Flow (callers unchanged)

```
Before: import db; db.get_vessel_by_imo(imo)
After:  import db; db.get_vessel_by_imo(imo)   ← identical

Internal:
  db/__init__.py re-exports get_vessel_by_imo from db/vessels.py
  No caller changes required anywhere in codebase
```

### Security Layer Data Flow

```
Incoming HTTP request
  → flask-talisman: adds security headers to response (HSTS, CSP, X-Frame-Options)
  → flask-limiter: checks rate limit bucket
      POST /login → 10/minute; 429 if exceeded
  → flask-wtf: validates CSRF token on HTML form POSTs (login only)
  → before_request auth check (existing)
  → route handler
```

---

## Patterns to Follow

### Pattern 1: Pre-Computed Scores with APScheduler

**What:** A `vessel_scores` table stores composite risk scores computed by a background job. Dashboard reads from this table instead of running all detection modules per request.

**Why APScheduler over alternatives:**

| Option | Assessment |
|--------|-----------|
| `APScheduler BackgroundScheduler` | Best fit — pure Python, no extra services, railway hobby tier |
| Celery + Redis | Overkill — requires separate Redis service; justified only at >1K vessels or sub-minute freshness |
| PostgreSQL materialized view | Cannot call Python detection logic (STS proximity, speed anomaly); only viable for pure-SQL aggregations |
| PostgreSQL triggers | Same constraint — cannot run Python; only valid for pure-SQL derived fields |
| GENERATED ALWAYS columns | PostgreSQL supports only deterministic SQL expressions; composite multi-indicator scoring is ineligible |

**Confidence:** MEDIUM — APScheduler is well-established (v3 stable, v4 released 2024); verify import path for whichever version is installed.

**Recommended table:**

```sql
CREATE TABLE vessel_scores (
    mmsi            TEXT PRIMARY KEY,
    composite_score INTEGER NOT NULL DEFAULT 0,
    is_sanctioned   BOOLEAN NOT NULL DEFAULT FALSE,
    indicator_json  JSONB,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_vessel_scores_score ON vessel_scores (composite_score DESC);

-- History table (append-only)
CREATE TABLE vessel_score_history (
    id              BIGSERIAL PRIMARY KEY,
    mmsi            TEXT NOT NULL,
    composite_score INTEGER NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_vsh_mmsi_time ON vessel_score_history (mmsi, computed_at DESC);
```

**APScheduler registration in app.py:**

```python
from apscheduler.schedulers.background import BackgroundScheduler

def refresh_all_scores():
    from screening import compute_all_scores  # avoid circular import at module level
    compute_all_scores()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(refresh_all_scores, 'interval', minutes=15,
                  id='score_refresh', replace_existing=True)
# Also: archive old positions and history rows
scheduler.add_job(db.archive_old_positions, 'interval', hours=24,
                  id='ais_archive', replace_existing=True)
scheduler.start()
```

**Staleness fallback in screening.py:**

```python
SCORE_MAX_AGE_SECONDS = 1800  # 30 minutes

def get_score_with_fallback(mmsi: str) -> dict:
    score_row = db.get_vessel_score(mmsi)
    if score_row:
        age = (datetime.now(timezone.utc) - score_row["computed_at"]).total_seconds()
        if age < SCORE_MAX_AGE_SECONDS:
            return score_row
    score = compute_score_for_vessel(mmsi)
    db.upsert_vessel_score(mmsi, score)
    return score
```

---

### Pattern 2: db.py Decomposition via Package with Re-Exports

**What:** Convert `db.py` (2,835 lines) into a `db/` package. The `db/__init__.py` re-exports every public function. All existing callers work without modification.

**Confidence:** HIGH — standard Python package pattern; well-documented.

**Why package + re-exports over alternatives:**

| Option | Assessment |
|--------|-----------|
| `db/` package with `__init__.py` re-exports | **Recommended.** Zero caller changes. Safe incremental migration. |
| Flat files (`db_vessels.py`, `db_sanctions.py`) | Requires updating 10+ `import db` call sites — high migration risk |
| Facade class | Adds object instantiation, mixes state and interface, less idiomatic for utility modules |
| Comment-separated sections in one file | No isolation — functions still share namespace, no independent testability |

**Target structure:**

```
db/
├── __init__.py       # Re-exports all public functions — only file callers see
├── connection.py     # _init_backend(), _conn(), _ph(), _ilike(), pool management
├── schema.py         # init_db(), CREATE TABLE statements for all tables
├── vessels.py        # vessels_canonical CRUD
├── sanctions.py      # sanctions_entries, sanctions_memberships CRUD
├── ais.py            # ais_positions, ais_vessel_static CRUD
├── detection.py      # detection result CRUD (dark_periods, sts_transfers, etc.)
└── scores.py         # vessel_scores, vessel_score_history CRUD (NEW)
```

**__init__.py pattern:**

```python
# db/__init__.py — public API; callers import from here only
from .connection import _conn, _ph, _ilike, init_db              # noqa: F401
from .vessels import (                                             # noqa: F401
    get_vessel_by_imo, upsert_canonical,
    list_all_vessels, get_vessel_by_canonical_id,
)
from .sanctions import (                                           # noqa: F401
    upsert_sanctions, get_sanctions_memberships,
)
from .ais import (                                                 # noqa: F401
    insert_ais_positions, upsert_ais_vessel_static,
    get_positions_for_mmsi, get_latest_positions_all,
    archive_old_positions,
)
from .detection import insert_detection_results, get_dark_periods  # noqa: F401
from .scores import get_vessel_score, upsert_vessel_score          # noqa: F401
```

**Migration sequence (each step independently deployable):**

1. Create `db/` directory, copy `db.py` content verbatim into `db/connection.py`; write thin `__init__.py` that imports everything from `connection.py` — all tests pass
2. Extract `schema.py` (CREATE TABLE) — run tests
3. Extract `vessels.py` — update `__init__.py` re-exports — run tests
4. Extract `sanctions.py` — run tests
5. Extract `ais.py` — run tests
6. Extract `detection.py` — run tests
7. Add new `scores.py` — run tests
8. Delete original `db.py`

**Cross-module dependency rule:** Sub-modules may only import from `connection.py`. No sub-module imports another sub-module. All coordination at `__init__.py` or caller level.

---

### Pattern 3: Flask Security Hardening — Three Libraries, One Init Block

**What:** Rate limiting, CSRF, and security headers applied at app-creation time using three libraries. Not per-route decorators. No Blueprint restructuring required.

**Confidence:** HIGH — flask-limiter, flask-wtf, flask-talisman are all stable, well-maintained libraries in the standard Flask security ecosystem.

**Recommended libraries:**

| Concern | Library | Why |
|---------|---------|-----|
| Rate limiting | `flask-limiter` | Standard; supports in-memory (Railway hobby) or Redis; per-route + global |
| CSRF | `flask-wtf` `CSRFProtect` | Standard Flask CSRF extension; supports explicit route exemption |
| Security headers | `flask-talisman` | One-liner wrapper; sets HSTS, CSP, X-Frame-Options, X-Content-Type-Options |

**New file: `security.py`**

```python
# security.py (NEW)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import flask_talisman

limiter = Limiter(key_func=get_remote_address, default_limits=[])
csrf = CSRFProtect()

def init_security(app):
    """Attach all security middleware to the Flask app."""
    limiter.init_app(app)

    csrf.init_app(app)
    # Exempt JSON API routes — CSRF not needed for same-origin JSON APIs
    for api_route in [
        "/api/ingest/ofac", "/api/ingest/opensanctions",
        "/api/reconcile", "/api/ais/start",
        "/api/dark-periods/detect", "/api/sts/detect",
        "/api/ais/detect-loitering", "/api/ais/detect-anomalies",
        "/api/ports/detect-calls", "/api/screen",
    ]:
        csrf.exempt(api_route)

    csp = {
        "default-src": "'self'",
        "script-src": ["'self'", "https://unpkg.com"],       # Leaflet CDN
        "style-src": ["'self'", "https://unpkg.com", "'unsafe-inline'"],
        "img-src": ["'self'", "data:", "https://*.tile.openstreetmap.org"],
        "connect-src": "'self'",
    }
    flask_talisman.Talisman(
        app,
        force_https=False,              # Railway terminates TLS at edge proxy
        strict_transport_security=True,
        content_security_policy=csp,
        frame_options="DENY",
        content_type_options=True,
        referrer_policy="strict-origin-when-cross-origin",
    )
```

**app.py initialization block:**

```python
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]  # enforced — KeyError if missing

from security import init_security, limiter
init_security(app)

@app.post("/login")
@limiter.limit("10 per minute")
def login():
    ...
```

**HSTS + Railway:** `force_https=False` because Railway's edge proxy handles TLS termination. The `strict_transport_security=True` header is still sent and forwarded to the browser by the proxy — correct Railway configuration.

**CSP + Leaflet:** Existing map uses Leaflet from unpkg.com CDN. The CSP must whitelist `unpkg.com` for `script-src`/`style-src` and `*.tile.openstreetmap.org` for `img-src`.

---

### Pattern 4: Detection Algorithm Testing with Synthetic Fixtures

**What:** Pytest fixtures that generate synthetic AIS position sequences targeting each algorithm's boundary conditions. No database required for unit tests.

**Confidence:** HIGH — standard pytest fixture pattern; pure-function extraction is standard Python refactoring.

**Enabling pure-function testing:** Extract the algorithm to a pure function that accepts positions directly:

```python
# dark_periods.py — extract pattern (apply to all 5 detectors)

def detect(positions: list[dict]) -> list[dict]:
    """Pure function. Testable without database."""
    if len(positions) < 2:
        return []
    gaps = []
    sorted_pos = sorted(positions, key=lambda p: p["position_ts"])
    for i in range(1, len(sorted_pos)):
        gap_hours = _compute_gap(sorted_pos[i-1], sorted_pos[i])
        if gap_hours >= DARK_PERIOD_THRESHOLD_HOURS:
            gaps.append(_build_gap_record(sorted_pos[i-1], sorted_pos[i], gap_hours))
    return gaps

def run_detection(mmsi: str | None = None) -> list[dict]:
    """Production entry point. Fetches positions from DB, calls detect()."""
    positions = db.get_positions_for_mmsi(mmsi)
    results = detect(positions)
    if results:
        db.insert_detection_results("dark_periods", results)
    return results
```

**Fixture factory (`tests/fixtures/ais_factory.py`):**

```python
from datetime import datetime, timedelta, timezone

def make_positions(mmsi, start, interval_minutes, count, lat=20.0, lon=60.0, sog=8.0):
    return [
        {
            "mmsi": mmsi,
            "lat": lat + i * 0.01,
            "lon": lon + i * 0.01,
            "sog": sog,
            "position_ts": (start + timedelta(minutes=interval_minutes * i)).isoformat(),
        }
        for i in range(count)
    ]

def make_gap_positions(mmsi, start, gap_after_index, gap_hours, count):
    before = make_positions(mmsi, start, 10, gap_after_index + 1)
    gap_end = start + timedelta(minutes=10 * gap_after_index) + timedelta(hours=gap_hours)
    after = make_positions(mmsi, gap_end, 10, count - gap_after_index - 1)
    return before + after
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Materialized Views for Score Computation

Composite risk score requires Python logic — haversine for STS, ownership-chain fuzzy matching, configurable thresholds from `risk_config.py`. None are expressible as SQL. Use APScheduler + plain `vessel_scores` table instead.

### Anti-Pattern 2: Flat Import Reorganization for db.py

Renaming `db.py` to multiple files and updating every `import db` call site is a large, risky refactor with no isolation. Use package + re-exports — callers never change.

### Anti-Pattern 3: Scattered Per-Route Security Decorators

Security policy becomes scattered and inconsistent; new routes added later may omit decorators. Use `init_security(app)` at app-creation time.

### Anti-Pattern 4: Testing Detection Functions Against a Live Database

Slow, fragile, conflates algorithm correctness with DB infrastructure. Test the pure `detect(positions)` function with synthetic fixtures instead.

### Anti-Pattern 5: CSRF on JSON API Endpoints

JSON API endpoints are protected by CORS. CSRF tokens on JSON endpoints add friction for zero security benefit. Apply CSRF only to `/login`.

---

## Suggested Build Order

```
Phase 1: db/ decomposition (no behavior change)
    ↓
Phase 2: pre-computed scores    Phase 3: detection tests (parallel)
    ↓                                ↓
Phase 4: security hardening
```

| Phase | Why This Order |
|-------|---------------|
| 1: db/ decomposition | Cleans foundation; zero behavior change; all subsequent phases benefit |
| 2: pre-computed scores | Depends on clean `db/` for new `db/scores.py`; unblocks dashboard performance |
| 3: detection tests | Independent of Phase 2; tests provide safety net for Phase 4 |
| 4: security hardening | Requires stable API surface (Phase 1) and regression safety net (Phase 3) |

---

## Phase-Specific Architecture Notes

| Phase | Key Decision | Rationale |
|-------|-------------|-----------|
| Phase 1 | Re-export everything from `__init__.py` before deleting old `db.py` | Zero caller changes |
| Phase 1 | Keep `_ph()` and `_ilike()` in `connection.py` only | Dual-backend abstraction must not be duplicated |
| Phase 2 | Score staleness threshold: 30 minutes | Balances freshness against Railway hobby CPU |
| Phase 2 | Store `indicator_breakdown` as JSONB | Avoids joining 10 indicator tables for dashboard display |
| Phase 3 | Extract `detect(positions)` as pure function alongside `run_detection()` | Non-breaking; enables unit testing without DB |
| Phase 4 | `force_https=False` in flask-talisman | Railway TLS termination at edge |
| Phase 4 | Exempt all `/api/*` from CSRF | JSON API callers cannot submit CSRF tokens |

---

*Architecture research: 2026-03-03. Confidence: HIGH (db decomposition, security libs, pytest patterns), MEDIUM (APScheduler version, Railway TLS behavior — verify with test deploy).*
