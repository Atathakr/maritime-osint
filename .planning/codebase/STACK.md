# Technology Stack

**Analysis Date:** 2026-03-03

## Languages

**Primary:**
- Python 3.11+ - Core application language for all backend services
  - Specified in `pyproject.toml` line 5: `requires-python = ">=3.11"`
  - Used in: `app.py`, `db.py`, `ingest.py`, `ais_listener.py`, all analysis modules

**Secondary:**
- HTML/CSS/JavaScript - Web UI templates in `templates/` directory (Jinja2 templates)

## Runtime

**Environment:**
- Python 3.11 (via Nixpacks builder on Railway)
- Specified in `pyproject.toml` line 19: `target-version = "py311"`

**Package Manager:**
- pip (via `requirements.txt`)
- Lockfile: `requirements.txt` (version-pinned dependencies)

## Frameworks

**Core:**
- Flask 3.1.0+ - Web application framework
  - Used in: `app.py` (lines 9, 29-30)
  - Provides: request routing, session management, template rendering
  - Entry point: `app = Flask(__name__)`

**Async/Concurrency:**
- asyncio - Built into Python standard library
  - Used in: `ais_listener.py` (line 15)
  - For WebSocket client connections

- websockets 12.0+ - WebSocket protocol implementation
  - Used in: `ais_listener.py` (lazy-imported at line 123)
  - Connects to `wss://stream.aisstream.io/v0/stream`

**Testing:**
- Ruff - Linter and formatter (ruff)
  - Config: `pyproject.toml` lines 17-55
  - Runs via: `pytest` (inherited from base Python environment)

**Build/Dev:**
- Gunicorn 22.0.0+ - WSGI HTTP server
  - Used in: `Procfile` line 1
  - Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
  - Deployed on Railway

- Nixpacks - Container builder (Railway)
  - Config: `railway.toml` line 2: `builder = "nixpacks"`
  - Automatic Python 3.11 detection and build

## Key Dependencies

**Critical:**
- requests 2.28.0+ - HTTP client library
  - Used for fetching OFAC SDN XML, OpenSanctions JSON, NOAA AIS datasets
  - Imports: `ingest.py` (line 18), `noaa_ingest.py` (line 33)

- anthropic 0.40.0+ - Anthropic Claude API client
  - Used for optional AI analysis features (future capability)
  - Configured via: `ANTHROPIC_API_KEY` env var
  - Usage: Imported but not yet integrated in core flows

- python-dotenv 1.0.0+ - Environment variable loader
  - Used in: `app.py` (line 8)
  - Loads `.env` file at runtime

- Pydantic - Data validation framework
  - Used in: `schemas.py` (lines 4-11)
  - Provides: `BaseModel`, field validation, serialization
  - Models: `AisPosition`, `AisVesselStatic`, `SanctionsListEntry`, etc.

**Infrastructure:**
- psycopg2-binary 2.9.0+ - PostgreSQL database driver
  - Lazy-imported in: `db.py` (lines 48-50, 89)
  - Used only when `DATABASE_URL` starts with `postgresql://`
  - Connection pooling: `ThreadedConnectionPool` (1-10 connections)

- sqlite3 - SQLite database driver (Python stdlib)
  - Used in: `db.py` (line 13)
  - Default backend when `DATABASE_URL` is not set

- lxml 5.0.0+ - XML parsing library
  - Used for: OFAC SDN XML parsing (namespaced XML)
  - Alternative to ElementTree: `xml.etree.ElementTree` (stdlib, also used)
  - Used in: `ingest.py` (line 7)

## Configuration

**Environment:**
- `.env` file (not committed, local development only)
  - Template: `.env.example` (lines 1-23)
  - Required vars (empty on startup):
    - `APP_PASSWORD` - Shared password for web UI (early access gate)
    - `SECRET_KEY` - Flask session signing key
    - `DATABASE_URL` - PostgreSQL connection string (set by Railway)
    - `AISSTREAM_API_KEY` - AIS Stream WebSocket API key
    - `ANTHROPIC_API_KEY` - Anthropic Claude API key (optional)

**Build:**
- `pyproject.toml` - Project metadata and tool config
  - Ruff linter settings (lines 17-55)
  - Linting ignores: docstrings, type annotations, SQL injection checks
  - Max complexity: 20 (line 54)

- `railway.toml` - Railway deployment config
  - Nixpacks builder (line 2)
  - Health check: `/health` endpoint, 30s timeout
  - Restart policy: on failure, max 5 retries

- `Procfile` - Process definition for gunicorn
  - 2 workers, 120s timeout
  - Binds to `0.0.0.0:$PORT` (Railway sets PORT automatically)

## Platform Requirements

**Development:**
- Python 3.11+
- pip package manager
- `.venv` virtual environment (present in repo)

**Production:**
- Railway platform (Nixpacks builder)
- PostgreSQL database plugin (Railway)
- 120s request timeout for ingestion tasks
- WebSocket support (for aisstream.io connection)

---

*Stack analysis: 2026-03-03*
