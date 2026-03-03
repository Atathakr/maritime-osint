# Architecture

**Analysis Date:** 2026-03-03

## Pattern Overview

**Overall:** Modular pipeline with layered responsibilities — Flask-based API server orchestrating a multi-stage data ingestion and risk-scoring engine.

**Key Characteristics:**
- **Dual-backend persistence:** SQLite (local) / PostgreSQL (production via Railway)
- **Plugin-style detection modules:** Each behavioral indicator (dark periods, STS, loitering, etc.) is a standalone function returning scored results
- **Composite risk scoring:** 13 indicators feed into a weighted formula producing 0–99 risk scores (100 for sanctioned vessels)
- **Two-tier reconciliation:** Canonical vessel deduplication using IMO > MMSI hierarchy to merge cross-source sanctions hits
- **Real-time + historical AIS:** WebSocket listener (aisstream.io) for live tanker positions + CSV ingest (NOAA Marine Cadastre) for historical data

---

## Layers

**Presentation (Web UI):**
- Purpose: Analyst-facing dashboard for vessel screening and risk visualization
- Location: `templates/dashboard.html`, `static/app.js`, `static/map.js`
- Contains: Flask template with interactive search, risk profile cards, Leaflet map component
- Depends on: REST API endpoints in `app.py`
- Used by: End users querying vessels and viewing behavioral analytics

**API / Route Handler:**
- Purpose: HTTP request routing, authentication, request validation, JSON response marshaling
- Location: `app.py` (routes for `/api/screen`, `/api/ingest/*`, `/api/ais/*`, `/api/*/detect`)
- Contains: Flask route definitions with `@app.get`/`@app.post` decorators, login/logout, auth middleware
- Depends on: Core logic modules (`screening`, `ingest`, `db`), Pydantic schemas for validation
- Used by: Frontend JavaScript, external API consumers

**Screening & Risk Scoring:**
- Purpose: Search sanctions lists by IMO/MMSI/name and compute composite risk scores
- Location: `screening.py`
- Contains: Search functions (`search_by_imo`, `search_by_mmsi`, `search_by_name`), ownership-chain checker, risk calculator
- Depends on: `db` (sanctions queries), `risk_config` (scoring weights), `dark_periods`, `sts_detection`, `loitering`, `spoofing`, `ports` (detection results)
- Used by: API handlers, risk profile generation

**Data Ingestion & Reconciliation:**
- Purpose: Download and parse external data sources; merge duplicate vessel records
- Location: `ingest.py` (OFAC SDN XML, OpenSanctions JSON), `noaa_ingest.py` (CSV), `reconcile.py` (two-tier dedup)
- Contains: Fetch + parse logic for each source, CSV readers, canonical record merge logic
- Depends on: `db` (upsert operations), `normalize` (flag/name standardization), `requests` (HTTP fetching)
- Used by: API `/api/ingest/*` endpoints, on-demand via browser

**Behavioral Detection Modules (Plugin Pattern):**
- Purpose: Identify individual shadow fleet indicators — AIS gaps, STS proximity, speed anomalies, loitering, sanctioned port calls, flag hopping
- Locations:
  - `dark_periods.py` (IND1 — ≥2 hour AIS transponder gaps)
  - `sts_detection.py` (IND7/8 — ship-to-ship transfers in/out of high-risk zones)
  - `loitering.py` (IND9 — open-water anchoring/loitering)
  - `spoofing.py` (IND10 — speed anomalies, SOG > 50 kt)
  - `ports.py` (IND29 — port calls to sanctioned/high-risk terminals)
  - Additional computed in `screening.py`: flag hopping (IND15), name discrepancy (IND16), flag risk tier (IND17), ownership chain (IND21), vessel age (IND23), PSC detentions (IND31)
- Contains: Detection logic (gap analysis, geospatial proximity, time-series patterns), risk level classification, result persistence
- Depends on: `db` (AIS positions, vessel metadata), `risk_config` (thresholds), `schemas` (result models)
- Used by: `screening.py` (score aggregation), API detection endpoints

**Real-Time AIS Stream Processor:**
- Purpose: Consume WebSocket stream from aisstream.io, buffer positions, persist to database
- Location: `ais_listener.py`
- Contains: Async WebSocket client, position/static data normalization, buffered writes, connection state management
- Depends on: `db` (batch inserts), `schemas` (AIS data validation)
- Used by: Daemon thread started by `app.py` on startup if `AISSTREAM_API_KEY` is set

**Persistence Layer (Backend-Agnostic):**
- Purpose: Unified database interface for SQLite / PostgreSQL; shields upper layers from backend differences
- Location: `db.py`
- Contains: Connection pooling, transaction management, SQL abstraction helpers (`_ph()` for placeholders, `_ilike()` for case-insensitive search), schema initialization, CRUD for sanctions entries, AIS positions, canonical vessels, ownership chains
- Depends on: `sqlite3` (local), `psycopg2` (production), `normalize` (data standardization)
- Used by: All upper layers (screening, ingest, detection, map data)

**Data Models & Validation:**
- Purpose: Enforce structure on external API responses and internal data
- Location: `schemas.py`
- Contains: Pydantic BaseModels for `AisPosition`, `AisVesselStatic`, `SanctionsEntry`, `OwnershipEntry`, risk response models
- Depends on: `pydantic` (validation framework)
- Used by: API request/response validation, AIS listener normalization, ingest parsers

**Configuration & Normalization:**
- Purpose: Risk scoring parameters, flag tier registry, data value normalization
- Locations:
  - `risk_config.py` — Indicator thresholds, scoring weights, flag risk tiers, PSC detention multipliers
  - `normalize.py` — Flag code standardization, name cleaning, canonical ID generation
- Contains: Lookup tables, thresholds, utility functions for data cleaning
- Depends on: None (configuration only)
- Used by: All detection modules, screening, ingest, db

---

## Data Flow

**Ingest Pipeline (One-time or on-demand):**

1. User clicks "Fetch OFAC" → `POST /api/ingest/ofac` → `ingest.fetch_ofac_sdn()` downloads OFAC XML
2. Parse OFAC entries → extract IMO/MMSI/name → `db.upsert_sanctions()` inserts into `sanctions_entries` table, auto-keyed by "IMO:{imo}" or "MMSI:{mmsi}" canonical ID
3. User clicks "Fetch OpenSanctions" → `POST /api/ingest/opensanctions` → `ingest.fetch_opensanctions()` streams JSON
4. Parse OpenSanctions → same upsert logic → merges OFAC/OpenSanctions entries sharing IMO into single canonical record
5. Optional: ingest PSC CSV (Paris MOU / Tokyo MOU detentions) → `POST /api/ingest/psc/<source>`
6. User clicks "Reconcile" → `POST /api/reconcile` → `reconcile.run_reconciliation()`
   - Tier 1: IMO safety sweep (guard against duplicate IMO canonicals)
   - Tier 2: MMSI→IMO merge (if MMSI-keyed canonical shares MMSI with IMO-keyed, merge into IMO)
   - Rebuild `source_tags` denormalization (list of sanctions list labels per canonical)

**Real-Time AIS Stream (Background):**

1. `ais_listener.start(api_key)` spawns daemon thread
2. WebSocket loop connects to aisstream.io, filters for tanker vessel types (AIS codes 80–89)
3. Each position report → `schemas.AisPosition` validation → buffered in `_buffer` list (BUFFER_SIZE=50)
4. When buffer full → `db.insert_ais_positions()` → `ais_positions` table (time-series)
5. Static data (vessel name, IMO) → `db.upsert_ais_vessel_static()` → `ais_vessel_static` table
6. Thread runs until `stop()` called or error; stats exposed via `get_stats()` → `/api/ais/status`

**Historical AIS Ingest (CSV):**

1. User or scheduled task → `POST /api/ingest/noaa` → `noaa_ingest.parse_and_insert_csv()`
2. Reads NOAA CSV format → batches inserts into `ais_positions` (same table as real-time)
3. Supports configurable history window (72 h default, up to 168 h)

**Vessel Screening (Query-time):**

1. User enters IMO/MMSI/name in dashboard → JavaScript `POST /api/screen` with query string
2. `app.screen_post()` → `screening.search_sanctions(query)`
3. Query type detection: regex `\d{7}` → "imo", `\d{9}` → "mmsi", else → "name"
4. If name query, fuzzy name search against `vessels_canonical.entity_name` with confidence labels
5. Return list of `ScreeningHit` objects with:
   - canonical vessel metadata (IMO, MMSI, flag, vessel type)
   - `source_tags` — list of sanctions list labels
   - `match_confidence` — "HIGH — exact IMO match" | "MEDIUM — name match (verify IMO)"
6. API response includes sanctions memberships (full lineage per source)

**Risk Profile (Deep Dive):**

1. User clicks vessel in screening results → `GET /api/screen/<imo>`
2. `app.screen_detail()` → `screening.compute_profile(imo)` returns composite profile:
   - Sanctions status (list memberships, programs, aliases)
   - Behavioral risk score (0–99, or 100 if sanctioned):
     - IND1 dark periods: `dark_periods.run_detection(mmsi)` queries `ais_positions` for gaps ≥2 h
     - IND7/8 STS transfers: `sts_detection.run_detection(mmsi)` detects ship-proximity in open water / high-risk zones
     - IND9 loitering: `loitering.run_detection(mmsi)` flags stationary positions in open water
     - IND10 speed anomalies: `spoofing.run_detection(mmsi)` flags SOG > 50 kt
     - IND29 port calls: `ports.run_detection(mmsi)` checks `ais_positions` against sanctioned terminal geofences
     - IND15 flag hopping: count distinct flag values in `vessels_canonical.past_flags`
     - IND16 name discrepancy: compare canonical `entity_name` vs AIS `ais_vessel_static.vessel_name`
     - IND17 flag risk tier: `risk_config.get_flag_tier(flag_state)` → Tier 0/1/2/3
     - IND21 ownership chain: `screening._check_ownership_chain()` fuzzy-searches ownership entities against sanctions list
     - IND23 vessel age: max(0, (build_year − 15) × 3) capped at 15 pts
     - IND31 PSC detentions: count detentions in last 24 months × 10 pts, capped at 20
   - Aggregate formula: min(sum of all contributions, 99)
3. Response includes individual indicator breakdowns for analyst review

**Map Visualization:**

1. User opens map view → `GET /api/map/vessels` → `map_data.prepare_map_data()`
2. Query `ais_positions` (latest position per MMSI) + join with `vessels_canonical` risk scores
3. GeoJSON with properties: MMSI, vessel name, position, composite risk score (0–100), risk color (green → yellow → red)
4. Frontend (`static/map.js`) renders Leaflet map with vessel markers colored by risk

---

## State Management

**Stateless API:**
- All request handling is stateless; state lives in the database
- Flask session (optional) holds only authentication flag; no screening state persists across requests

**Background Thread State:**
- `ais_listener._stats` dict holds connection metrics (messages received, positions inserted, errors)
- `ais_listener._buffer` holds position batch awaiting flush to DB
- `ais_listener._stop_event` coordinates graceful shutdown

**Database Transactions:**
- Implicit per-request: `_conn()` context manager auto-commits on clean exit, rolls back on exception
- No multi-request transactions; each API call is atomic
- Critical consistency: canonical → memberships foreign key ensures orphaned memberships cannot occur

---

## Key Abstractions

**Canonical Vessel Record:**
- Purpose: Single source-of-truth identity for a vessel across sanctions lists
- Examples: `vessels_canonical` table rows like `canonical_id="IMO:1234567"` or `canonical_id="MMSI:123456789"`
- Pattern: IMO > MMSI > name+flag hash for key selection; Tier 2 reconciliation merges MMSI-keyed into IMO-keyed
- Fields: `canonical_id`, `entity_name`, `imo_number`, `mmsi`, `vessel_type`, `flag_state`, `source_tags` (JSON list), `match_method`, `build_year`, `call_sign`, `gross_tonnage`

**Sanctions Membership:**
- Purpose: Link a canonical vessel to a specific sanctions list entry
- Example: Canonical `IMO:1234567` may have memberships in OFAC SDN, EU, UN SC simultaneously
- Pattern: `sanctions_memberships` table with foreign key to `vessels_canonical`, per-source fields (list_name, source_id, programs, aliases)
- Enables lineage: query `sanctons_memberships WHERE canonical_id=...` to see all sources claiming this vessel is sanctioned

**Detection Result:**
- Purpose: Timestamped record of a single behavioral indicator for a vessel
- Examples: A dark period (gap_start, gap_end, duration_hours, risk_level, risk_zone)
- Pattern: Persisted in module-specific tables (`dark_periods`, `sts_transfers`, `loitering_reports`, etc.)
- Fields: MMSI, timestamp range, computed risk level, supporting details (zone, distance, confidence)

**AIS Position Time-Series:**
- Purpose: Breadcrumb trail of vessel movements for behavioral analysis
- Structure: `ais_positions` (MMSI, lat, lon, SOG, COG, heading, vessel_name, position_ts)
- Storage: Configurable history window; used for dark period detection, STS proximity, loitering
- Indexing: Critical for performance — indices on (MMSI, position_ts) for time-window queries

---

## Entry Points

**Web Server:**
- Location: `app.py` line 29 `app = Flask(__name__)`
- Triggers: `python app.py` (Flask development server) or Gunicorn in production (`Procfile: gunicorn app:app --bind 0.0.0.0:$PORT`)
- Responsibilities:
  - Initialize Flask, load .env, call `db.init_db()`
  - Auto-start AIS listener if `AISSTREAM_API_KEY` set (line 38–39)
  - Register routes for `/login`, `/logout`, `/health`, dashboard, API endpoints
  - Enforce authentication middleware if `APP_PASSWORD` set

**Data Ingest Endpoints:**
- `/api/ingest/ofac` (POST) — `ingest.fetch_ofac_sdn()` + `db.upsert_sanctions()`
- `/api/ingest/opensanctions` (POST) — `ingest.fetch_opensanctions()` + streaming insert
- `/api/ingest/psc/<paris|tokyo>` (POST) — `noaa_ingest.parse_psc_csv()` + insert

**Reconciliation Endpoint:**
- `/api/reconcile` (POST) — `reconcile.run_reconciliation()` — triggers Tier 1 + Tier 2 merges

**Real-Time AIS Control:**
- `/api/ais/start` (POST) — `ais_listener.start(api_key)` — spawns WebSocket consumer thread
- `/api/ais/status` (GET) — returns `ais_listener.get_stats()` — connection health, message rates

**Detection Trigger Endpoints:**
- `/api/dark-periods/detect` (POST) — `dark_periods.run_detection()`
- `/api/sts/detect` (POST) — `sts_detection.run_detection()`
- `/api/ais/detect-loitering` (POST) — `loitering.run_detection()`
- `/api/ais/detect-anomalies` (POST) — `spoofing.run_detection()`
- `/api/ports/detect-calls` (POST) — `ports.run_detection()`

**Screening Endpoints:**
- `POST /api/screen` — query sanctions by IMO/MMSI/name
- `GET /api/screen/<imo>` — full risk profile for a vessel

---

## Error Handling

**Strategy:** Graceful degradation; recoverable errors logged and returned as HTTP errors. Critical errors (DB failures) halt request processing.

**Patterns:**

**Validation Errors (HTTP 400):**
```python
# In app.py routes:
try:
    req = schemas.ScreenRequest.model_validate(request.json)
except ValidationError as e:
    return jsonify({"error": "Invalid request", "details": e.errors()}), 400
```

**Resource Not Found (HTTP 404):**
```python
# Example from screening.py:
hit = db.get_vessel_by_canonical_id(canonical_id)
if not hit:
    return {"error": f"Vessel {canonical_id} not found"}, 404
```

**Database Connection Failure (HTTP 500):**
```python
# In db.py _conn() context manager:
except Exception:
    conn.rollback()
    raise  # Propagates; Flask catches and returns 500
```

**External API Failure (Retry + Log):**
```python
# In ingest.py:
try:
    resp = requests.get(OFAC_SDN_URL, timeout=90)
    resp.raise_for_status()
except requests.RequestException as e:
    logger.error(f"Failed to fetch OFAC: {e}")
    return {"error": "External data source unavailable"}, 503
```

**Detection Module Robustness:**
- All detection functions (`dark_periods.run_detection()`, etc.) validate inputs and return empty result lists on missing data
- Example: If a vessel has no AIS positions, dark period detection returns `[]` (no gaps found) rather than raising

---

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` module with `__name__`-based loggers per module
- Usage: `logger.info()` for operational milestones (ingest progress, reconciliation), `logger.error()` for failures
- Output: Gunicorn captures to Railway logs in production; local console in development

**Validation:**
- **Request/Response:** Pydantic models in `schemas.py` — all external API boundaries use typed BaseModels
- **Data Ingestion:** Regex extraction for IMO (7 digits), MMSI (9 digits), flag normalization in `normalize.py`
- **Database:** Foreign key constraints enforced at persistence layer; type conversions in `_rows()` / `_row()`

**Authentication:**
- Mechanism: Optional password-based session (if `APP_PASSWORD` set)
- Middleware: `app.before_request` checks `session.get("authenticated")` and redirects to `/login` unless on open paths
- Login form: `POST /login` sets `session["authenticated"] = True`; logout clears session

---

*Architecture analysis: 2026-03-03*
