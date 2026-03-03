# Contributing to Maritime OSINT

Thank you for your interest in contributing. This document covers development
setup, code conventions, how to add new indicators, and the PR process.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Code Style](#code-style)
4. [How to Add a New Indicator](#how-to-add-a-new-indicator)
5. [Pull Request Process](#pull-request-process)
6. [Issue Types](#issue-types)
7. [Data and Privacy Notes](#data-and-privacy-notes)

---

## Development Setup

**Requirements:** Python 3.11+, Git

```bash
git clone https://github.com/Atathakr/maritime-osint.git
cd maritime-osint

python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
pip install ruff                 # required for contributions

cp .env.example .env
# Leave all values blank for local development

python app.py
```

The app starts on http://localhost:5000 with SQLite. No PostgreSQL instance is
needed for development.

---

## Project Structure

| File | Role |
|---|---|
| `app.py` | Flask routes and auth middleware — keep handlers thin |
| `db.py` | All database schema and queries — single source of truth |
| `screening.py` | Core risk scoring — `screen_vessel_detail()` assembles all indicators |
| `risk_config.py` | All scoring weights, thresholds, and flag tier definitions |
| `ingest.py` | Data downloaders: OFAC SDN, OpenSanctions, PSC MOU lists |
| `schemas.py` | All Pydantic request and response models |
| `static/app.js` | Frontend: vessel profile renderer, signal rows, ingest controls |

---

## Code Style

The project uses [Ruff](https://docs.astral.sh/ruff/). Configuration is in
`pyproject.toml`.

**Before every commit:**

```bash
ruff check .
ruff format .
```

Key rules:
- Line length: 100 characters
- `select = ["ALL"]` with ignores in `pyproject.toml` — these are intentional
- Type annotations: welcome but not required (ANN disabled)
- Docstrings: encouraged for public functions

**Conventions:**
- All SQL belongs in `db.py`. Use the `_conn()` / `_cursor()` context managers
  and placeholder helper (`"?" if _BACKEND == "sqlite" else "%s"`).
- Return `jsonify(...)` from all Flask routes.
- Apply `@login_required` to all routes.
- New Pydantic models go in `schemas.py`.

---

## How to Add a New Indicator

Ten indicators in `docs/indicators.md` are marked "Not yet implemented" and
are good contribution candidates. Use the **New Indicator** issue template to
propose before starting non-trivial work.

### Step 1 — Choose an indicator

Check `docs/indicators.md`. "Not feasible" indicators require proprietary data
and should not be attempted without a new open-source data source.

### Step 2 — Create the detection module

Follow the pattern of `dark_periods.py` or `sts_detection.py`:
- Module-level constants for all thresholds
- A `run_detection(mmsi=None, ...)` function that queries, detects, and
  persists results
- A summary helper returning a dict for the API response

### Step 3 — Add the database table

Add `CREATE TABLE IF NOT EXISTS` in both `_init_postgres()` and
`_init_sqlite()` in `db.py`. Add `upsert_X()` and `get_X_count(mmsi)` query
functions following existing naming conventions.

### Step 4 — Add scoring to `screening.py`

In `screen_vessel_detail()`, add a block after the existing indicator blocks:

```python
# ── INDXX: Your indicator name ────────────────────────────────────────────
your_count = db.get_your_count(imo_clean)
your_score = min(your_count * risk_config.INDXX_PTS_PER_EVENT, risk_config.INDXX_CAP)
if your_score > 0 and not processed_hits:
    risk_factors.append(f"Your description (+{your_score} pts, INDXX)")
```

Add the score to the `risk_score` formula.

### Step 5 — Add constants to `risk_config.py`

```python
INDXX_PTS_PER_EVENT: int = 10
INDXX_CAP:           int = 30
```

### Step 6 — Add the API endpoint in `app.py`

```python
@app.post("/api/your-indicator/detect")
@login_required
def api_detect_your_indicator():
    """Run INDXX detection. Body (all optional): {...}"""
    ...
```

### Step 7 — Update `docs/indicators.md`

Update the indicator's status. Add the DB table name, thresholds, and score
formula.

### Step 8 — Add tests (strongly encouraged)

There is no test suite yet. Tests in `tests/` using `pytest` with SQLite
in-memory fixtures are very welcome.

---

## Pull Request Process

1. Fork the repository and branch from `main`. Use descriptive names:
   `ind-XX-name`, `fix-sts-detection`, `docs-improve-readme`.
2. Run `ruff check .` and `ruff format .` — PRs with lint failures will not be
   reviewed.
3. Test locally. For a new indicator, verify the score appears correctly in
   `screen_vessel_detail()` output.
4. Open a PR against `main` and fill in the template.

**What makes a good PR:**
- Focused scope — one indicator or one bug fix per PR
- Real or synthetic data validation described in the PR body
- All thresholds in `risk_config.py`, all DB calls in `db.py`
- `docs/indicators.md` updated if an indicator status changed

---

## Issue Types

- **Bug report** — Something broken or producing wrong results
- **Feature request** — New capability not related to indicator framework
- **New indicator** — Proposal to implement a shadow fleet framework indicator

---

## Data and Privacy Notes

- Do not commit vessel data, AIS recordings, or database files. `.gitignore`
  excludes `*.db`, `*.db-shm`, `*.db-wal`, and `.env`.
- No API keys, passwords, or credentials in any tracked file.
- For new data sources, verify terms before ingesting. Open-source and public
  domain sources are preferred.
