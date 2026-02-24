# Codebase Structure

**Analysis Date:** 2025-02-14

## Directory Layout

```
maritime-osint/
├── ais_listener.py     # Background AIS WebSocket client
├── app.py              # Main Flask web application entry point
├── dark_periods.py     # AIS gap detection logic
├── db.py               # Database abstraction (SQLite/Postgres)
├── ingest.py           # Sanctions list ingestion (OFAC/OpenSanctions)
├── map_data.py         # GIS data preparation for map display
├── noaa_ingest.py      # NOAA weather/environmental data ingestion
├── normalize.py        # ID generation and field normalization
├── pyproject.toml      # Build system dependencies
├── requirements.txt    # Python dependencies
├── reconcile.py        # Cross-list record merging logic
├── schemas.py          # Pydantic data models
├── screening.py        # Vessel sanctions screening logic
├── sts_detection.py    # Ship-to-ship transfer detection
├── static/             # Frontend assets (JS, CSS)
│   ├── app.js          # General dashboard JS
│   ├── map.js          # Leaflet map logic
│   └── style.css       # UI styling
├── templates/          # Jinja2 HTML templates
│   ├── dashboard.html  # Main application UI
│   └── login.html      # Authentication UI
└── maritime_osint.db   # Default SQLite database (local dev)
```

## Directory Purposes

**Root Directory:**
- Purpose: Contains the core application logic, data processing modules, and entry points.
- Contains: Python scripts, configuration files, and project manifests.
- Key files: `app.py`, `db.py`, `schemas.py`.

**static/:**
- Purpose: Hosts client-side assets served by the web application.
- Contains: CSS for styling and JavaScript for interactivity and map rendering.
- Key files: `static/map.js`, `static/app.js`.

**templates/:**
- Purpose: Contains HTML templates for the Flask application.
- Contains: Jinja2 templates defining the structure of web pages.
- Key files: `templates/dashboard.html`.

## Key File Locations

**Entry Points:**
- `app.py`: The primary web server and entry point for the application.
- `ais_listener.py`: The entry point for the background data streaming thread.

**Configuration:**
- `pyproject.toml`: Modern Python build configuration.
- `requirements.txt`: List of required Python packages.
- `.env.example`: Template for environment variables.

**Core Logic:**
- `db.py`: The data access layer for all database interactions.
- `schemas.py`: Central definition of data models and validation rules.
- `reconcile.py`: Logic for maintaining data integrity across sources.

**Testing:**
- Not detected (No dedicated `tests/` directory or `*.test.py` files found in root).

## Naming Conventions

**Files:**
- Snake Case: `ais_listener.py`, `dark_periods.py`, `sts_detection.py`.

**Directories:**
- Short, descriptive names: `static`, `templates`.

## Where to Add New Code

**New Risk Detection Algorithm:**
- Primary code: Create a new module in the root (e.g., `loitering_detection.py`).
- Integration: Add detection trigger to `app.py` or a background task, and update `db.py` with necessary tables.

**New Frontend Feature:**
- Implementation: Update `templates/dashboard.html` and add logic to `static/app.js` or `static/map.js`.

**New Data Source:**
- Ingestion logic: Add a new function in `ingest.py` or a new standalone `[source]_ingest.py`.
- Normalization: Update `normalize.py` to handle source-specific formatting.

## Special Directories

**__pycache__:**
- Purpose: Contains compiled Python bytecode.
- Generated: Yes
- Committed: No (ignored via `.gitignore`)

**.venv:**
- Purpose: Local Python virtual environment.
- Generated: Yes
- Committed: No

---

*Structure analysis: 2025-02-14*
