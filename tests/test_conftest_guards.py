import os


def test_database_url_cleared():
    """T01: conftest.py must force DATABASE_URL to empty string before test collection."""
    assert os.environ.get("DATABASE_URL") == "", \
        f"DATABASE_URL not cleared by conftest.py: got {os.environ.get('DATABASE_URL')!r}"


def test_aisstream_key_cleared():
    """T02: conftest.py must remove AISSTREAM_API_KEY before test collection."""
    assert "AISSTREAM_API_KEY" not in os.environ, \
        "AISSTREAM_API_KEY still present — conftest.py did not pop it"
