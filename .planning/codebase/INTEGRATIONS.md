# External Integrations

**Analysis Date:** 2026-03-03

## APIs & External Services

**Sanctions Data:**
- OFAC SDN (U.S. Treasury) - Specially Designated Nationals list
  - SDK/Client: HTTP requests library
  - URL: `https://www.treasury.gov/ofac/downloads/sdn.xml`
  - Auth: None required (public XML feed)
  - Parsing: `ingest.py` function `fetch_ofac_sdn()` (lines 63-174)
  - Namespace: `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML`
  - Data cached in: `sanctioned_vessels` table

- OpenSanctions - Consolidated sanctions dataset
  - SDK/Client: HTTP requests library
  - URL: `https://data.opensanctions.org/datasets/latest/sanctions/entities.ftm.json`
  - Auth: None required (public bulk download)
  - Parsing: `ingest.py` function `stream_opensanctions()` (lines 194-291)
  - Format: Streaming FtM JSON Lines (one JSON object per line)
  - Data cached in: `sanctioned_vessels` table

**AIS Live Tracking:**
- aisstream.io - Real-time vessel Automatic Identification System (AIS) data
  - SDK/Client: Python websockets library (lazy-imported)
  - Protocol: WebSocket (wss://)
  - Endpoint: `wss://stream.aisstream.io/v0/stream`
  - Auth: API key via `AISSTREAM_API_KEY` environment variable
  - Signup: `https://aisstream.io` (free tier available)
  - Implementation: `ais_listener.py` (async WebSocket listener, lines 73-283)
  - Start condition: Auto-started in `app.py` if API key is configured (lines 38-39)
  - Filter: Tanker vessel types only (AIS codes 80-89)
  - Buffering: Batch inserts (BUFFER_SIZE=50) to reduce database write load

**AIS Historical Data:**
- NOAA Marine Cadastre - Bulk AIS historical datasets
  - SDK/Client: HTTP requests library with streaming
  - URL pattern: `https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/AIS_{year}_{month:02d}_Zone{zone:02d}.zip`
  - Auth: None required (public NOAA data)
  - Data: Monthly zipped CSV files per zone (17 US coastal zones)
  - Implementation: `noaa_ingest.py` function `fetch_and_ingest()` (lines 52-160)
  - Recommended start: Zone 10 (Gulf of Mexico, known shadow fleet transit corridor)
  - File sizes: 200 MB - 1 GB zipped
  - Ingest method: Streaming decompression, batch insert (BATCH_SIZE=500)

**Port/Detention Lists:**
- Paris MOU - Port State Control detention list
  - URL: `https://www.parismou.org/sites/default/files/Paris%20MOU%20Detention%20List.csv`
  - Format: CSV
  - Auth: None required
  - Reference in: `ingest.py` line 304

- Tokyo MOU - Asian port detention list
  - URL: `https://www.tokyo-mou.org/doc/DetentionList.csv`
  - Format: CSV
  - Auth: None required
  - Reference in: `ingest.py` line 308

**AI/Analysis (Future):**
- Anthropic Claude API - AI-powered threat analysis
  - SDK/Client: `anthropic` Python package (0.40.0+)
  - Auth: `ANTHROPIC_API_KEY` environment variable
  - Status: Imported but not yet integrated in core analysis flows
  - Configuration: `app.py` line 10

## Data Storage

**Databases:**
- PostgreSQL (Production)
  - Connection: `DATABASE_URL` environment variable (set by Railway)
  - Client: `psycopg2-binary` library with `ThreadedConnectionPool`
  - Pool size: 1-10 connections (lazy-initialized)
  - Cursor type: `RealDictCursor` for dict-like row access
  - Backend detection: Auto-selected when `DATABASE_URL` starts with `postgresql://` or `postgres://`

- SQLite (Development/Local)
  - Connection: Default backend when `DATABASE_URL` not set or starts with `sqlite:///`
  - File: `maritime_osint.db` (220 MB on disk)
  - Settings: WAL mode + foreign key constraints enabled
  - Dual-backend abstraction: `db.py` lines 18-31 (auto-detection)
  - Used by all functions via `_conn()` context manager

**Schema:**
- Tables managed by `db.init_db()` function
- Key tables:
  - `sanctioned_vessels` - OFAC and OpenSanctions entries with reconciliation
  - `ais_positions` - Live and historical position reports
  - `ais_vessel_static` - Static vessel information (name, IMO, type)
  - `ingest_logs` - Audit trail of import operations

**File Storage:**
- Local filesystem only
  - SQLite database file in project root
  - No external file storage (S3, etc.)

**Caching:**
- None - Direct database queries
- In-memory buffers only: AIS WebSocket position buffer (50 records)

## Authentication & Identity

**Auth Provider:**
- Custom session-based (built-in Flask)
  - Implementation: `app.py` lines 42-79
  - Password: `APP_PASSWORD` environment variable (shared password for early access)
  - Session storage: Flask default (signed cookies with `SECRET_KEY`)
  - Session key: `FLASK_ENV` auto-generated if not set

**Requirement:**
- Optional: App password gate can be disabled by leaving `APP_PASSWORD` empty
- Open paths (no auth required): `/login`, `/static/`, `/health`

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service
- Logs: Python standard `logging` module

**Logs:**
- Approach: Python `logging` module (built-in)
- Loggers: Each module has `logger = logging.getLogger(__name__)`
- Used in: `ais_listener.py`, `ingest.py`, `noaa_ingest.py`, `db.py`
- Output: Sent to stdout (captured by Railway logs)

**Health Check:**
- Endpoint: `GET /health` (public, no auth)
- Implementation: `app.py` lines 84-86
- Response: `{"status": "ok"}`
- Used by: Railway deployment (healthcheckPath in `railway.toml` line 5)

## CI/CD & Deployment

**Hosting:**
- Railway platform (`https://railway.app`)
- Automatic deployment on git push to main branch

**Build Process:**
- Nixpacks builder (auto-detects Python 3.11)
- Installs dependencies from `requirements.txt`
- Runs: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

**Deployment Config:**
- File: `railway.toml`
  - Health check: `/health` endpoint, 30s timeout
  - Restart policy: on_failure, max 5 retries
- Environment: Railway PostgreSQL plugin automatically sets `DATABASE_URL`

**CI Pipeline:**
- None configured (no GitHub Actions, no pre-push hooks)

## Environment Configuration

**Required env vars (empty on startup):**
- `APP_PASSWORD` - Web UI password (leave empty to disable auth)
- `SECRET_KEY` - Flask session key (auto-generated if empty)
- `DATABASE_URL` - PostgreSQL connection (set by Railway plugin)
- `AISSTREAM_API_KEY` - Live AIS WebSocket API key (leave empty to disable live feed)
- `ANTHROPIC_API_KEY` - Claude API key (optional, for future AI features)

**Auto-set by Railway:**
- `PORT` - HTTP listen port (app binds to 0.0.0.0:$PORT)
- `FLASK_ENV` - Deployment environment (production on Railway)

**Secrets location:**
- `.env` file (local development only, not committed)
- Railway dashboard: Project → Settings → Variables (production secrets)

**Generation:**
- `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
- `AISSTREAM_API_KEY`: Register at `https://aisstream.io` for free tier API key

## Webhooks & Callbacks

**Incoming:**
- None - Application is pull-based (fetches data from external APIs)

**Outgoing:**
- None - Application only reads from external data sources

---

*Integration audit: 2026-03-03*
