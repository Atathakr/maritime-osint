# Codebase Concerns

**Analysis Date:** 2024-05-24

## Tech Debt

**Database Layer Complexity:**
- Issue: The `db.py` file is extremely large (~2000 lines) and handles dual backends (SQLite and PostgreSQL) with manual string manipulation for SQL dialect differences.
- Files: `db.py`
- Impact: Hard to maintain, prone to SQL injection risks if not careful, and difficult to test.
- Fix approach: Use an ORM like SQLAlchemy or a query builder that handles dialect differences natively. Split the file into smaller modules (e.g., `db/base.py`, `db/postgres.py`, `db/sqlite.py`).

**Manual Thread Management:**
- Issue: AIS listener runs in a manual `threading.Thread` with a custom asyncio loop inside it.
- Files: `ais_listener.py`
- Impact: Error handling and lifecycle management are complex and potentially fragile.
- Fix approach: Use a task queue (like Celery/Redis) or a more robust background worker pattern.

## Security Risks

**Simple Password Authentication:**
- Issue: Authentication is a single shared `APP_PASSWORD` stored in environment variables.
- Files: `app.py`
- Risk: Low security for a platform handling potentially sensitive maritime data. No multi-user support or audit logs.
- Current mitigation: `login_required` decorator and session-based authentication.
- Recommendations: Implement a proper identity provider or at least hashed passwords with individual user accounts.

**Missing CSRF Protection:**
- Issue: Flask-WTF or standard CSRF protection is not evident in the POST routes.
- Files: `app.py`
- Risk: Cross-Site Request Forgery on state-changing actions like starting/stopping the AIS listener or triggering reconciliation.
- Recommendations: Enable Flask-WTF CSRF protection.

## Performance Bottlenecks

**Database Write Pressure:**
- Issue: While AIS positions are buffered (size 50), the high volume of global tanker AIS data could still overwhelm the database, especially SQLite.
- Files: `ais_listener.py`, `db.py`
- Cause: Synchronous database writes in batches.
- Improvement path: Move to a time-series database for positions or use an async database driver (e.g., `asyncpg`).

**Blocking Operations in Web Routes:**
- Issue: Several API endpoints (reconcile, detect) perform heavy logic synchronously.
- Files: `app.py`
- Cause: Direct calls to `reconcile.reconcile_all()`, `screening.screen_vessel()`, etc., within the request-response cycle.
- Improvement path: Move long-running operations to background tasks.

## Fragile Areas

**Dual Backend Logic:**
- Files: `db.py`
- Why fragile: Every new table or complex query must be implemented/verified for two different SQL dialects.
- Safe modification: Requires thorough manual testing on both SQLite and Postgres.
- Test coverage: Significant gaps in automated testing for both backends.

## Test Coverage Gaps

**Missing Test Suite:**
- What's not tested: No automated tests (unit or integration) were identified in the codebase.
- Files: Entire codebase.
- Risk: High risk of regressions when modifying core logic in `db.py`, `normalize.py`, or `screening.py`.
- Priority: High.

---

*Concerns audit: 2024-05-24*
