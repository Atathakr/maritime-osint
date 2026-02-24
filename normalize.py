"""
normalize.py — data normalisation helpers for Maritime OSINT Platform.

Covers:
  • Flag state: ISO 3166-1 alpha-2 → full country name (and pass-through for
    values that are already full names)
  • OpenSanctions dataset codes → short display labels
  • Canonical vessel ID generation (IMO > MMSI > hash fallback)
"""

import hashlib
import json

# ── ISO 3166-1 alpha-2 → full country name ────────────────────────────────
# Focused on shadow-fleet flag states and sanctioned / high-risk states.

_FLAG_MAP: dict[str, str] = {
    # Sanctioned / high-risk states
    "ir": "Iran",
    "ru": "Russia",
    "kp": "North Korea",
    "sy": "Syria",
    "ve": "Venezuela",
    "cu": "Cuba",
    "by": "Belarus",
    "mm": "Myanmar",
    "sd": "Sudan",
    "ly": "Libya",
    "so": "Somalia",
    "ye": "Yemen",
    "iq": "Iraq",
    # Common shadow-fleet open registries
    "pa": "Panama",
    "lr": "Liberia",
    "mh": "Marshall Islands",
    "bz": "Belize",
    "vc": "Saint Vincent and the Grenadines",
    "vg": "British Virgin Islands",
    "km": "Comoros",
    "pw": "Palau",
    "tg": "Togo",
    "bb": "Barbados",
    "ag": "Antigua and Barbuda",
    "kn": "Saint Kitts and Nevis",
    "mv": "Maldives",
    "ga": "Gabon",
    "gq": "Equatorial Guinea",
    "ci": "Côte d'Ivoire",
    "tz": "Tanzania",
    "sc": "Seychelles",
    "mg": "Madagascar",
    "dj": "Djibouti",
    "cv": "Cabo Verde",
    "bn": "Brunei",
    "pf": "French Polynesia",
    # Middle East / Gulf
    "ae": "United Arab Emirates",
    "om": "Oman",
    "sa": "Saudi Arabia",
    "kw": "Kuwait",
    "bh": "Bahrain",
    "qa": "Qatar",
    # Asia-Pacific
    "cn": "China",
    "in": "India",
    "id": "Indonesia",
    "my": "Malaysia",
    "sg": "Singapore",
    "th": "Thailand",
    "pk": "Pakistan",
    "ph": "Philippines",
    "kr": "South Korea",
    "jp": "Japan",
    "vn": "Vietnam",
    "bd": "Bangladesh",
    # Europe
    "gr": "Greece",
    "cy": "Cyprus",
    "mt": "Malta",
    "gb": "United Kingdom",
    "de": "Germany",
    "no": "Norway",
    "dk": "Denmark",
    "nl": "Netherlands",
    "it": "Italy",
    "fr": "France",
    "tr": "Turkey",
    "ua": "Ukraine",
    "az": "Azerbaijan",
    "ge": "Georgia",
    "es": "Spain",
    "pt": "Portugal",
    "pl": "Poland",
    "hr": "Croatia",
    # Americas
    "us": "United States",
    "bs": "Bahamas",
    "tt": "Trinidad and Tobago",
    "hn": "Honduras",
    "gt": "Guatemala",
    "ec": "Ecuador",
    "co": "Colombia",
    "mx": "Mexico",
    "br": "Brazil",
    "bm": "Bermuda",
    "ky": "Cayman Islands",
    # Africa
    "ng": "Nigeria",
    "za": "South Africa",
    "eg": "Egypt",
    "ma": "Morocco",
    "gh": "Ghana",
    "cm": "Cameroon",
    "ao": "Angola",
}

# ── OpenSanctions dataset code → short display label ──────────────────────
# Derived from OpenSanctions' published dataset taxonomy.
# Codes are stored in FtM entities' properties.dataset[] array.

_DATASET_LABELS: dict[str, str] = {
    "us_ofac_sdn":              "OFAC SDN",
    "us_ofac_cons":             "OFAC CONS",
    "eu_consolidated":          "EU",
    "eu_eeas_sanctions":        "EU",
    "eu_fco_sanctions":         "EU",
    "un_sc_sanctions":          "UN SC",
    "gb_hmt_sanctions":         "UK HMT",
    "gb_ofsi_body":             "UK OFSI",
    "ch_seco_sanctions":        "Switzerland",
    "au_dfat_sanctions":        "Australia",
    "ca_osfi_sanctions":        "Canada",
    "jp_meti_sanctions":        "Japan",
    "jp_mof_sanctions":         "Japan",
    "ua_sfms_blacklist":        "Ukraine",
    "fr_tresor_gels_avoir":     "France",
    "be_fod_sanctions":         "Belgium",
    "nl_fm_sanctions":          "Netherlands",
    "pl_mswia_sanctions":       "Poland",
    "interpol_red_notices":     "Interpol",
    "worldbank_debarred":       "World Bank",
    "opensanctions":            "OpenSanctions",
    "sanctions":                "OpenSanctions",
}


# ── Public helpers ─────────────────────────────────────────────────────────

def normalize_flag(flag_raw: str | None) -> str | None:
    """
    Normalise a flag state value to a full English country name.
    • 2-letter ISO codes  → look up in _FLAG_MAP (uppercase if unknown)
    • Anything longer     → return as-is (already a full name)
    • None / empty        → None
    """
    if not flag_raw:
        return None
    flag = flag_raw.strip()
    if len(flag) <= 2:
        return _FLAG_MAP.get(flag.lower(), flag.upper())
    return flag


def dataset_label(code: str) -> str:
    """Map a single OpenSanctions dataset code to a short display label."""
    return _DATASET_LABELS.get(code.lower(), code)


def parse_source_tags(list_name: str, identifiers: dict | str | None) -> list[str]:
    """
    Build the ordered, de-duplicated source-tag list for a sanctions entry.

    • OFAC_SDN entries       → ["OFAC SDN"]
    • OpenSanctions entries  → derived from identifiers["datasets"],
                               falling back to ["OpenSanctions"] if empty.
    """
    if list_name == "OFAC_SDN":
        return ["OFAC SDN"]

    # Tolerate raw JSON strings (SQLite storage)
    if isinstance(identifiers, str):
        try:
            identifiers = json.loads(identifiers)
        except Exception:
            identifiers = {}

    if not identifiers:
        return ["OpenSanctions"]

    raw_datasets: list = identifiers.get("datasets") or []
    if isinstance(raw_datasets, str):
        try:
            raw_datasets = json.loads(raw_datasets)
        except Exception:
            raw_datasets = []

    tags: list[str] = []
    for ds in raw_datasets:
        label = dataset_label(str(ds))
        if label not in tags:
            tags.append(label)

    return tags if tags else ["OpenSanctions"]


def make_canonical_id(
    imo: str | None,
    mmsi: str | None,
    name: str,
    flag: str | None,
) -> tuple[str, str]:
    """
    Compute a stable canonical vessel identifier and the match method used.

    Priority:
      1. IMO number   → "IMO:{imo}"    match_method = "imo_exact"
      2. MMSI number  → "MMSI:{mmsi}"  match_method = "mmsi_exact"
      3. Hash(name+flag) → "HASH:{12-char hex}"  match_method = "single_source"

    Returns (canonical_id, match_method).
    """
    if imo:
        return f"IMO:{imo}", "imo_exact"
    if mmsi:
        return f"MMSI:{mmsi}", "mmsi_exact"
    key = f"{name.lower().strip()}|{(flag or '').lower().strip()}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"HASH:{digest}", "single_source"
