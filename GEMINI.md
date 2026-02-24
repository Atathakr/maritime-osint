# GEMINI.md - Maritime OSINT Platform Context

This document provides instructional context and technical overview for the Maritime OSINT Platform.

## Project Overview

The Maritime OSINT Platform is a specialized tool for tracking sanctioned vessels and detecting suspicious maritime behavior. It aggregates data from multiple sanctions lists (OFAC SDN, OpenSanctions, EU, UN, etc.) and cross-references it with live and historical AIS (Automatic Identification System) data.

### Main Technologies
- **Backend:** Python 3.13, Flask
- **Database:** Dual-backend support (SQLite for local dev, PostgreSQL for production) via `db.py`.
- **AIS Data:** 
    - Real-time: WebSocket connection to `aisstream.io` via `ais_listener.py`.
    - Historical: NOAA Marine Cadastre CSV ingestion via `noaa_ingest.py`.
- **Sanctions Data:** 
    - OFAC SDN (XML) and OpenSanctions (JSON API/Streaming) via `ingest.py`.
- **Frontend:** Leaflet 1.9.4 for map visualization, Vanilla JS for interactivity.
- **Deployment:** Railway (`railway.toml`, `Procfile`).

## Architecture & Core Logic

### 1. Canonical Vessel Registry
The project implements a "Canonical Vessel" strategy to handle identity across fragmented data sources.
- **ID Generation:** Uses `normalize.make_canonical_id` with priority: `IMO:{num}` > `MMSI:{num}` > `HASH:{name+flag}`.
- **Reconciliation:** `reconcile.py` performs multi-tier merging to link records (e.g., merging an MMSI-only record into an IMO-keyed record when an overlap is found).

### 2. Behavioral Analytics
- **Vessel Track History (`db.py` / `app.py`):** Provides a 72-hour breadcrumb trail for any vessel with historical AIS data. Accessed via `GET /api/ais/vessels/<mmsi>/track`.
- **Dark Periods (`dark_periods.py`):** Detects gaps in AIS reporting that exceed a specified duration (default 2h), calculating distance and risk level based on location.
- **STS Detection (`sts_detection.py`):** Ship-to-Ship proximity detection. Identifies vessels within close range (< 1km) at low speeds.

### 3. Screening (`screening.py`)
Provides unified lookup for vessels by IMO, MMSI, or Name. It returns a "match confidence" and aggregates risk factors across all linked sanctions memberships.

## Building and Running

### Prerequisites
- Python 3.13
- `.env` file with:
  ```env
  DATABASE_URL=...
  APP_PASSWORD=...
  AISSTREAM_API_KEY=...
  SECRET_KEY=...
  ```

### Commands
- **Setup:**
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # or .venv\Scripts\activate on Windows
  pip install -r requirements.txt
  ```
- **Run Application:**
  ```bash
  python app.py
  ```
- **Tests:** (TODO: Add test suite)

### Initialization Flow
1. Start the app.
2. Trigger Sanctions Ingest: `POST /api/ingest/ofac` and `POST /api/ingest/opensanctions`.
3. Run Reconciliation: `POST /api/reconcile`.
4. Start AIS Listener: `POST /api/ais/start`.

## Development Conventions

- **Database Abstraction:** All DB calls should go through `db.py`. Use the provided `_conn()` and `_cursor()` context managers to ensure compatibility with both SQLite and Postgres.
- **Normalization:** Use `normalize.py` for country codes, dataset labels, and ID generation to maintain consistency.
- **API Response:** Prefer returning `jsonify` from Flask routes. Most internal logic uses dictionaries that represent rows.
- **Auth:** Use the `@login_required` decorator for all API and Page routes.
- **Concurrency:** Real-time AIS listening runs in a background thread managed by `ais_listener.py`.

## Key Files
- `app.py`: Flask application and route definitions.
- `db.py`: Database schema and cross-backend query layer.
- `ingest.py`: Sanctions list fetching logic.
- `reconcile.py`: Cross-list entity resolution.
- `screening.py`: Core sanctions search engine.
- `ais_listener.py`: WebSocket client for live tracking.
- `dark_periods.py` & `sts_detection.py`: Analytical modules.
- `map_data.py`: Prepares geo-spatial data for the Leaflet frontend.
