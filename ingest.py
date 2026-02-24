"""
Data ingestion for Maritime OSINT platform.

Session 1 sources:
  - OFAC SDN XML   (U.S. Treasury, free, no auth)
  - OpenSanctions  (CC BY-SA 4.0, free bulk download)
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Generator

import requests

import normalize

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

        if owner_operator:
            identifiers["owner_operator"] = owner_operator

        entries.append({
            "source_id":    uid,
            "entity_type":  "Vessel" if sdn_type == "Vessel" else sdn_type,
            "entity_name":  name,
            "imo_number":   imo_number,
            "mmsi":         mmsi,
            "vessel_type":  vessel_type,
            "flag_state":   flag_state,
            "call_sign":    call_sign,
            "program":      ", ".join(programs),
            "gross_tonnage": gross_tonnage,
            "aliases":      aliases,
            "identifiers":  identifiers,
        })

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

        entries.append({
            "source_id":    obj["id"],
            "entity_type":  "Vessel",
            "entity_name":  primary or name,
            "imo_number":   imo_number,
            "mmsi":         mmsi,
            "vessel_type":  vessel_type,
            "flag_state":   flag_raw,
            "call_sign":    call_sign,
            "program":      ", ".join(programs[:5]),
            "gross_tonnage": None,
            "aliases":      aliases[:15],
            "identifiers":  {
                "topics":   props.get("topics", []),
                "datasets": datasets,          # full list, no truncation
            },
        })

    logger.info(
        "Scanned %d OpenSanctions entities, extracted %d vessels",
        total_lines, len(entries),
    )
    return entries
