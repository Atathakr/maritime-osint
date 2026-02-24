# External Integrations (INTEGRATIONS.md)

**APIs & Services:**
- **aisstream.io:** WebSocket stream for global AIS position data.
- **OFAC SDN:** U.S. Treasury sanctions list (XML source).
- **OpenSanctions:** Consolidated sanctions data (JSON Lines source).
- **NOAA Marine Cadastre:** Monthly AIS CSV data ingestion.
- **Anthropic:** AI-powered analysis (SDK: `anthropic`).

**Data Storage:**
- **Databases:** Supports PostgreSQL (Production) and SQLite (Local/Dev) via `db.py`.

**Authentication:**
- **Custom:** Simple password-based session authentication (`APP_PASSWORD`).

**Deployment:**
- **Hosting:** Railway (via `railway.toml` and `Procfile`).
