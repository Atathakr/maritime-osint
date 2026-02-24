# Architecture

**Analysis Date:** 2025-02-14

## Pattern Overview

**Overall:** Monolithic Python/Flask application with background processing.

**Key Characteristics:**
- **Dual-Backend Support:** Abstracted database layer supporting both SQLite (dev) and PostgreSQL (prod).
- **Canonical Identity Registry:** Merges disparate vessel data into a unified identity model using a `vessels_canonical` pattern.
- **Background Ingestion:** Real-time data streaming via WebSocket (AIS) and periodic batch ingestion (Sanctions).

## Layers

**Web/Presentation Layer:**
- Purpose: Provides the user interface and REST API.
- Location: `app.py`, `templates/`, `static/`
- Contains: Flask routes, HTML templates, and client-side JavaScript for map visualization and dashboards.
- Depends on: Logic and Database layers.
- Used by: End users.

**Logic Layer:**
- Purpose: Implements business rules, risk scoring, and behavioral detection algorithms.
- Location: `screening.py`, `reconcile.py`, `sts_detection.py`, `dark_periods.py`, `normalize.py`
- Contains: Vessel screening logic, record merging (reconciliation), and behavioral analysis (AIS gaps, STS proximity).
- Depends on: Database layer, Schemas.
- Used by: Web layer, Ingestion processes.

**Data Ingestion Layer:**
- Purpose: Fetches and parses data from external sources.
- Location: `ingest.py`, `ais_listener.py`, `noaa_ingest.py`
- Contains: HTTP clients (requests), WebSocket clients (websockets), and parsers (XML/JSON).
- Depends on: Database layer, Schemas.
- Used by: Background threads and manual triggers.

**Data Access Layer:**
- Purpose: Provides a backend-agnostic interface for database operations.
- Location: `db.py`
- Contains: Connection pooling, SQL query execution, and schema management.
- Depends on: `normalize.py` (for ID generation).
- Used by: All other Python modules requiring persistent storage.

## Data Flow

**Sanctions Ingestion & Reconciliation:**

1. `ingest.py` fetches data from OFAC/OpenSanctions.
2. Data is normalized and inserted into `vessels_canonical` and `sanctions_memberships` via `db.py`.
3. `reconcile.py` runs Tier 1 (IMO) and Tier 2 (MMSI) merges to link records across sources.
4. Canonical records are updated with merged metadata and source tags.

**Real-time AIS Processing:**

1. `ais_listener.py` receives position and static data via WebSocket from `aisstream.io`.
2. Positions are buffered and batch-inserted into `ais_positions` via `db.py`.
3. Static vessel data is upserted into `ais_vessels` to maintain current state.
4. (Implicitly) Analysis modules scan `ais_positions` to detect gaps or rendezvous.

## Key Abstractions

**Canonical Vessel (`vessels_canonical`):**
- Purpose: Represents a unique vessel identity regardless of how many sanctions lists it appears on.
- Examples: Managed in `db.py`, generated via `normalize.make_canonical_id`.
- Pattern: Identity Map / Record Linkage.

**Match Method:**
- Purpose: Records the strength and type of link between a source entry and a canonical identity.
- Examples: `imo_exact`, `mmsi_exact`, `single_source`.
- Pattern: Strategy/Metadata.

## Entry Points

**Web Application:**
- Location: `app.py`
- Triggers: HTTP requests.
- Responsibilities: Routing, session management, authentication, and serving API responses.

**AIS Background Listener:**
- Location: `ais_listener.py`
- Triggers: Started by `app.py` as a daemon thread.
- Responsibilities: Maintaining WebSocket connection, filtering tanker data, and buffering database writes.

## Error Handling

**Strategy:** Fail-soft with logging.

**Patterns:**
- **Retry Logic:** Reconnection loops in `ais_listener.py` with exponential backoff/fixed delays.
- **Validation:** Pydantic models in `schemas.py` for input/output validation.
- **Database Transactions:** `@contextmanager` in `db.py` ensures atomicity and clean connection release.

## Cross-Cutting Concerns

**Logging:** Standard Python `logging` used across modules to track ingestion status and detection events.
**Validation:** Pydantic models in `schemas.py` define the shape of core entities (Vessel, Position, Event).
**Authentication:** Simple session-based password authentication in `app.py` via a `login_required` decorator.

---

*Architecture analysis: 2025-02-14*
