# Maritime OSINT — Sanctions & Shadow Fleet Intelligence

> An open-source web platform for maritime threat intelligence. Screen vessels
> against OFAC SDN and OpenSanctions lists, track real-time AIS positions, and
> score vessels against a 31-indicator behavioral framework for shadow fleet
> detection.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.1-lightgrey)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active%20development-orange)

---

## What This Is

The shadow fleet — vessels deliberately obscuring their identity, ownership, or
movements to evade sanctions — has grown substantially since 2022. Most
open-source tools address either sanctions screening or AIS tracking in
isolation. This platform combines both into a single analyst-facing interface.

You load a vessel identifier (IMO number, MMSI, or name), and the platform
returns:

- Whether the vessel appears on OFAC SDN, OpenSanctions, EU, UN, or other lists
- A composite risk score (0–100) derived from 13 behavioral and structural indicators
- AIS behavioral signals: dark periods, ship-to-ship transfers, loitering, speed anomalies
- Port call history against ~30 sanctioned or high-risk terminals
- Flag state risk tier and flag-hopping history
- PSC detention record (Paris MOU + Tokyo MOU)
- Ownership chain screening against the sanctions database

This is a research and triage tool. It is not a substitute for professional
compliance analysis. All signals should be interpreted by a qualified analyst.

---

## Features

### Sanctions Screening

| Capability | Detail |
|---|---|
| OFAC SDN | U.S. Treasury Specially Designated Nationals, vessel entries |
| OpenSanctions | Consolidated multi-jurisdiction list: EU, UN SC, UK HMT, Australia, Canada, Japan, and others |
| Unified canonical registry | Deduplicates vessels across lists using IMO > MMSI > name+flag hash priority |
| Post-ingest reconciliation | Two-tier merge: IMO collision sweep + MMSI-to-IMO upgrade |
| Search | IMO number, MMSI, or partial vessel name with match confidence labels |

### Real-Time AIS Tracking

| Capability | Detail |
|---|---|
| Live feed | WebSocket connection to aisstream.io (free tier supported) |
| Historical data | NOAA Marine Cadastre monthly AIS CSV ingest |
| Vessel roster | One row per MMSI with last known position |
| Track history | 72-hour breadcrumb trail per vessel (configurable up to 168 h) |
| Live map | Leaflet 1.9.4, composite risk colouring, vessel tracks |

### Behavioral Analytics — Shadow Fleet Framework

The platform implements a subset of a 31-indicator behavioral framework for
shadow fleet risk assessment. Indicators are grouped into six categories.

| Status | Count |
|---|---|
| Fully implemented and scored | 13 |
| Partial (detected, not fully scored) | 1 |
| Not yet implemented | 10 |
| Not feasible with open-source data | 7 |

**Implemented indicators:**

| Code | Name | Category |
|---|---|---|
| IND1 | AIS dark periods (transponder gaps ≥ 2 h) | AIS / Transponder |
| IND2 | Speed anomalies / AIS spoofing proxy (SOG > 50 kt) | AIS / Transponder |
| IND7 | Ship-to-ship transfers in open ocean | Movement / Behavioral |
| IND8 | STS transfers in 9 named high-risk zones | Movement / Behavioral |
| IND9 | Loitering / unusual open-water anchoring | Movement / Behavioral |
| IND10 | Abnormal speed profiles | Movement / Behavioral |
| IND15 | Flag hopping (multiple flag changes) | Ownership / Identity |
| IND16 | Vessel name discrepancy (AIS vs canonical) | Ownership / Identity |
| IND17 | High-risk / flag-of-convenience flag state | Ownership / Identity |
| IND21 | Ownership chain sanctions match | Ownership / Identity |
| IND23 | Vessel age (≥ 15 years elevated risk) | Physical / Operational |
| IND29 | Port calls to sanctioned / high-risk ports | Port / Geographic |
| IND31 | PSC detention record (Paris MOU / Tokyo MOU) | Port / Geographic |

### Risk Scoring

Non-sanctioned vessels receive a composite score from 0 to 99. Vessels on any
sanctions list always receive a score of 100.

```
risk_score = min(
    min(dp_count × 10, 40)          -- IND1  AIS dark periods
  + min(sts_count × 15, 45)         -- IND7  STS transfers
  + min(sts_zone_count × 5, 10)     -- IND8  STS in high-risk zones
  + flag_tier × 7                   -- IND17 flag risk tier (max 21)
  + min(hop_count × 8, 16)          -- IND15 flag hopping
  + min(spoof_count × 8, 24)        -- IND10 speed anomalies
  + min(port_count × 20, 40)        -- IND29 sanctioned port calls
  + min(loiter_count × 5, 15)       -- IND9  loitering
  + max(0, min((age − 15) × 3, 15)) -- IND23 vessel age
  + min(owner_hits × 20, 40)        -- IND21 ownership chain
  + min(psc_count × 10, 20),        -- IND31 PSC detentions
  99                                -- hard ceiling for non-sanctioned
)
```

**Flag risk tiers (IND17):**

| Tier | Score | Examples |
|---|---|---|
| 3 — High-risk / sanctioned | 21 pts | Iran, Russia, North Korea, Syria, Cameroon, Tanzania, Comoros |
| 2 — Shadow fleet registries | 14 pts | Panama, Palau, Togo, Gabon, Cambodia, Sierra Leone |
| 1 — Mainstream open registries | 7 pts | Marshall Islands, Liberia, Bahamas, Belize |
| 0 — Standard | 0 pts | EU member states, UK, USA, Norway, Japan, etc. |

---

## Data Sources

| Source | Type | License / Terms | URL |
|---|---|---|---|
| OFAC SDN | Sanctions list (XML) | U.S. public domain | https://www.treasury.gov/ofac/downloads/sdn.xml |
| OpenSanctions | Consolidated sanctions (JSON) | CC BY-SA 4.0 | https://opensanctions.org |
| aisstream.io | Real-time AIS (WebSocket) | Free tier available | https://aisstream.io |
| NOAA Marine Cadastre | Historical AIS (CSV) | U.S. public domain | https://marinecadastre.gov |
| Paris MOU | PSC detentions (CSV) | Public | https://www.parismou.org |
| Tokyo MOU | PSC detentions (CSV) | Public | https://www.tokyo-mou.org |

All data sources are publicly available. No commercial subscriptions are required.

---

## Quick Start (Local)

**Requirements:** Python 3.11 or later, Git

```bash
git clone https://github.com/Atathakr/maritime-osint.git
cd maritime-osint

python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — all fields optional for local dev
# Add AISSTREAM_API_KEY for real-time AIS (free at aisstream.io)

python app.py
```

Open http://localhost:5000.

**Initial data load (in the browser):**

1. Click **Fetch OFAC** — downloads and parses the OFAC SDN XML (~5–15 s)
2. Click **Fetch OpenSanctions** — streams the consolidated JSON (~30–90 s)
3. Click **Reconcile** — merges duplicate vessel records
4. Optional: click **Start AIS** for the live feed (requires API key)

After steps 1–3, sanctions screening is fully functional. AIS behavioral
analytics activate once position data is flowing.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | No | PostgreSQL connection string. Omit to use SQLite. |
| `APP_PASSWORD` | No | Password for the dashboard login page. Leave blank to disable auth. |
| `SECRET_KEY` | No | Flask session key. Auto-generated at startup if not set. |
| `AISSTREAM_API_KEY` | No | API key for aisstream.io. Free registration at aisstream.io. |

---

## Deployment (Railway)

1. Fork the repository.
2. Create a Railway project and connect your fork.
3. Add the **PostgreSQL plugin** — Railway sets `DATABASE_URL` automatically.
4. Set `APP_PASSWORD` and `AISSTREAM_API_KEY` in Railway environment variables.
5. Deploy. The `/health` endpoint confirms readiness.

The 120-second Gunicorn timeout in the `Procfile` is required for the
OpenSanctions streaming ingest.

**Self-hosted:** Any platform that runs Python with Gunicorn works. Set
`DATABASE_URL` for PostgreSQL in production, or leave unset for SQLite.

---

## Architecture Overview

```
app.py                  Flask routes and auth middleware
├── ingest.py           OFAC SDN + OpenSanctions + PSC CSV ingest
├── screening.py        Unified vessel search and risk scoring engine
├── reconcile.py        Two-tier canonical vessel deduplication
├── db.py               Database abstraction layer (SQLite / PostgreSQL)
├── ais_listener.py     aisstream.io WebSocket consumer (background thread)
├── dark_periods.py     IND1 — AIS transponder gap detector
├── sts_detection.py    IND7/8 — ship-to-ship proximity detector
├── loitering.py        IND9 — open-water loitering detector
├── spoofing.py         IND10 — speed anomaly detector
├── ports.py            IND29 — sanctioned port call detector
├── noaa_ingest.py      Historical AIS CSV ingest (NOAA Marine Cadastre)
├── normalize.py        Flag normalisation, dataset labels, canonical IDs
├── risk_config.py      Scoring weights, thresholds, flag tier registry
├── schemas.py          Pydantic data models for all request/response types
└── map_data.py         Geospatial data preparation for Leaflet frontend
```

---

## API Reference (Selected Endpoints)

All endpoints require authentication if `APP_PASSWORD` is set.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/screen` | Screen vessel by IMO, MMSI, or name |
| GET | `/api/screen/<imo>` | Full risk profile for a specific vessel |
| GET | `/api/sanctions` | Browse sanctions entries with filtering |
| POST | `/api/ingest/ofac` | Trigger OFAC SDN ingest |
| POST | `/api/ingest/opensanctions` | Trigger OpenSanctions ingest |
| POST | `/api/ingest/psc/<paris\|tokyo>` | Ingest PSC detention CSV |
| POST | `/api/reconcile` | Run canonical deduplication |
| POST | `/api/ais/start` | Start AIS WebSocket listener |
| GET | `/api/ais/status` | AIS listener statistics |
| GET | `/api/ais/vessels` | AIS vessel roster |
| GET | `/api/ais/vessels/<mmsi>/track` | Historical vessel track |
| POST | `/api/dark-periods/detect` | Run dark period detection |
| POST | `/api/sts/detect` | Run STS proximity detection |
| POST | `/api/ais/detect-loitering` | Run loitering detection |
| POST | `/api/ports/detect-calls` | Run sanctioned port call detection |
| POST | `/api/ais/detect-anomalies` | Run speed anomaly detection |
| GET | `/api/map/vessels` | Vessel positions + composite risk for map |

Full request/response schemas are in `schemas.py`.

---

## Limitations

Seven of the 31 shadow fleet indicators require commercial data:

| Indicator | Why not feasible |
|---|---|
| IND5 — Disabled LRIT | Requires LRIT receiver network subscription |
| IND13 — Voyage vs cargo inconsistency | Requires cargo manifest / Bill of Lading |
| IND14 — VHF communication silence | Requires coastal radio monitoring |
| IND22 — Fraudulent documents | Requires document authentication access |
| IND24 — Physical modifications | Requires satellite imagery |
| IND25 — Draught anomalies | AIS draught is self-reported, not enforced |
| IND28 — Cargo inconsistencies | Requires customs / BoL data |

The speed anomaly detector (IND10) is a spoofing *proxy* — SOG > 50 knots is
a conservative threshold. True GNSS spoofing detection requires cross-reference
with satellite receivers.

AIS coverage gaps (not deliberate blackouts) exist in regions with limited
terrestrial receiver density.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and
how to add new indicators to the framework.

---

## Security

See [SECURITY.md](SECURITY.md) for the vulnerability reporting policy.

---

## License

This project is licensed under the [MIT License](LICENSE).

Data licenses apply separately:
- OpenSanctions data: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- OFAC SDN and NOAA AIS data: U.S. government public domain
