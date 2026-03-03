"""
Data ingestion for Maritime OSINT platform.

Session 1 sources:
  - OFAC SDN XML   (U.S. Treasury, free, no auth)
  - OpenSanctions  (CC BY-SA 4.0, free bulk download)
"""

import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from io import StringIO
from typing import Generator

import requests

import schemas

logger = logging.getLogger(__name__)

OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
OPENSANCTIONS_URL = (
    "https://data.opensanctions.org/datasets/latest/sanctions/entities.ftm.json"
)

# OFAC SDN XML uses this default namespace on all elements
OFAC_NS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"


# ── Helpers ────────────────────────────────────────────────────────────────

def _t(el, tag):
    """First child with OFAC namespace."""
    return el.find(f"{{{OFAC_NS}}}{tag}")


def _txt(el, tag, default: str = "") -> str:
    child = _t(el, tag)
    return (child.text or "").strip() if child is not None else default


def _clean_imo(raw: str | None) -> str | None:
    """Extract 7-digit IMO number, return None if not valid."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 7 else None


def _clean_mmsi(raw: str | None) -> str | None:
    """Extract 9-digit MMSI, return None if not valid."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 9 else None


# ── OFAC SDN ──────────────────────────────────────────────────────────────

def fetch_ofac_sdn(vessel_only: bool = True) -> list[dict]:
    """
    Download and parse the OFAC Specially Designated Nationals XML list.

    By default (vessel_only=True) returns only entries where sdnType='Vessel'
    or a <vesselInfo> element is present.  Set vessel_only=False to return all
    ~18,000 SDN entries (useful for owner/company cross-referencing later).
    """
    logger.info("Fetching OFAC SDN XML from %s", OFAC_SDN_URL)
    resp = requests.get(OFAC_SDN_URL, timeout=90)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    entries = []

    for sdn_entry in root.findall(f"{{{OFAC_NS}}}sdnEntry"):
        sdn_type = _txt(sdn_entry, "sdnType")
        vessel_info_el = _t(sdn_entry, "vesselInfo")

        if vessel_only and sdn_type != "Vessel" and vessel_info_el is None:
            continue

        uid = _txt(sdn_entry, "uid")
        # Vessel primary name is in <lastName>; persons use both
        name = _txt(sdn_entry, "lastName") or _txt(sdn_entry, "firstName")

        # Sanctions programs
        prog_el = _t(sdn_entry, "programList")
        programs: list[str] = []
        if prog_el is not None:
            for prog in prog_el.findall(f"{{{OFAC_NS}}}program"):
                if prog.text:
                    programs.append(prog.text.strip())

        # Aliases
        aka_el = _t(sdn_entry, "akaList")
        aliases: list[str] = []
        if aka_el is not None:
            for aka in aka_el.findall(f"{{{OFAC_NS}}}aka"):
                aka_name = _txt(aka, "lastName") or _txt(aka, "firstName")
                if aka_name and aka_name != name:
                    aliases.append(aka_name)

        # Identifiers (IMO, MMSI, Call Sign, etc.)
        id_el = _t(sdn_entry, "idList")
        imo_number = None
        mmsi = None
        identifiers: dict = {}
        if id_el is not None:
            for id_item in id_el.findall(f"{{{OFAC_NS}}}id"):
                id_type = _txt(id_item, "idType")
                id_number = _txt(id_item, "idNumber")
                if id_type == "IMO Number":
                    imo_number = _clean_imo(id_number)
                elif id_type in ("MMSI", "Maritime Mobile Service Identities (MMSI)"):
                    mmsi = _clean_mmsi(id_number)
                elif id_type and id_number:
                    identifiers[id_type] = id_number

        # Vessel-specific attributes
        call_sign = None
        vessel_type = None
        flag_state = None
        owner_operator = None
        gross_tonnage = None
        if vessel_info_el is not None:
            call_sign = _txt(vessel_info_el, "callSign") or None
            vessel_type = _txt(vessel_info_el, "vesselType") or None
            flag_state = _txt(vessel_info_el, "vesselFlag") or None
            owner_operator = _txt(vessel_info_el, "vesselOwnerOperator") or None
            gt_raw = (
                _txt(vessel_info_el, "grossRegisteredTonnage")
                or _txt(vessel_info_el, "tonnage")
            )
            if gt_raw:
                try:
                    gross_tonnage = int(re.sub(r"\D", "", gt_raw))
                except ValueError:
                    pass

        # Structured ownership entry — also keep in identifiers for backward compat
        ofac_ownership: list[dict] = []
        if owner_operator:
            identifiers["owner_operator"] = owner_operator
            ofac_ownership.append({
                "role": "owner",
                "entity_name": owner_operator,
                "source": "OFAC_SDN",
            })

        try:
            entry = schemas.SanctionsEntry(
                list_name="OFAC_SDN",
                source_id=uid,
                entity_name=name,
                entity_type="Vessel" if sdn_type == "Vessel" else sdn_type,
                imo_number=imo_number,
                mmsi=mmsi,
                vessel_type=vessel_type,
                flag_state=flag_state,
                call_sign=call_sign,
                program=", ".join(programs),
                gross_tonnage=gross_tonnage,
                aliases=aliases,
                identifiers=identifiers,
                ownership_entries=ofac_ownership,
            )
            entries.append(entry.model_dump())
        except Exception as e:
            logger.debug("Validation failed for OFAC entry %s: %s", uid, e)

    logger.info("Parsed %d OFAC SDN vessel entries", len(entries))
    return entries


# ── OpenSanctions ──────────────────────────────────────────────────────────

def _iter_opensanctions_lines(url: str) -> Generator[dict, None, None]:
    """Stream FtM JSON Lines from OpenSanctions, yielding one dict per line."""
    with requests.get(url, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            try:
                yield json.loads(raw_line)
            except json.JSONDecodeError:
                continue


def fetch_opensanctions_vessels() -> list[dict]:
    """
    Stream the OpenSanctions consolidated sanctions dataset and return
    all entities with schema='Vessel'.

    The FtM (FollowTheMoney) format has:
      {"id": "...", "schema": "Vessel", "caption": "...",
       "properties": {"name": [...], "imoNumber": [...], ...}}

    All property values are arrays.
    """
    logger.info("Streaming OpenSanctions vessels from %s", OPENSANCTIONS_URL)
    entries: list[dict] = []
    total_lines = 0

    for obj in _iter_opensanctions_lines(OPENSANCTIONS_URL):
        total_lines += 1
        if obj.get("schema") != "Vessel":
            continue

        props = obj.get("properties", {})

        def first(key, default=None):
            vals = props.get(key, [])
            return vals[0] if vals else default

        name = first("name") or obj.get("caption", "")
        imo_number = _clean_imo(first("imoNumber") or first("registrationNumber"))
        mmsi = _clean_mmsi(first("mmsi"))
        flag_raw = first("flag")
        vessel_type = first("type") or first("buildMaterial")
        call_sign = first("callSign")
        # Full dataset list — used by normalize.parse_source_tags to build source_tags
        datasets: list = props.get("dataset", [])
        programs = props.get("program", datasets)
        # Name list: first is primary, rest are aliases
        all_names = props.get("name", [])
        primary = all_names[0] if all_names else name
        aliases = list({n for n in all_names[1:] + props.get("alias", []) if n != primary})

        # ── Ownership opacity fields ──────────────────────────────────────
        build_year_raw = first("buildDate")   # e.g. "1998" or "1998-01-01"
        build_year: int | None = None
        if build_year_raw and build_year_raw[:4].isdigit():
            build_year = int(build_year_raw[:4])

        gross_tonnage_raw = first("grossTonnage")
        gross_tonnage: int | None = None
        if gross_tonnage_raw:
            digits = re.sub(r"\D", "", gross_tonnage_raw)
            gross_tonnage = int(digits) if digits else None

        past_flags: list[str] = props.get("pastFlags", [])

        ownership_entries: list[dict] = []
        for role, prop_key in [
            ("owner",         "owner"),
            ("operator",      "operator"),
            ("manager",       "manager"),
            ("past_owner",    "pastOwner"),
            ("past_operator", "pastOperator"),
            ("past_manager",  "pastManager"),
        ]:
            for name_val in props.get(prop_key, []):
                if name_val:
                    ownership_entries.append({
                        "role": role,
                        "entity_name": name_val,
                        "source": "OpenSanctions",
                    })

        try:
            entry = schemas.SanctionsEntry(
                list_name="OpenSanctions",
                source_id=obj["id"],
                entity_name=primary or name,
                entity_type="Vessel",
                imo_number=imo_number,
                mmsi=mmsi,
                vessel_type=vessel_type,
                flag_state=flag_raw,
                call_sign=call_sign,
                program=", ".join(programs[:5]),
                gross_tonnage=gross_tonnage,
                aliases=aliases[:15],
                identifiers={
                    "topics":   props.get("topics", []),
                    "datasets": datasets,
                },
                build_year=build_year,
                past_flags=past_flags,
                ownership_entries=ownership_entries,
            )
            entries.append(entry.model_dump())
        except Exception as e:
            logger.debug("Validation failed for OpenSanctions entry %s: %s", obj["id"], e)

    logger.info(
        "Scanned %d OpenSanctions entities, extracted %d vessels",
        total_lines, len(entries),
    )
    return entries


# ── PSC Detention Lists (IND31) ────────────────────────────────────────────

# Public CSV endpoints — update if the MOU changes their download URL.
# Paris MOU: monthly updated detention list (free, no auth)
# Tokyo MOU: equivalent Pacific-region list
PSC_SOURCES: dict[str, dict] = {
    "paris": {
        "url":       "https://www.parismou.org/sites/default/files/Paris%20MOU%20Detention%20List.csv",
        "authority": "Paris MOU",
    },
    "tokyo": {
        "url":       "https://www.tokyo-mou.org/doc/DetentionList.csv",
        "authority": "Tokyo MOU",
    },
}

# Expected CSV column name aliases (lower-cased, stripped) → canonical key
_PSC_COL_MAP: dict[str, str] = {
    # IMO
    "imo number": "imo", "imo no": "imo", "imo no.": "imo", "imo": "imo",
    # Vessel name
    "ship name": "vessel_name", "vessel name": "vessel_name", "name": "vessel_name",
    # Flag
    "flag": "flag_state", "flag state": "flag_state",
    # Dates
    "date detained":     "detention_date",
    "detention date":    "detention_date",
    "date of detention": "detention_date",
    "date released":     "release_date",
    "release date":      "release_date",
    "date released/still detained": "release_date",
    # Port
    "port":         "port_name",
    "port/state":   "port_name",
    "port of detention": "port_name",
    # Country
    "country":       "port_country",
    "port country":  "port_country",
    # Deficiencies
    "no. of deficiencies": "deficiency_count",
    "deficiencies":        "deficiency_count",
    "number of deficiencies": "deficiency_count",
    "no of deficiencies":     "deficiency_count",
}

# Date formats tried in order when parsing PSC CSV date fields
_PSC_DATE_FMTS = ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%B %d, %Y")


def _parse_psc_date(raw: str | None) -> str | None:
    """Parse a PSC CSV date string to ISO YYYY-MM-DD, or None if unparseable."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in _PSC_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_psc_int(raw: str | None) -> int | None:
    """Return integer value of a PSC field, or None."""
    if not raw:
        return None
    try:
        return int(str(raw).strip().split()[0])  # handle "5 (2 class)" etc.
    except (ValueError, IndexError):
        return None


def fetch_psc_detentions(source: str = "paris") -> list[dict]:
    """
    Download and parse a Paris MOU or Tokyo MOU PSC detention list CSV.

    source: "paris" or "tokyo"

    Returns a list of dicts suitable for db.upsert_psc_detentions():
      imo_number, vessel_name, flag_state, detention_date, release_date,
      port_name, port_country, authority, deficiency_count, list_source

    CSV column names are normalised so minor formatting variations are handled.
    Rows without a valid 7-digit IMO number are silently skipped.

    The Paris MOU URL is public and requires no authentication:
      https://www.parismou.org/sites/default/files/Paris%20MOU%20Detention%20List.csv
    Update PSC_SOURCES if the download URL changes.
    """
    cfg = PSC_SOURCES.get(source)
    if not cfg:
        raise ValueError(f"Unknown PSC source '{source}'. Choose 'paris' or 'tokyo'.")

    url       = cfg["url"]
    authority = cfg["authority"]
    logger.info("Downloading PSC detention list from %s", url)

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # Detect encoding — Paris MOU often uses latin-1
    encoding = resp.encoding or "utf-8"
    try:
        text = resp.content.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = resp.content.decode("latin-1", errors="replace")

    reader  = csv.DictReader(StringIO(text))
    records = []

    for row in reader:
        # Normalise all column names
        norm: dict[str, str] = {}
        for k, v in row.items():
            if k:
                mapped = _PSC_COL_MAP.get(k.lower().strip())
                if mapped:
                    norm[mapped] = (v or "").strip()

        # Require a valid 7-digit IMO
        imo_raw = norm.get("imo", "")
        imo     = re.sub(r"\D", "", imo_raw)
        if len(imo) != 7:
            continue

        records.append({
            "imo_number":       imo,
            "vessel_name":      norm.get("vessel_name"),
            "flag_state":       norm.get("flag_state"),
            "detention_date":   _parse_psc_date(norm.get("detention_date")),
            "release_date":     _parse_psc_date(norm.get("release_date")),
            "port_name":        norm.get("port_name"),
            "port_country":     norm.get("port_country"),
            "authority":        authority,
            "deficiency_count": _parse_psc_int(norm.get("deficiency_count")),
            "list_source":      source,
        })

    logger.info("Parsed %d PSC detention records from %s", len(records), authority)
    return records
