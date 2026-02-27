"""
Risk configuration — Shadow Fleet Framework indicator parameters.

Flag risk tiers are based on:
  - Paris MOU annual Black/Grey List (port state control deficiency rate)
  - OFAC/EU/UN sanctioned flag states
  - Shadow fleet registry usage patterns (Windward, C4ADS, EPRS research)

Tier 3 (21 pts): Paris MOU Black List + sanctioned registries
Tier 2 (14 pts): Open registries frequently used in shadow fleet operations
Tier 1  (7 pts): Mainstream open registries — common but not directly associated with evasion
Tier 0  (0 pts): All other flags (EU member states, UK, US, Japan, etc.)

ISO 3166-1 alpha-2 codes only.  Use get_flag_tier() which handles both ISO codes
and full English country names (as stored by normalize.normalize_flag()).
"""

FLAG_RISK_TIERS: dict[str, int] = {
    # ── Tier 3: Paris MOU Black List + sanctioned flag states ─────────────
    "CM": 3,   # Cameroon  — Paris MOU Black List (deficiency rate 6.56)
    "TZ": 3,   # Tanzania  — Paris MOU Black List (deficiency rate 5.88)
    "MD": 3,   # Moldova   — Paris MOU Black List (deficiency rate 4.81)
    "VN": 3,   # Vietnam   — Paris MOU Black List (deficiency rate 4.42)
    "KM": 3,   # Comoros   — Paris MOU Black List (deficiency rate 3.59)
    "KP": 3,   # DPRK (North Korea) — UN/OFAC/EU sanctioned
    "SY": 3,   # Syria     — OFAC/EU sanctioned
    "IR": 3,   # Iran      — OFAC/EU sanctioned
    "RU": 3,   # Russia    — OFAC/EU/UK sanctioned post-2022

    # ── Tier 2: Shadow fleet open registries ──────────────────────────────
    "PW": 2,   # Palau     — rapid shadow fleet expansion post-sanctions
    "TG": 2,   # Togo      — significant deficiency rate, shadow fleet hub
    "GA": 2,   # Gabon     — fleet expanded 1,038% in 12 months (EPRS 2024)
    "CK": 2,   # Cook Islands — open registry, limited oversight
    "SL": 2,   # Sierra Leone — Paris MOU Grey List
    "KH": 2,   # Cambodia  — open registry, frequent shadow fleet use
    "PA": 2,   # Panama    — largest open registry; frequently used in evasion despite some oversight
    "BI": 2,   # Burundi   — limited maritime oversight
    "CV": 2,   # Cabo Verde — Paris MOU Grey List
    "GN": 2,   # Guinea    — Paris MOU Black List (deficiency rate 3.0+)
    "ST": 2,   # São Tomé & Príncipe — shadow fleet registry
    "GQ": 2,   # Equatorial Guinea — limited enforcement capacity

    # ── Tier 1: Mainstream open registries ───────────────────────────────
    # Well-regulated but commonly used by shadow fleet as "clean" flags
    "MH": 1,   # Marshall Islands — large open registry, generally well-governed
    "LR": 1,   # Liberia   — large open registry, generally well-governed
    "BS": 1,   # Bahamas   — large open registry, IMO-compliant
    "BZ": 1,   # Belize    — open registry, some oversight gaps
    "AG": 1,   # Antigua & Barbuda — open registry
    "BB": 1,   # Barbados  — open registry
    "VC": 1,   # St. Vincent & Grenadines — open registry
    "KN": 1,   # St. Kitts & Nevis — open registry
}

# ── Speed anomaly detection ────────────────────────────────────────────────
# Merchant vessel maximum practical speed is ~25 knots.
# 50 knots represents an unambiguous physical impossibility for any surface vessel.
# This threshold is deliberately conservative to minimize false positives from
# terrestrial AIS data artifacts (late packet delivery, timing skew, etc.).
SPEED_ANOMALY_THRESHOLD_KT: float = 50.0

# ── Full country name → tier (for flag_normalized which stores full names) ─
_FLAG_RISK_TIERS_BY_NAME: dict[str, int] = {
    # Tier 3
    "cameroon": 3, "tanzania": 3, "moldova": 3, "vietnam": 3, "comoros": 3,
    "north korea": 3, "dprk": 3, "korea, democratic people's republic of": 3,
    "syria": 3, "iran": 3, "iran, islamic republic of": 3,
    "russia": 3, "russian federation": 3,
    # Tier 2
    "palau": 2, "togo": 2, "gabon": 2, "cook islands": 2, "sierra leone": 2,
    "cambodia": 2, "panama": 2, "burundi": 2, "cabo verde": 2, "cape verde": 2,
    "guinea": 2,
    "são tomé and príncipe": 2, "sao tome and principe": 2,
    "equatorial guinea": 2,
    # Tier 1
    "marshall islands": 1, "liberia": 1, "bahamas": 1, "belize": 1,
    "antigua and barbuda": 1, "barbados": 1,
    "saint vincent and the grenadines": 1, "st. vincent and the grenadines": 1,
    "saint kitts and nevis": 1, "st. kitts and nevis": 1,
}


def get_flag_tier(flag: str | None) -> int:
    """
    Return the risk tier for a flag value.
    Accepts ISO 3166-1 alpha-2 codes (e.g. 'IR') or full country names (e.g. 'Iran').
    Returns 0 for unknown/standard flags.
    """
    if not flag:
        return 0
    flag = flag.strip()
    # Try ISO code (2-letter, upper-case)
    tier = FLAG_RISK_TIERS.get(flag.upper())
    if tier is not None:
        return tier
    # Fall back to full-name lookup (lower-case)
    return _FLAG_RISK_TIERS_BY_NAME.get(flag.lower(), 0)


# ── Label strings for UI display ──────────────────────────────────────────
FLAG_TIER_LABELS: dict[int, str] = {
    0: "Standard registry",
    1: "Open registry (Tier 1)",
    2: "Shadow fleet registry (Tier 2)",
    3: "High-risk / sanctioned registry (Tier 3)",
}
