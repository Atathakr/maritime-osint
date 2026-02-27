import json
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FieldSerializationInfo,
    field_serializer,
    model_validator,
)


class AisPosition(BaseModel):
    """Normalized AIS position report."""
    model_config = ConfigDict(from_attributes=True)

    mmsi: str = Field(..., pattern=r"^\d{9}$")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    vessel_name: str | None = None
    vessel_type: int | None = None
    sog: float | None = None
    cog: float | None = None
    heading: int | None = None
    nav_status: int | None = None
    source: str = "aisstream"
    position_ts: datetime

    @field_serializer("position_ts", when_used="json")
    def serialize_ts(self, ts: datetime, _info: FieldSerializationInfo) -> str:
        return ts.isoformat()


class AisVesselStatic(BaseModel):
    """Normalized vessel static data (ShipStaticData)."""
    model_config = ConfigDict(from_attributes=True)

    mmsi: str = Field(..., pattern=r"^\d{9}$")
    imo_number: str | None = Field(None, pattern=r"^\d{7}$")
    vessel_name: str | None = None
    vessel_type: int | None = None
    call_sign: str | None = None
    length: float | None = None
    width: float | None = None
    draft: float | None = None
    destination: str | None = None
    eta: str | None = None


class OwnershipEntry(BaseModel):
    """A single ownership / management link for a vessel."""
    role: str           # 'owner', 'operator', 'manager', 'past_owner', etc.
    entity_name: str
    source: str


class SanctionsEntry(BaseModel):
    """Normalized sanctions list entry for a vessel."""
    model_config = ConfigDict(from_attributes=True)

    list_name: str
    source_id: str
    entity_name: str
    entity_type: str = "Vessel"
    imo_number: str | None = Field(None, pattern=r"^\d{7}$")
    mmsi: str | None = Field(None, pattern=r"^\d{9}$")
    vessel_type: str | None = None
    flag_state: str | None = None
    call_sign: str | None = None
    program: str | None = None
    gross_tonnage: int | None = None
    aliases: list[str] = Field(default_factory=list)
    identifiers: dict = Field(default_factory=dict)
    # Ownership opacity enrichment
    build_year: int | None = None
    past_flags: list[str] = Field(default_factory=list)
    ownership_entries: list[dict] = Field(default_factory=list)


class DarkPeriod(BaseModel):
    """Normalized dark period event (AIS gap)."""
    model_config = ConfigDict(from_attributes=True)

    mmsi: str = Field(..., pattern=r"^\d{9}$")
    imo_number: str | None = Field(None, pattern=r"^\d{7}$")
    vessel_name: str | None = None
    gap_start: datetime
    gap_end: datetime | None = None
    gap_hours: float | None = None
    last_lat: float | None = Field(None, ge=-90, le=90)
    last_lon: float | None = Field(None, ge=-180, le=180)
    reappear_lat: float | None = Field(None, ge=-90, le=90)
    reappear_lon: float | None = Field(None, ge=-180, le=180)
    distance_km: float | None = None
    risk_zone: str | None = None
    risk_level: str = "LOW"
    sanctions_hit: bool = False
    indicator_code: str = "IND1"

    @field_serializer("gap_start", "gap_end", when_used="json")
    def serialize_dates(self, dt: datetime | None, _info: FieldSerializationInfo) -> str | None:
        return dt.isoformat() if dt else None


class StsEvent(BaseModel):
    """Normalized ship-to-ship transfer event."""
    model_config = ConfigDict(from_attributes=True)

    mmsi1: str = Field(..., pattern=r"^\d{9}$")
    mmsi2: str = Field(..., pattern=r"^\d{9}$")
    vessel_name1: str | None = None
    vessel_name2: str | None = None
    event_ts: datetime
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    distance_m: float | None = None
    sog1: float | None = None
    sog2: float | None = None
    risk_zone: str | None = None
    risk_level: str = "LOW"
    sanctions_hit: bool = False
    indicator_code: str = "IND7"

    @field_serializer("event_ts", when_used="json")
    def serialize_event_ts(self, ts: datetime, _info: FieldSerializationInfo) -> str:
        return ts.isoformat()


# ── API Request Schemas ───────────────────────────────────────────────────

class ScreeningRequest(BaseModel):
    """Vessel screening query."""
    query: str = Field(..., min_length=1)


class DarkPeriodDetectRequest(BaseModel):
    """Dark period detection parameters."""
    mmsi: str | None = Field(None, pattern=r"^\d{9}$")
    min_hours: float = Field(2.0, gt=0)


class StsDetectRequest(BaseModel):
    """STS detection parameters."""
    hours_back: int = Field(48, gt=0, le=168)
    max_distance_km: float = Field(0.926, gt=0)
    max_sog: float = Field(3.0, gt=0)


# ── API Response / Result Schemas ─────────────────────────────────────────

class ScreeningHit(BaseModel):
    """A single sanctions match result."""
    canonical_id: str
    entity_name: str
    imo_number: str | None = None
    mmsi: str | None = None
    vessel_type: str | None = None
    flag_state: str | None = None
    source_tags: list[str] = Field(default_factory=list)
    program: str | None = None
    match_method: str
    match_confidence: str
    memberships: list[dict] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    # Ownership opacity enrichment
    build_year: int | None = None
    call_sign: str | None = None
    gross_tonnage: int | None = None
    flag_history: list[dict] = Field(default_factory=list)
    ownership: list[dict] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, data: dict) -> dict:
        """Parse JSON strings for list/dict fields (SQLite fallback)."""
        if not isinstance(data, dict):
            return data
        for field in ("aliases", "source_tags", "memberships"):
            val = data.get(field)
            if isinstance(val, str):
                try:
                    data[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    data[field] = []
            elif val is None:
                data[field] = []
        return data


class ScreeningResult(BaseModel):
    """Complete vessel screening report."""
    query: str
    query_type: str
    sanctioned: bool
    total_hits: int
    hits: list[ScreeningHit]
    error: str | None = None


class IndicatorSummary(BaseModel):
    """
    AIS intelligence signal counts and latest-event metadata for one vessel.
    Populated by db.get_vessel_indicator_summary(mmsi).
    """
    # Dark periods (IND1)
    dp_count: int = 0
    dp_last_ts: datetime | None = None
    dp_last_hours: float | None = None
    dp_last_lat: float | None = None
    dp_last_lon: float | None = None
    # STS events (IND7)
    sts_count: int = 0
    sts_last_ts: datetime | None = None
    sts_last_lat: float | None = None
    sts_last_lon: float | None = None
    # AIS last-seen
    ais_last_seen: datetime | None = None
    ais_sog: float | None = None
    ais_destination: str | None = None
    ais_lat: float | None = None
    ais_lon: float | None = None
    # Flag state risk (IND17)
    flag_risk_tier: int = 0
    flag_hop_count: int = 0
    # Speed anomalies / GPS spoofing proxy (IND10)
    spoof_count: int = 0
    spoof_last_ts: datetime | None = None
    spoof_last_lat: float | None = None
    spoof_last_lon: float | None = None
    spoof_last_speed_kt: float | None = None

    @field_serializer(
        "dp_last_ts", "sts_last_ts", "ais_last_seen", "spoof_last_ts", when_used="json"
    )
    def serialize_dt(self, dt: datetime | None, _info: FieldSerializationInfo) -> str | None:
        return dt.isoformat() if dt else None


class VesselDetail(BaseModel):
    """
    Deep detail report for a specific vessel.

    risk_score formula:
      sanctioned → 100 (hard ceiling)
      else       → min(min(dp×10,40) + min(sts×15,45) + tier×7 + min(hops×8,16) + min(spoof×8,24), 99)
    """
    imo_number: str
    vessel: dict | None = None
    sanctions_hits: list[ScreeningHit] = Field(default_factory=list)
    source_tags: list[str] = Field(default_factory=list)
    total_memberships: int = 0
    risk_factors: list[str] = Field(default_factory=list)
    risk_score: int = 0
    sanctioned: bool = False
    indicator_summary: IndicatorSummary | None = None
