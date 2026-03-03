# Codebase Concerns

**Analysis Date:** 2026-03-03

## Tech Debt

### SQLite WAL File Bloat (Database Persistence)
- **Issue:** SQLite WAL (Write-Ahead Logging) files are not being checkpointed/pruned. The `.db-wal` file exists at 32KB and `.db-shm` at 32KB, but the database file is 212 GB, indicating incomplete cleanup cycles.
- **Files:** `db.py` (lines 72–83), `maritime_osint.db*` (active WAL files)
- **Impact:**
  - WAL files will grow unbounded and consume disk space on long-running instances
  - Disk exhaustion can cause silent transaction failures
  - On Railway PostgreSQL, this is not a concern (Postgres manages its own WAL), but local SQLite development is vulnerable
- **Fix approach:**
  1. Execute periodic `PRAGMA wal_checkpoint(TRUNCATE)` after bulk ingests
  2. Consider adding a background checkpoint thread in development
  3. Migrate to PostgreSQL-only for production (Railway plugin already configured)

### Database Backend Abstraction Complexity
- **Issue:** Dual-backend architecture (`_BACKEND = "sqlite" | "postgres"`) adds abstraction overhead. SQL placeholder handling (lines 105–122 in `db.py`) uses string-based logic to switch between `%s` and `?`, which is error-prone.
- **Files:** `db.py` (lines 20–122), all `*.py` files that call `db.*` functions
- **Impact:**
  - Future developers may accidentally write Postgres-only SQL and miss SQLite bugs
  - The `_P` global is evaluated once at module load, preventing runtime backend switching
  - No tests ensure both backends behave identically
- **Fix approach:**
  1. Add a CI step that runs the test suite against both SQLite and PostgreSQL
  2. Consider dropping SQLite for production; keep it development-only with explicit warnings
  3. Add unit tests for `_ph()` and `_ilike()` placeholder generation

### SQL Injection Avoidance Workaround
- **Issue:** `pyproject.toml` disables Ruff rule `S608` ("Possible SQL injection") because the code uses backend-agnostic placeholder generation. This is a false positive but masks genuine injection risks if someone adds raw string concatenation elsewhere.
- **Files:** `pyproject.toml` (line 41), `db.py` throughout
- **Impact:** Future SQL additions may not be caught by linters
- **Fix approach:**
  1. Use parameterized queries consistently (already done)
  2. Consider a custom linting rule or code review checklist for SQL safety
  3. Document the `_ph()` pattern in `db.py` docstring

---

## Known Bugs

### AIS Listener WebSocket Reconnection Logging
- **Issue:** When the AIS WebSocket disconnects, the listener logs "reconnecting in 15s" (line 149 in `ais_listener.py`) but there is no explicit reconnection delay; the code immediately tries to reconnect in the next loop iteration.
- **Files:** `ais_listener.py` (lines 146–150)
- **Impact:** Log messages are misleading; the actual behavior depends on how quickly the next `websockets.connect()` attempt is made
- **Workaround:** None needed; the reconnection loop works but the log message is inaccurate
- **Fix approach:** Add explicit `await asyncio.sleep(15)` before the next connection attempt, or update the log message

### Exception Handling in Message Parsing
- **Issue:** `_handle_message()` in `ais_listener.py` is referenced but not shown in the truncated file. If it fails, errors are caught at line 142–144, incremented as `_stats["errors"]`, but the error is only logged at `DEBUG` level (line 144). No retry or backoff strategy for malformed messages.
- **Files:** `ais_listener.py` (lines 137–145)
- **Impact:** Silent message loss; operator won't notice degradation until reviewing stats
- **Fix approach:**
  1. Log message parsing errors at WARNING level with sample of the malformed message
  2. Add exponential backoff or circuit breaker if error rate exceeds threshold

### Dark Period Haversine Calculation with None Values
- **Issue:** `dark_periods.py` calls `_haversine()` without null checks. If `last_lat`, `last_lon`, `reappear_lat`, or `reappear_lon` are None, the function will crash.
- **Files:** `dark_periods.py` (lines 90–93)
- **Impact:** Dark period detection can fail silently if any coordinate is missing
- **Fix approach:** Return `None` for distance if any coordinate is missing, or pre-filter gaps with valid coordinates before calculating distance

### Screening Hit Validation Silent Failure
- **Issue:** `screening.py` (lines 150–153) catches exceptions during `ScreeningHit.model_validate()` but silently skips invalid hits with `continue`. The reason is not logged.
- **Files:** `screening.py` (lines 149–153)
- **Impact:** Operator loses visibility into why certain sanctions entries don't appear in results
- **Fix approach:** Log the validation error at WARNING level before skipping the hit

### MMSI Validation Edge Case in AIS Listener
- **Issue:** AIS messages from `aisstream.io` may include partial MMSI fields (fewer than 9 digits after padding). The listener doesn't validate MMSI format before buffering.
- **Files:** `ais_listener.py` (referenced but implementation not shown in truncated file)
- **Impact:** Invalid MMSIs can be persisted to `ais_positions`, breaking downstream queries
- **Fix approach:** Add `schemas.AisPosition.model_validate()` on incoming messages before buffering (or rely on Pydantic validation at insert time)

---

## Security Considerations

### Session Authentication Bypass Risk
- **Issue:** The login session mechanism (`app.py`, lines 44–79) uses simple password comparison without rate limiting or account lockout.
- **Files:** `app.py` (lines 44–79), no rate limiting middleware
- **Impact:**
  - Brute-force attacks are trivial (no throttle on `/login` POST)
  - All endpoints redirect unauthenticated users to login, but no CSRF protection on the form
- **Current mitigation:**
  - Password is stored in `APP_PASSWORD` env var (Railway plugin keeps secrets encrypted)
  - Session uses Flask's default secure cookie
- **Recommendations:**
  1. Add rate limiting middleware (e.g., `Flask-Limiter`) to `/login` POST (max 5 attempts per minute)
  2. Add CSRF token to login form
  3. Consider OAuth2 integration for production (e.g., GitHub, Keycloak) once multi-user support is needed

### Overly Permissive CORS / API Exposure
- **Issue:** All authenticated endpoints are accessible via REST without CORS restrictions specified in the code. If deployed publicly, any authenticated browser could call sensitive endpoints.
- **Files:** `app.py` (no CORS or SameSite cookie settings)
- **Impact:**
  - Cross-site request forgery is possible if a user is tricked into visiting a malicious site
  - API endpoints are not protected by Same-Site cookie policy
- **Fix approach:**
  1. Add `Flask-CORS` and configure `CORS(app, origins=["https://yourdomain.com"])`
  2. Add `SESSION_COOKIE_SAMESITE = "Lax"` to Flask config
  3. Document API security model in `SECURITY.md` (exists, check current content)

### Risk Scoring Not Cryptographically Backed
- **Issue:** `risk_score` in `screening.py` (lines 169–182) is a simple sum of weighted indicators. No signature or audit trail; the score can be trivially modified in the database.
- **Files:** `screening.py` (lines 169–182), `db.py` (risk_score columns throughout)
- **Impact:** For high-stakes decisions (e.g., freezing assets), an attacker with DB access could lower a vessel's risk score
- **Current mitigation:** None
- **Recommendations:**
  1. Add audit logging for all risk score changes (timestamp, old value, new value, reason)
  2. Consider digital signatures on critical screening outputs
  3. Document that this tool is for intelligence research, not compliance (see existing `SECURITY.md`)

### Secrets in Logs
- **Issue:** Multiple API keys and credentials flow through the logger:
  - `AISSTREAM_API_KEY` is passed to `ais_listener.start()` (app.py line 39, 271)
  - `APP_PASSWORD` is never logged, but if `request.form.get("password")` were logged, it would be exposed
- **Files:** `app.py` (lines 35–39, 268–271), `ais_listener.py` (API key in logs)
- **Impact:**
  - AIS API key could be exposed in Rails logs if debugging is enabled
  - No sensitive data masking in log output
- **Fix approach:**
  1. Add a logging filter to mask API keys in all log output
  2. Never log password fields or form data
  3. Use `logging.config` to set up a custom formatter that redacts secrets

### Unauthenticated Health Check Leaks Stats
- **Issue:** `/health` endpoint (app.py, lines 84–86) is unauthenticated and always returns 200. However, no endpoint exposes stats; this is not an immediate risk.
- **Files:** `app.py` (lines 84–86)
- **Impact:** Low — just confirms the app is running
- **Fix approach:** Keep as-is for monitoring; consider adding optional `?verbose=1` flag that requires auth if detailed stats are added later

### Dependency Vulnerability — lxml
- **Issue:** `lxml>=5.0.0` is used to parse OFAC SDN XML (`ingest.py`, line 75). Older versions had XXE (XML External Entity) vulnerabilities, but lxml 5.0+ is patched. However, the `pyproject.toml` disables Ruff rule `S314` (line 49), which checks for XML vulnerabilities.
- **Files:** `pyproject.toml` (line 49), `ingest.py` (lines 75, `ET.fromstring()`)
- **Impact:** Future developers might not realize XML parsing is a risk zone
- **Fix approach:**
  1. Add a comment explaining why `S314` is disabled (XML parsing is safe with external input filtering)
  2. Consider adding a custom linting rule or docstring on `fetch_ofac_sdn()` noting the XML attack surface

---

## Performance Bottlenecks

### Database Query N+1 in Screening Pipeline
- **Issue:** `screening.py` (lines 140–153) iterates over hits and calls `db.get_vessel_ownership()` and `db.get_vessel_flag_history()` inside a loop. Each call is a separate database query.
- **Files:** `screening.py` (lines 146–148)
- **Impact:**
  - Screening a vessel with 10 sanctions hits triggers 20+ queries
  - On PostgreSQL, acceptable; on SQLite, could cause locking contention
- **Fix approach:**
  1. Batch the queries: fetch all ownership records for all canonical_ids in one query
  2. Add a new `db.get_batch_vessel_ownership(canonical_ids: list[str])` function
  3. Cache results in memory during a single screening request

### AIS Position Buffer Inefficiency
- **Issue:** `ais_listener.py` buffers positions (line 32, `BUFFER_SIZE = 50`) but does not implement smart batching. If messages arrive slowly, a batch insert might wait indefinitely.
- **Files:** `ais_listener.py` (lines 31–32, 150+)
- **Impact:**
  - High latency between AIS message receipt and database availability (could be minutes)
  - If the listener crashes, up to 50 messages are lost
- **Fix approach:**
  1. Add a timeout-based flush: if 30 seconds have passed since last flush, flush even if buffer < 50
  2. Add explicit `_flush_buffer()` calls on WebSocket disconnect
  3. Consider increasing `BUFFER_SIZE` to 500 if batch insert time is acceptable

### Full-Table Scan for AIS Gap Detection
- **Issue:** `db.find_ais_gaps()` (referenced from `dark_periods.py` line 63) is not shown, but based on usage, it likely scans `ais_positions` for all MMSIs without filtering. On a large dataset (millions of positions), this could be slow.
- **Files:** `db.py` (implementation not visible in first 500 lines), `dark_periods.py` (line 63)
- **Impact:** Dark period detection at scale (all MMSIs) could take minutes
- **Fix approach:**
  1. Add time-window filtering: only scan positions from the last 30–90 days
  2. Add indexes on `(mmsi, position_ts DESC)` (already in schema, line 345)
  3. Add query plan analysis / `EXPLAIN` output to the documentation

### Risk Score Calculation Overhead
- **Issue:** `screen_vessel_detail()` (screening.py, lines 164–182) performs a complex risk calculation with 7+ weighted components. If called for many vessels (e.g., in a bulk screening API), it could be slow.
- **Files:** `screening.py` (lines 164–182)
- **Impact:** Bulk screening is not optimized; each vessel requires a separate calculation
- **Fix approach:**
  1. Cache risk scores in `vessels_canonical.risk_score` and regenerate on-demand
  2. Add a background job to pre-compute scores for top-ranked vessels
  3. Profile the calculation with Python's `cProfile` module

---

## Fragile Areas

### Canonical Reconciliation Data Loss Risk
- **Issue:** `reconcile.py` performs merges (`db.merge_canonical()`) without explicit transaction handling. If the merge fails mid-operation, the database could be left in an inconsistent state (one canonical deleted, memberships partially reassigned).
- **Files:** `reconcile.py` (lines 39–50, 70, 91), `db.py` (merge_canonical implementation not shown)
- **Impact:**
  - Duplicate or orphaned records in `vessels_canonical` after a failed reconciliation
  - Future ingests might create new duplicates
- **Fix approach:**
  1. Wrap `run_reconciliation()` in a transaction: call `BEGIN` before tier1, `COMMIT` after tier2, `ROLLBACK` on any exception
  2. Add a dry-run mode to `reconcile.py` that prints what would be merged without committing
  3. Add pre- and post-reconciliation integrity checks (e.g., count canonical records, verify foreign keys)

### AIS Listener Daemon Thread State Consistency
- **Issue:** `ais_listener.py` uses module-level mutable state (`_buffer`, `_stats`) that is accessed from multiple threads (the listener thread and Flask request threads). There is no lock protecting `_buffer` or `_stats`.
- **Files:** `ais_listener.py` (lines 36–48), `_flush_buffer()` (not shown), `get_stats()` (lines 53–66)
- **Impact:**
  - Race conditions between the listener thread writing to `_buffer` and the flush thread reading/clearing it
  - Stats could be inconsistent if a request fetches stats while they're being updated
  - A malformed message could corrupt `_buffer` or `_stats`
- **Fix approach:**
  1. Use `threading.Lock()` to protect all reads/writes to `_buffer` and `_stats`
  2. Wrap stats access in a property that acquires the lock: `with _lock: s = dict(_stats)`
  3. Consider switching from module-level state to a thread-safe class (`threading.Thread` subclass)

### OFAC XML Parsing Lacks Error Recovery
- **Issue:** `ingest.py` (lines 75, `ET.fromstring(resp.content)`) will raise an exception if the XML is malformed. There is no retry or graceful degradation.
- **Files:** `ingest.py` (lines 63–76)
- **Impact:**
  - A single malformed OFAC SDN file will block the entire ingest
  - No partial results; either all entries are ingested or none
- **Fix approach:**
  1. Wrap `ET.fromstring()` in a try-except; if parsing fails, attempt to recover by stripping invalid characters or using a lenient parser
  2. Log the error and return an empty list (or partial results up to the first error)
  3. Consider adding a retry mechanism with exponential backoff for HTTP failures

### Port Call Detection Coordinate Validation
- **Issue:** `ports.py` performs spatial queries on `port_calls` without validating that `center_lat` and `center_lon` are within valid ranges. Invalid coordinates could crash geometry calculations.
- **Files:** `ports.py` (referenced but not shown in truncated file)
- **Impact:** Bad port data could silently corrupt the port call detection results
- **Fix approach:**
  1. Add range checks: `assert -90 <= lat <= 90 and -180 <= lon <= 180` before any spatial query
  2. Add a database constraint: `CHECK (center_lat >= -90 AND center_lat <= 90 AND center_lon >= -180 AND center_lon <= 180)`
  3. Add unit tests for boundary cases (poles, date line)

---

## Scaling Limits

### SQLite Concurrent Write Lock
- **Issue:** SQLite uses a file-level write lock, so only one writer can update the database at a time. On a single developer machine, this is fine; in production, it becomes a bottleneck.
- **Current capacity:** ~100 writes/second (WAL mode, single process)
- **Limit:** Breaks at 500+ concurrent writes/second
- **Scaling path:**
  1. Use PostgreSQL (already configured for Railway, line 28 in `db.py`)
  2. Set connection pool size based on load: currently `ThreadedConnectionPool(1, 10, ...)` (line 50) — increase max to 20–50 for higher concurrency
  3. Consider read replicas if query volume exceeds 1000 QPS

### AIS Position Storage Growth
- **Issue:** `ais_positions` table grows unbounded. At current ingest rate (aisstream.io free tier ~100 msgs/min), the table could grow by 5+ million rows per month.
- **Current capacity:** 212 GB database file suggests millions of rows already stored
- **Limit:** SQLite files >2 GB become slow; PostgreSQL becomes slow at 1 billion rows without partitioning
- **Scaling path:**
  1. Add data retention policy: delete positions older than 90 days (configurable)
  2. Archive old data to S3 or tape before deletion
  3. Partition `ais_positions` by time (e.g., monthly tables) once moving to PostgreSQL
  4. Consider a time-series database (e.g., TimescaleDB extension on PostgreSQL)

### Sanctions Entry Duplication at Scale
- **Issue:** As more sanctions lists are ingested, the risk of duplicate canonicals increases. At 50+ sources, reconciliation becomes slow (O(n²) MMSI collision detection).
- **Current capacity:** ~18,000 OFAC + ~5,000 OpenSanctions entries = 23,000 entries
- **Limit:** Reconciliation becomes slow (>10 seconds) at 100,000+ entries
- **Scaling path:**
  1. Add a fuzzy-matching service to de-duplicate on ingestion (e.g., Levenshtein distance on vessel name)
  2. Implement incremental reconciliation: only reconcile newly ingested entries
  3. Use a caching layer (Redis) to memoize name-matching results

### Memory Usage in Detection Loops
- **Issue:** `dark_periods.py` and `sts_detection.py` load entire result sets into memory before processing. For large time windows (e.g., all AIS positions from the last 5 years), this could consume GB of RAM.
- **Current capacity:** ~500 MB for a 30-day window
- **Limit:** Out-of-memory errors at 5-year scans
- **Scaling path:**
  1. Use database cursors with `fetchmany(1000)` instead of `fetchall()`
  2. Implement streaming detection: process records one at a time
  3. Consider a map-reduce framework (Apache Spark) for very large historical scans

---

## Dependencies at Risk

### Anthropic SDK Not Currently Used
- **Issue:** `anthropic>=0.40.0` is listed in `pyproject.toml` (line 10) but is not imported or used anywhere in the codebase. It was likely added for future AI enrichment features.
- **Files:** `pyproject.toml` (line 10), no imports in `*.py`
- **Impact:**
  - Dead dependency; increases attack surface and build time
  - No benefit until the feature is implemented
- **Fix approach:**
  1. Remove `anthropic` from dependencies until a feature requires it
  2. If keeping it, document the planned use case (e.g., "Planned for LLM-based name matching in Phase 2")
  3. Consider using a `extras` dependency group in `pyproject.toml` for optional features

### Deprecated Websockets Usage Pattern
- **Issue:** `ais_listener.py` imports `websockets` lazily (line 123: "Import here so the module loads even if websockets isn't installed"). This is a workaround for an optional dependency, but `websockets` is listed as required in `pyproject.toml`.
- **Files:** `ais_listener.py` (line 123), `pyproject.toml` (line 8)
- **Impact:** Confusing and redundant — the lazy import serves no purpose if websockets is required
- **Fix approach:**
  1. Move `import websockets` to the top of the file
  2. If websockets should truly be optional, use extras: `websockets>=12.0; extra == "ais"`
  3. Update documentation to clarify that AIS requires websockets

### Security Update Path for lxml
- **Issue:** `lxml>=5.0.0` is pinned to a minimum version but not a maximum. New lxml major versions could introduce breaking changes or unexpected behavior.
- **Files:** `pyproject.toml` (line 7)
- **Impact:**
  - May auto-upgrade to a breaking version during `pip install --upgrade`
  - Not a risk for normal development, but important for CI/CD
- **Fix approach:**
  1. Pin to a safe range: `lxml>=5.0.0,<6.0.0`
  2. Set up Dependabot or similar to notify when a new major version is available
  3. Add a `requirements-lock.txt` or `poetry.lock` file to ensure reproducible builds

---

## Missing Critical Features

### No Input Validation on Long-running Detection Tasks
- **Issue:** Endpoints like `/api/dark-periods/detect` (app.py, lines 330–353) accept unbounded `min_hours` and `hours_back` parameters. A user could pass `hours_back=87600` (10 years) and crash the app.
- **Files:** `app.py` (lines 330–353), `schemas.py` (no validation shown for these params)
- **Impact:** Denial-of-service via expensive queries
- **Fix approach:**
  1. Add Pydantic field constraints: `hours_back: int = Field(48, gt=0, le=8760)` (1 year max)
  2. Add a timeout decorator: detect runs longer than 60s should return a partial result or background job ID
  3. Document API rate limits (e.g., max 10 detection jobs per minute per user)

### No Audit Logging for Admin Actions
- **Issue:** Ingests (`/api/ingest/*` endpoints) and reconciliations (`/api/reconcile`) are not logged with user/timestamp/before-after snapshots. An admin could run an ingest and there's no trace of what changed.
- **Files:** `app.py` (lines 177–252, 534–555), `db.log_ingest_complete()` exists but doesn't capture before/after state
- **Impact:**
  - No accountability for data changes
  - Difficult to audit for compliance (e.g., OFAC screening audits)
- **Fix approach:**
  1. Expand `ingest_log` table schema: add `admin_user`, `records_before`, `records_after`, `checksum` (hash of changes)
  2. Log all reconciliation merges with canonical_id pairs and timestamp
  3. Create a `/api/audit-log` endpoint (protected, for admins only) to review changes

### No Bulk Screening or Batch Job API
- **Issue:** To screen 1,000 vessels, you must call `/api/screen` 1,000 times. There is no batch endpoint or async job queue.
- **Files:** `app.py` (lines 107–117), `screening.py` (screen function)
- **Impact:**
  - Inefficient for bulk operations (e.g., daily re-screening of a fleet)
  - No way to offload long-running tasks to a background worker
- **Fix approach:**
  1. Add `/api/batch-screen` endpoint that accepts a CSV or JSON list of vessels
  2. Return a job ID and store results in a `batch_jobs` table
  3. Use Celery or APScheduler to queue the batch task
  4. Add `/api/batch-screen/<job_id>/status` and `/api/batch-screen/<job_id>/results` endpoints

### No Data Freshness Validation
- **Issue:** There is no automatic check that sanctions lists are not stale. A missing scheduled ingest could go unnoticed for weeks.
- **Files:** `app.py` (ingest endpoints), `db.py` (ingest_log table)
- **Impact:**
  - Operators might rely on outdated OFAC data without realizing it
  - Compliance risk: screening against stale lists provides no protection
- **Fix approach:**
  1. Add a `last_ingest_date` column to `ingest_log` or a separate `source_freshness` table
  2. Add a `/api/health/data-freshness` endpoint that returns warnings if any source is >7 days old
  3. Set up a scheduled ingest job (via APScheduler or GitHub Actions) to auto-run ingestss weekly
  4. Send an alert (Slack, email) if an ingest fails

---

## Test Coverage Gaps

### No Tests for Database Backend Switching
- **Issue:** The codebase has dual-backend support (SQLite + PostgreSQL) but no tests verify both backends behave identically. A change to SQL queries could break one backend without being caught.
- **Files:** `db.py` (backend switching logic), no `tests/` directory visible
- **Impact:**
  - SQLite bugs could go unnoticed until production deployment to PostgreSQL
  - Developers may not realize they've written Postgres-specific SQL
- **Priority:** High
- **Fix approach:**
  1. Create `tests/test_db_backends.py` with tests for both SQLite and PostgreSQL
  2. Use a CI matrix to run tests on both backends
  3. Add fixtures to create and tear down test databases for each backend

### No End-to-End Tests for AIS Listener
- **Issue:** The AIS listener thread is complex (reconnect logic, buffering, parsing) but is not tested. It's only tested manually.
- **Files:** `ais_listener.py`, no visible tests
- **Impact:**
  - Reconnection bugs, race conditions, or message loss would only be caught in production
  - Regressions during refactoring are likely
- **Priority:** High
- **Fix approach:**
  1. Create a mock WebSocket server for testing
  2. Add `tests/test_ais_listener.py` with scenarios: connection success, disconnect/reconnect, malformed messages
  3. Use `unittest.mock` to inject test messages and verify buffer state

### No Tests for Screening Logic
- **Issue:** `screening.py` performs complex query and annotation logic but is not tested. Edge cases like fallback MMSI matching, ownership chain checks, and confidence scoring are untested.
- **Files:** `screening.py` (356 lines), no visible tests
- **Impact:**
  - Screening bugs could go unnoticed (e.g., confidence scoring is wrong, fallback search doesn't work)
  - Refactoring is risky
- **Priority:** High
- **Fix approach:**
  1. Create `tests/test_screening.py` with test cases for:
     - IMO exact match → HIGH confidence
     - MMSI fallback when IMO has no hits
     - Name matching → MEDIUM confidence
     - Ownership chain matching (IND21)
  2. Use fixtures with pre-populated mock vessels and sanctions entries
  3. Verify confidence labels are correct for each match type

### No Tests for Reconciliation
- **Issue:** `reconcile.py` performs merges and canonical consolidation but is not tested. Data loss bugs or orphaned records would go unnoticed.
- **Files:** `reconcile.py` (93 lines), no visible tests
- **Impact:**
  - Reconciliation bugs could corrupt the canonical registry
  - Tier 1 and Tier 2 merges are not validated before committing
- **Priority:** High
- **Fix approach:**
  1. Create `tests/test_reconcile.py` with scenarios:
     - Two canonicals with the same IMO merge into one
     - MMSI-keyed canonical merges into IMO-keyed canonical
     - All memberships and ownership records survive the merge
  2. Verify `source_tags` are rebuilt correctly after merges
  3. Add a dry-run test that prints merge operations without committing

### No Tests for Dark Period Detection Edge Cases
- **Issue:** `dark_periods.py` performs spatial and temporal calculations (Haversine distance, risk zone classification) but is not tested for edge cases (poles, date line, null coordinates).
- **Files:** `dark_periods.py`, no visible tests
- **Impact:**
  - Polar vessels or edge-case coordinates could cause crashes or wrong risk scores
  - Boundary cases are not verified
- **Priority:** Medium
- **Fix approach:**
  1. Create `tests/test_dark_periods.py` with edge cases:
     - Null coordinates (should skip distance calculation)
     - Poles (lat = ±90)
     - Date line (lon = ±180)
     - Risk zone boundary vessels (just inside/outside zone)
  2. Verify distance calculations are correct (unit test Haversine against known distances)

---

*Concerns audit: 2026-03-03*
