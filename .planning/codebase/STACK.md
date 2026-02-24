# Technology Stack (STACK.md)

**Primary Language:** Python 3.11 (Core logic, Flask backend)
**Secondary Languages:** JavaScript (Frontend map logic in `static/map.js`), HTML (Jinja2 templates)
**Runtime:** Python 3.11.9, Flask 3.1.0, Gunicorn 22.0.0
**Frameworks:** Flask (Web), Pydantic (Data validation in `schemas.py`)

**Key Dependencies:**
- `requests`: External API consumption (OFAC, OpenSanctions, NOAA).
- `websockets`: Real-time AIS data streaming from `aisstream.io`.
- `psycopg2-binary`: PostgreSQL database support.
- `anthropic`: Anthropic Claude API integration (dependency present).
- `lxml`: XML parsing for OFAC SDN lists.

**Configuration:** Environment-based via `python-dotenv`. Key vars: `DATABASE_URL`, `AISSTREAM_API_KEY`, `APP_PASSWORD`, `SECRET_KEY`.
