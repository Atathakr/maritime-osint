# db/connection.py
"""
Backend detection and connection management for Maritime OSINT Platform.

Dual-backend:
  - SQLite   — local development (no DATABASE_URL, or sqlite:///... URL)
  - PostgreSQL — Railway production  (DATABASE_URL = postgresql://...)

All public functions are backend-agnostic; callers never import psycopg2 directly.
"""

import json  # noqa: F401 — exported for sub-module use
import os
import sqlite3
from contextlib import contextmanager

import normalize  # noqa: F401 — project root; stays as top-level import

# ── Backend detection ─────────────────────────────────────────────────────

_DB_URL: str = ""
_BACKEND: str = "sqlite"   # 'sqlite' | 'postgres'
_POOL = None                # ThreadedConnectionPool (postgres only)


def _init_backend() -> None:
    global _DB_URL, _BACKEND
    _DB_URL = os.getenv("DATABASE_URL", "")
    _BACKEND = "postgres" if _DB_URL.startswith(("postgresql://", "postgres://")) else "sqlite"


_init_backend()


def _sqlite_path() -> str:
    # db/connection.py lives one level below the project root — go up one directory
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _DB_URL.startswith("sqlite:///"):
        rel = _DB_URL[10:]
        # If it looks relative, anchor it to the project directory
        return rel if os.path.isabs(rel) else os.path.join(_here, rel)
    return os.path.join(_here, "maritime_osint.db")


# ── Connection management ─────────────────────────────────────────────────

def _get_pool():
    global _POOL
    if _POOL is None:
        from psycopg2.pool import ThreadedConnectionPool
        url = _DB_URL.replace("postgres://", "postgresql://", 1)
        _POOL = ThreadedConnectionPool(1, 10, dsn=url)
    return _POOL


@contextmanager
def _conn():
    """
    Yield a database connection; commit on clean exit, rollback on exception,
    always release/close.
    """
    if _BACKEND == "postgres":
        pool = _get_pool()
        conn = pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    else:
        conn = sqlite3.connect(_sqlite_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _cursor(conn):
    """Return a cursor with dict-like rows for the current backend."""
    if _BACKEND == "postgres":
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()   # sqlite3.Row already set on conn


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def _row(cursor) -> dict | None:
    r = cursor.fetchone()
    return dict(r) if r else None


# ── SQL helpers ───────────────────────────────────────────────────────────

_P = "%s" if _BACKEND == "postgres" else "?"   # param placeholder


def _ph(n: int = 1) -> str:
    """Return n comma-separated placeholders for the current backend."""
    p = "%s" if _BACKEND == "postgres" else "?"
    return ", ".join([p] * n)


def _ilike(col: str) -> str:
    """Case-insensitive LIKE operator."""
    p = "%s" if _BACKEND == "postgres" else "?"
    return f"{col} {'ILIKE' if _BACKEND == 'postgres' else 'LIKE'} {p}"


def _jp() -> str:
    """JSON-typed parameter placeholder — includes ::jsonb cast for Postgres."""
    return "%s::jsonb" if _BACKEND == "postgres" else "?"
