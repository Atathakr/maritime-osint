"""
NOAA Marine Cadastre AIS bulk ingest — historical baseline data.

Downloads a monthly AIS CSV file (zipped) from NOAA's Marine Cadastre,
streams and decompresses it in memory, filters to tanker vessel types,
and batch-inserts into ais_positions.

Data URL pattern:
  https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/AIS_{year}_{month:02d}_Zone{zone:02d}.zip

Zones: 01–17 cover US coastal waters.
Recommended starting zone: Zone 10 (Gulf of Mexico) — rich tanker traffic
  and a known transit corridor for shadow fleet movements.

File sizes: 200 MB – 1 GB zipped; expect 5–15 min download on a typical link.
This ingest runs synchronously inside a Flask request — the gunicorn timeout
is 120 s which is sufficient for a single zone file over a fast connection.
For large files, call from a background thread or increase the timeout.

CSV columns (NOAA AIS 2015+):
  MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading,
  VesselName, IMO, CallSign, VesselType, Status,
  Length, Width, Draft, Cargo, TransceiverClass
"""

import csv
import io
import logging
import re
import zipfile
from datetime import UTC, datetime

import requests

import db

logger = logging.getLogger(__name__)

NOAA_BASE = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler"

# AIS tanker type codes (same as live feed)
TANKER_TYPES = set(range(80, 90))

# Batch size for DB inserts
BATCH_SIZE = 500


def build_url(year: int, month: int, zone: int) -> str:
    return f"{NOAA_BASE}/{year}/AIS_{year}_{month:02d}_Zone{zone:02d}.zip"


def fetch_and_ingest(year: int, month: int, zone: int,
                     all_vessel_types: bool = False) -> dict:
    """
    Download, unzip, parse and insert a NOAA AIS monthly zone file.

    Args:
        year, month, zone: Identify the dataset file.
        all_vessel_types:  If True, ingest all vessel types (not just tankers).
                           Warning: produces very large datasets.

    Returns dict with: url, rows_read, rows_inserted, errors.
    """
    url = build_url(year, month, zone)
    logger.info("NOAA ingest: downloading %s", url)

    stats = {"url": url, "rows_read": 0, "rows_inserted": 0, "errors": 0}

    try:
        resp = requests.get(url, timeout=300, stream=True)
        resp.raise_for_status()
    except Exception as e:
        stats["error"] = str(e)
        return stats

    # Buffer the entire zip into memory (streaming decompression)
    logger.info("NOAA: downloading zip content…")
    zip_bytes = io.BytesIO(resp.content)

    try:
        with zipfile.ZipFile(zip_bytes) as zf:
            # There should be one CSV inside the zip
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                stats["error"] = "No CSV found in zip"
                return stats

            csv_name = csv_names[0]
            logger.info("NOAA: parsing %s", csv_name)

            with zf.open(csv_name) as raw_csv:
                reader = csv.DictReader(io.TextIOWrapper(raw_csv, encoding="utf-8"))
                batch: list[dict] = []

                for row in reader:
                    stats["rows_read"] += 1
                    try:
                        vessel_type = _safe_int(row.get("VesselType"))
                        if not all_vessel_types and vessel_type not in TANKER_TYPES:
                            continue

                        lat = _safe_float(row.get("LAT"))
                        lon = _safe_float(row.get("LON"))
                        if lat is None or lon is None:
                            continue
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            continue

                        mmsi = str(row.get("MMSI", "")).strip()
                        if not mmsi or len(mmsi) != 9:
                            continue

                        ts_raw = row.get("BaseDateTime", "")
                        try:
                            ts = datetime.strptime(ts_raw, "%Y-%m-%dT%H:%M:%S").replace(
                                tzinfo=UTC
                            )
                            position_ts = ts.isoformat()
                        except Exception:
                            continue

                        imo_raw = re.sub(r"\D", "", row.get("IMO", ""))
                        imo = imo_raw if len(imo_raw) == 7 else None

                        batch.append({
                            "mmsi":        mmsi,
                            "imo_number":  imo,
                            "vessel_name": row.get("VesselName", "").strip() or None,
                            "vessel_type": vessel_type,
                            "lat":         lat,
                            "lon":         lon,
                            "sog":         _safe_float(row.get("SOG")),
                            "cog":         _safe_float(row.get("COG")),
                            "heading":     _safe_int(row.get("Heading")),
                            "nav_status":  _safe_int(row.get("Status")),
                            "source":      "noaa",
                            "position_ts": position_ts,
                        })

                        if len(batch) >= BATCH_SIZE:
                            stats["rows_inserted"] += db.insert_ais_positions(batch)
                            batch = []

                    except Exception as e:
                        stats["errors"] += 1
                        logger.debug("Row parse error: %s", e)

                # Flush remainder
                if batch:
                    stats["rows_inserted"] += db.insert_ais_positions(batch)

    except zipfile.BadZipFile as e:
        stats["error"] = f"Bad zip file: {e}"
        return stats

    logger.info(
        "NOAA ingest complete: %d rows read, %d inserted, %d errors",
        stats["rows_read"], stats["rows_inserted"], stats["errors"],
    )
    return stats


# ── Helpers ───────────────────────────────────────────────────────────────

def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
