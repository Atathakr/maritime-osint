# Deferred Items — Phase 07

## Pre-existing Issue: conftest guard tests fail when test_alerts.py is in suite

**Discovered during:** Plan 07-01, Task 3

**Issue:** `tests/test_conftest_guards.py::test_database_url_cleared` and `test_aisstream_key_cleared` fail when `test_alerts.py` is included in the test run. Root cause: `app_client` fixture (used by the stub/real tests in test_alerts.py) triggers `from app import app`, which runs `load_dotenv(override=True)` at line 51 of app.py — this re-loads `.env` and re-sets `AISSTREAM_API_KEY` and `DATABASE_URL` for the process. Since `test_conftest_guards.py` runs AFTER `test_alerts.py` (alphabetical order), the guard tests see the re-set values.

**Confirmed pre-existing:** Verified that the original stub test_alerts.py (Plan 07-00) produced the same 2 failures in the full suite (10 total failures: 8 stubs + 2 conftest guard).

**Impact:** Cosmetic — does not affect correctness of any production code. The 4 target tests (ALRT-04/05/06/07) pass correctly.

**Fix (for a future plan):** Either:
1. Add `os.environ.pop("AISSTREAM_API_KEY", None); os.environ["DATABASE_URL"] = ""` at the end of the `app_client` fixture in `conftest.py` (after fixture teardown), OR
2. Wrap the `load_dotenv(override=True)` call in app.py line 51 with a `DOTENV_DISABLED` check (matching line 10-12 pattern), OR
3. Set `DOTENV_DISABLED=1` before `from app import app` in the `app_client` fixture.

**Out of scope for Plan 07-01:** This is a pre-existing issue not introduced by the plan's changes.
