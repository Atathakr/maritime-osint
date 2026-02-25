# maritime-osint

*Global Maritime Intelligence & AIS Analysis Platform*

---

## Vision
A unified platform for detecting illicit maritime activity, including sanctions evasion, Ship-to-Ship (STS) transfers, dark periods, and AIS spoofing.

## Project State
- **Status:** Active / Brownfield
- **Tech Stack:** Python 3.11, Flask, PostgreSQL/SQLite, WebSockets, Pydantic.
- **Key Integrations:** aisstream.io, OFAC SDN, OpenSanctions, NOAA.

## Milestone History

### [M1] AIS Spoof Detector (Current)
- **Goal:** Identify vessels broadcasting implausible or manipulated AIS data.
- **Signals:** Teleportation (speed), Overland track (location), MMSI/IMO identity mismatch.
- **Started:** 2026-02-24

---

## Architectural Principles
- **Surgical Updates:** Minimize disruption to existing `db.py` and `app.py` logic.
- **Service Isolation:** Logic resides in dedicated modules (e.g., `spoof_detector.py`).
- **Data Integrity:** Strict validation of AIS data via Pydantic schemas.
- **Real-time & Batch:** Support for both real-time stream analysis and historical batch processing.

---

## Business Context
Used by OSINT researchers and compliance officers to flag high-risk vessel behavior for manual review.
