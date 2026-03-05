"""
tests/conftest.py — Phase 3 upgrade

Force-clears DATABASE_URL and AISSTREAM_API_KEY at module import time, before pytest
collects any test files. Module-level code in conftest.py runs before test collection.

Using os.environ["DATABASE_URL"] = "" (not setdefault) because setdefault is a no-op
when CI already exports DATABASE_URL=postgresql://..., which would connect to production.
"""
import os
import pytest

# Force-clear before any db or app import in the test session.
# This matches the pattern used in test_scores.py (os.environ["DATABASE_URL"] = "").
os.environ["DATABASE_URL"] = ""
os.environ.pop("AISSTREAM_API_KEY", None)


@pytest.fixture(scope="session")
def sqlite_db():
    """
    Initialize a fresh in-memory-equivalent SQLite DB for the test session.

    Note: db._sqlite_path() is __file__-anchored to the project root (not cwd).
    Tests that write to the DB use unique MMSI/IMO strings to avoid collisions
    with Phase 2 tests (which use IMO1234567 through IMO6666666).
    Phase 3 db-touching tests use IMO7000001 onward.
    """
    import db
    db._init_backend()
    db.init_db()
    return db._sqlite_path()
