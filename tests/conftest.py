# tests/conftest.py
"""
Phase 1 conftest — set DATABASE_URL before any db import.
This prevents tests from accidentally connecting to a real PostgreSQL instance.
"""
import os

# Must be set before any db import anywhere in the test session.
os.environ.setdefault("DATABASE_URL", "")
