from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, FieldSerializationInfo, field_serializer


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
    position_ts: datetime | str

    @field_serializer("position_ts")
    def serialize_ts(self, ts: datetime | str, _info: FieldSerializationInfo) -> str:
        if isinstance(ts, datetime):
            return ts.isoformat()
        return ts


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


class DarkPeriod(BaseModel):
    """Normalized dark period event (AIS gap)."""
    model_config = ConfigDict(from_attributes=True)

    mmsi: str = Field(..., pattern=r"^\d{9}$")
    imo_number: str | None = Field(None, pattern=r"^\d{7}$")
    vessel_name: str | None = None
    gap_start: datetime | str
    gap_end: datetime | str | None = None
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

    @field_serializer("gap_start", "gap_end")
    def serialize_dates(self, dt: datetime | str | None, _info: FieldSerializationInfo) -> str | None:
        if isinstance(dt, datetime):
            return dt.isoformat()
        return dt


class StsEvent(BaseModel):
    """Normalized ship-to-ship transfer event."""
    model_config = ConfigDict(from_attributes=True)

    mmsi1: str = Field(..., pattern=r"^\d{9}$")
    mmsi2: str = Field(..., pattern=r"^\d{9}$")
    vessel_name1: str | None = None
    vessel_name2: str | None = None
    event_ts: datetime | str
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    distance_m: float | None = None
    sog1: float | None = None
    sog2: float | None = None
    risk_zone: str | None = None
    risk_level: str = "LOW"
    sanctions_hit: bool = False
    indicator_code: str = "IND7"

    @field_serializer("event_ts")
    def serialize_event_ts(self, ts: datetime | str, _info: FieldSerializationInfo) -> str:
        if isinstance(ts, datetime):
            return ts.isoformat()
        return ts


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
