# Codebase Structure

**Analysis Date:** 2026-03-03

## Directory Layout

```
maritime-osint/
├── app.py                      # Flask application entry point, route definitions
├── db.py                        # Dual-backend (SQLite/PostgreSQL) persistence layer
├── screening.py                # Vessel search & risk scoring engine
├── ingest.py                   # OFAC SDN + OpenSanctions data ingestion
├── reconcile.py                # Two-tier canonical vessel deduplication
├── schemas.py                  # Pydantic data models for validation
├── risk_config.py              # Scoring weights, flag tier registry, thresholds
├── normalize.py                # Flag normalization, canonical ID generation
│
├── ais_listener.py             # aisstream.io WebSocket consumer (background thread)
├── noaa_ingest.py              # NOAA Marine Cadastre CSV ingest
│
├── dark_periods.py             # IND1 detector — AIS transponder gaps
├── sts_detection.py            # IND7/8 detector — ship-to-ship proximity
├── loitering.py                # IND9 detector — open-water anchoring
├── spoofing.py                 # IND10 detector — speed anomalies
├── ports.py                    # IND29 detector — sanctioned port calls
│
├── map_data.py                 # Geospatial data prep for Leaflet frontend
│
├── templates/
│   ├── dashboard.html          # Main analyst interface (Vue.js + Leaflet)
│   └── login.html              # Authentication form
│
├── static/
│   ├── app.js                  # Frontend logic, API calls, state management
│   ├── map.js                  # Leaflet map initialization & rendering
│   ├── style.css               # Layout & component styles
│   └── css/
│       └── (additional stylesheets)
│
├── docs/                       # Project documentation
├── .github/
│   ├── ISSUE_TEMPLATE/         # GitHub issue templates
│   └── PULL_REQUEST_TEMPLATE/  # PR template
│
├── .planning/                  # GSD-generated analysis documents
│   └── codebase/
│       ├── ARCHITECTURE.md     # (this file location)
│       ├── STRUCTURE.md        # Directory layout & conventions
│       └── (other codebase docs)
│
├── .env                        # Local environment config (secrets — do not commit)
├── .env.example                # Template for .env
├── requirements.txt            # Python dependencies (pip format)
├── pyproject.toml              # Modern Python project metadata
├── Procfile                    # Gunicorn startup command (Railway)
├── runtime.txt                 # Python version (3.11)
├── railway.toml                # Railway platform config
├── .gitignore                  # Git exclusions (.venv, __pycache__, .env, *.db)
│
├── maritime_osint.db           # SQLite database (local development, ~210 MB)
├── maritime_osint.db-shm       # SQLite write-ahead log (temporary)
├── maritime_osint.db-wal       # SQLite write-ahead log (temporary)
│
└── .venv/                      # Python virtual environment (excluded from git)
```

---

## Directory Purposes

**Root (Application Core):**
- Purpose: Python Flask application with modular core logic
- Contains: 16 .py files (app, db layer, screening, ingest, 5 behavioral detectors, AIS listener, map prep, utilities)
- Key pattern: Each detector module is self-contained, returns scored results to `screening.py`

**templates/**
- Purpose: Server-rendered HTML pages + JavaScript app skeleton
- Contains:
  - `dashboard.html` (25 KB) — Main UI with search bar, risk cards, map container, detection panels
  - `login.html` (1.9 KB) — Simple password form
- Rendered by: Flask `render_template()` in `app.py`

**static/**
- Purpose: Client-side assets (JavaScript, CSS)
- Contains:
  - `app.js` (63 KB) — Vue.js reactive UI, API call handlers, state management, form validation
  - `map.js` (11 KB) — Leaflet map initialization, vessel marker rendering, track lines
  - `style.css` (184 bytes) — CSS overrides and layout
  - `css/` subdirectory — Additional stylesheets (Bootstrap, Leaflet CSS imported in HTML)
- Served by: Flask `static/` directory at `/static/` path

**docs/**
- Purpose: Project documentation (development guides, architecture notes, case studies)
- Contains: Markdown files, PDFs (e.g., Shadow Fleet Framework.pdf)
- Not code; for reference only

**.github/**
- Purpose: GitHub-specific templates and workflows
- Contains:
  - `ISSUE_TEMPLATE/` — Issue type templates (bug_report.md, feature_request.md, new_indicator.md)
  - `PULL_REQUEST_TEMPLATE/` — PR description template
- Used by: GitHub PR/issue forms

**.planning/**
- Purpose: GSD (Golden Spiral Deploy) analysis documents
- Contains: Codebase mapping outputs (ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, CONCERNS.md, STACK.md, INTEGRATIONS.md)
- Updated by: GSD `/map-codebase` command

**Root Config Files:**
- `.env` — Environment variables (DATABASE_URL, APP_PASSWORD, SECRET_KEY, AISSTREAM_API_KEY) — **secrets, do not commit**
- `.env.example` — Template showing all variables
- `requirements.txt` — Python dependencies (Flask, requests, psycopg2-binary, pydantic, etc.)
- `pyproject.toml` — Project metadata (name, version, dependencies, build config)
- `Procfile` — Gunicorn command for production deployment
- `runtime.txt` — Python 3.11
- `railway.toml` — Railway.app platform config
- `.gitignore` — Excludes venv, DB files, .env, pycache

**Database Files (local dev):**
- `maritime_osint.db` (210+ MB) — SQLite database with all tables (vessels_canonical, sanctions_entries, sanctions_memberships, ais_positions, ais_vessel_static, etc.)
- `maritime_osint.db-shm`, `maritime_osint.db-wal` — Write-ahead log files (temporary, safe to delete)

---

## Key File Locations

**Entry Points:**

| File | Purpose | Usage |
|------|---------|-------|
| `app.py` | Flask application root, route definitions | `python app.py` (dev) or Gunicorn entry point |
| `templates/dashboard.html` | Main UI template | Rendered by `@app.get("/")` |
| `static/app.js` | Frontend application logic | Loaded in dashboard.html, handles all API calls |

**Database & Persistence:**

| File | Purpose |
|------|---------|
| `db.py` | Connection pooling, SQL abstraction, CRUD for all entities |
| `schemas.py` | Pydantic models for validation & serialization |
| `normalize.py` | Data cleaning (flags, names, ID generation) |

**Data Ingestion Pipeline:**

| File | Purpose |
|------|---------|
| `ingest.py` | OFAC SDN XML fetch/parse, OpenSanctions JSON stream |
| `noaa_ingest.py` | NOAA Marine Cadastre CSV parsing & insertion |
| `reconcile.py` | Tier 1 (IMO sweep) + Tier 2 (MMSI→IMO merge) deduplication |

**Screening & Risk Scoring:**

| File | Purpose |
|------|---------|
| `screening.py` | Vessel search (IMO/MMSI/name), risk profile computation, score aggregation |
| `risk_config.py` | Scoring formula parameters, flag tier registry, thresholds |

**Behavioral Detectors (Plugin Pattern):**

| File | Purpose |
|------|---------|
| `dark_periods.py` | IND1 — AIS transponder gaps ≥2 hours |
| `sts_detection.py` | IND7/8 — ship-to-ship proximity detection |
| `loitering.py` | IND9 — stationary vessel in open water |
| `spoofing.py` | IND10 — speed anomalies (SOG > 50 kt) |
| `ports.py` | IND29 — port calls to sanctioned/high-risk terminals |

**Real-Time AIS:**

| File | Purpose |
|------|---------|
| `ais_listener.py` | WebSocket consumer for aisstream.io live tanker positions |

**Map & Visualization:**

| File | Purpose |
|------|---------|
| `map_data.py` | GeoJSON preparation for Leaflet map (vessels + risk colors) |
| `static/map.js` | Leaflet map rendering, marker clustering, track animation |

---

## Naming Conventions

**Python Files (Modules):**
- Pattern: `snake_case.py`
- Examples: `dark_periods.py`, `sts_detection.py`, `risk_config.py`
- Rationale: Standard Python convention; one detector per file

**Python Functions:**
- Pattern: `snake_case()` for all functions (public and private)
- Private helpers: `_leading_underscore()` convention used in db.py, ingest.py
- Examples: `_clean_imo()`, `_fetch_ofac_sdn()`, `_check_ownership_chain()`

**Python Classes:**
- Pattern: `PascalCase` (Pydantic models in `schemas.py` only)
- Examples: `AisPosition`, `SanctionsEntry`, `OwnershipEntry`, `ScreeningHit`

**Database Tables:**
- Pattern: `snake_case_plural`
- Examples: `vessels_canonical`, `sanctions_entries`, `sanctions_memberships`, `ais_positions`, `ais_vessel_static`, `dark_periods`, `sts_transfers`, `loitering_reports`
- Canonical ID format: `IMO:1234567` or `MMSI:123456789`

**JavaScript Functions (frontend):**
- Pattern: `camelCase()` in `static/app.js`, `static/map.js`
- Examples: `searchVessels()`, `screenByImoCached()`, `updateMapMarkers()`, `displayRiskProfile()`

**Environment Variables:**
- Pattern: `UPPER_SNAKE_CASE`
- Examples: `DATABASE_URL`, `APP_PASSWORD`, `SECRET_KEY`, `AISSTREAM_API_KEY`

**HTML/CSS:**
- Class names: `kebab-case` (BEM-style)
- IDs: `camelCase`
- Examples: `<div class="risk-card" id="profileContainer">`

---

## Where to Add New Code

**New Behavioral Indicator (Detector):**

1. **Create detector module:** `new_indicator.py` in root
   - Pattern: `def run_detection(mmsi: str | None = None) -> list[dict]:`
   - Returns: List of result dicts with fields: `mmsi`, `timestamp`, `risk_level`, `description`
   - Persist to DB: `db.insert_detection_results("new_indicator", results)`
   - Example: Copy structure from `dark_periods.py` (gap detection) or `loitering.py` (geospatial)

2. **Integrate into `screening.py`:**
   - Import: `import new_indicator`
   - In `compute_profile()`: Call `new_indicator.run_detection(mmsi)` and aggregate results
   - Add score contribution to risk formula: `score += min(indicator_count × weight, cap)`
   - Add to indicator breakdown in response

3. **Create API endpoint** (optional) in `app.py`:
   - `@app.post("/api/new-indicator/detect")`
   - Handler: Trigger `new_indicator.run_detection()`, return results

4. **Update `risk_config.py`:**
   - Add threshold constants: `NEW_INDICATOR_THRESHOLD_HOURS = 3.0`
   - Add weight: `NEW_INDICATOR_PTS_PER_HIT = 5`
   - Add cap: `NEW_INDICATOR_CAP = 20`

**New API Endpoint:**

1. **Add route to `app.py`:**
   ```python
   @app.get("/api/resource/<param>")
   @login_required
   def resource_detail(param):
       data = module.fetch_resource(param)
       return jsonify(schemas.ResourceSchema.from_attributes(data))
   ```

2. **Add schema to `schemas.py`:**
   - Pydantic BaseModel with proper validation and serialization

3. **Export/import functions from respective modules** (screening, db, detection)

**New Database Table:**

1. **Add table creation to `db.init_db()`:**
   - In `_init_schema()` function, add CREATE TABLE statement (backend-agnostic SQL)
   - Use `_ph()` placeholder helper for portability

2. **Add CRUD wrapper functions in `db.py`:**
   - `insert_new_resource(data: dict)`
   - `get_new_resource(id: str)`
   - `update_new_resource(id: str, updates: dict)`
   - `delete_new_resource(id: str)`

3. **Add schema model in `schemas.py`:**
   - Pydantic BaseModel for validation

**Frontend Component (Dashboard):**

1. **Add HTML structure** to `templates/dashboard.html`:
   - New `<div class="panel">` or card section
   - Bind to Vue.js data with `v-if`, `v-for`, event handlers

2. **Add JavaScript logic** to `static/app.js`:
   - New computed property or method
   - API call handler (e.g., `fetch('/api/endpoint')`)
   - Data binding to template

3. **Add styling** to `static/style.css` or `static/css/`:
   - BEM-style class names: `.panel-header`, `.panel__title`, `.panel--active`

**New Dependency:**

1. Add to `requirements.txt`:
   ```
   new-package==1.2.3
   ```

2. Update `pyproject.toml` dependencies section:
   ```toml
   dependencies = [
       "flask==3.1.3",
       "new-package==1.2.3",
   ]
   ```

3. Install locally: `pip install -r requirements.txt`

---

## Special Directories

**venv/ (.venv/):**
- Purpose: Python virtual environment (isolated dependencies)
- Generated: Yes (created by `python -m venv .venv`)
- Committed: No — excluded via .gitignore
- Activation: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Unix)

**__pycache__/ (root + per-module):**
- Purpose: Python bytecode cache
- Generated: Yes (auto-created by Python interpreter)
- Committed: No — excluded via .gitignore
- Safe to delete: Yes, will be regenerated on next run

**.git/:**
- Purpose: Git version control metadata
- Generated: Yes (by `git init` or `git clone`)
- Committed: No — is .git directory itself
- Contains: Commit history, branches, hooks, objects

**.env:**
- Purpose: Local environment variables (secrets)
- Generated: Manually (copy from .env.example, edit)
- Committed: No — excluded via .gitignore
- Contains: `DATABASE_URL`, `APP_PASSWORD`, `AISSTREAM_API_KEY`, `SECRET_KEY`
- **WARNING:** Never commit .env with real secrets

**.env.example:**
- Purpose: Template showing required/optional variables
- Generated: No (hand-written)
- Committed: Yes — safe to share
- Used for: Developer onboarding (`cp .env.example .env`)

**maritime_osint.db:**
- Purpose: SQLite database file (local development)
- Generated: Yes (by `db.init_db()` on first run)
- Committed: No — excluded via .gitignore (too large, environment-specific)
- Size: ~210 MB with sample data
- Lifecycle: Persistent between runs; can be deleted to reset (will be recreated)

---

## Import Conventions

**Python Imports Observed:**
```python
# Standard library
import os, sys, csv, json, logging, re
from pathlib import Path
from functools import wraps
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Generator

# Third-party libraries
import requests  # HTTP
import sqlite3   # SQLite
import psycopg2.extras  # PostgreSQL (conditionally imported)
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pydantic import BaseModel, Field, ValidationError, field_serializer, model_validator
from dotenv import load_dotenv

# Local modules
import db
import ingest
import screening
import schemas
import risk_config
import normalize
```

**Patterns:**
- No circular imports observed (clean dependency graph)
- Internal modules imported flat (not from subdirectories)
- Conditional imports: psycopg2 only if `_BACKEND == "postgres"`
- Pydantic used throughout for validation at API boundaries

---

## Configuration & Build

**Local Development:**
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # Edit with local values
python app.py  # Starts Flask dev server at http://localhost:5000
```

**Production (Railway):**
```bash
# Procfile defines entry point:
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120

# Environment:
# - DATABASE_URL (set by Railway PostgreSQL plugin)
# - APP_PASSWORD (set in Railway env vars)
# - AISSTREAM_API_KEY (set in Railway env vars)
```

**Database Selection:**
- `DATABASE_URL` not set or empty → SQLite (`maritime_osint.db`)
- `DATABASE_URL=postgresql://...` → PostgreSQL connection pool (Railway)
- Auto-detected in `db._init_backend()` line 28

---

*Structure analysis: 2026-03-03*
