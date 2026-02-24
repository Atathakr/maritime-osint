# Coding Conventions

**Analysis Date:** 2025-01-24

## Naming Patterns

**Files:**
- Python: `snake_case.py` (e.g., `ais_listener.py`, `dark_periods.py`)
- JavaScript: `camelCase.js` (e.g., `app.js`, `map.js`)
- HTML: `lowercase.html` (e.g., `dashboard.html`, `login.html`)

**Functions:**
- Python: `snake_case` (e.g., `init_db`, `login_required`). Internal functions are prefixed with an underscore (e.g., `_conn`).
- JavaScript: `camelCase` (e.g., `loadStats`, `apiFetch`). Internal-ish variables sometimes use a leading underscore (e.g., `_bootDone`).

**Variables:**
- Python: `snake_case` for local variables and parameters. `UPPER_SNAKE_CASE` for constants and global configuration (e.g., `APP_PASSWORD`, `_DB_URL`).
- JavaScript: `camelCase` for most variables. `UPPER_SNAKE_CASE` for constants (e.g., `PAGE_SIZE`).

**Types:**
- Python (Pydantic models): `PascalCase` (e.g., `AisPosition`, `SanctionsEntry` in `schemas.py`).

## Code Style

**Formatting:**
- **Python:** Ruff is used for formatting. Line length is set to 100 characters in `pyproject.toml`.
- **JavaScript:** Standard vanilla JS with 2-space indentation. No automated formatter detected in config.

**Linting:**
- **Python:** Ruff is the primary linter. Many rules are explicitly ignored in `pyproject.toml` (e.g., missing docstrings, missing type annotations, print statements). This indicates a preference for development speed over strict compliance.
- **JavaScript:** `'use strict';` is used in `static/app.js`. No ESLint config detected.

## Import Organization

**Order:**
1. Standard library imports
2. Third-party library imports
3. Local module imports

**Path Aliases:**
- Not detected. Absolute paths or relative imports within the root directory are used.

## Error Handling

**Patterns:**
- **Python:** Uses `try-except` blocks. In `db.py`, a context manager `_conn` handles database transactions with automatic rollback on exception.
- **JavaScript:** Uses `try-catch` blocks around `async` API calls. Errors are typically logged to the console or displayed in the UI via `escHtml`.

## Logging

**Framework:** `console` for JavaScript. Python uses `print` statements (explicitly allowed by ignoring Ruff's `T201` rule).

**Patterns:**
- Simple logging of successes/failures to the console/stdout.
- JavaScript `apiFetch` logs failed requests.

## Comments

**When to Comment:**
- Large files use section dividers: `# ── Section Name ─────────────────────────────────────────────────────────────`.
- Module-level docstrings are common.
- Function-level docstrings describe purpose and design.

**JSDoc/TSDoc:**
- Minimal usage. Basic block comments for helpers in `static/app.js`.

## Function Design

**Size:** Functions are generally small and focused on a single task (e.g., one API endpoint or one UI component refresh).

**Parameters:** Python functions often use type hints for parameters and return values, especially in core modules like `db.py` and `normalize.py`.

**Return Values:**
- Database functions return lists of dictionaries or single dictionaries.
- API endpoints return JSON responses via Flask's `jsonify`.

## Module Design

**Exports:**
- Python: Modules are imported directly.
- JavaScript: Global scope in `static/app.js` and `static/map.js`.

**Barrel Files:**
- `schemas.py` acts as a central location for data models.

---

*Convention analysis: 2025-01-24*
