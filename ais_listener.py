"""
AIS live position listener — aisstream.io WebSocket client.

Runs as a daemon thread started automatically by app.py when
AISSTREAM_API_KEY is set in the environment.

Filter: tanker vessel types (AIS codes 80–89) globally.
Buffer: positions are batched (BUFFER_SIZE) before DB insert to
        reduce write pressure on the SQLite/PostgreSQL backend.

aisstream.io free tier: https://aisstream.io  (register → API key)
WebSocket docs:         https://aisstream.io/documentation
"""

import asyncio
import json
import logging
import re
import threading
from datetime import datetime, timezone

import schemas

logger = logging.getLogger(__name__)

WSS_URL = "wss://stream.aisstream.io/v0/stream"

# AIS vessel type codes — tankers
TANKER_TYPES = list(range(80, 90))   # 80 = tanker (unspecified) … 89 = reserved

# Batch size before flushing to DB
BUFFER_SIZE = 50

# ── Module-level state ────────────────────────────────────────────────────

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_buffer: list[dict] = []
_stats: dict = {
    "connected":          False,
    "messages_received":  0,
    "positions_buffered": 0,
    "positions_inserted": 0,
    "static_updates":     0,
    "errors":             0,
    "last_message_at":    None,
    "connected_since":    None,
}


# ── Public API ────────────────────────────────────────────────────────────

def get_stats() -> dict:
    return dict(_stats)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def start(api_key: str) -> bool:
    """Start the background listener thread. Returns False if already running."""
    global _thread
    if is_running():
        return False
    _stop_event.clear()
    _thread = threading.Thread(
        target=_thread_main,
        args=(api_key,),
        daemon=True,
        name="ais-listener",
    )
    _thread.start()
    logger.info("AIS listener thread started")
    return True


def stop() -> None:
    """Signal the listener to shut down gracefully."""
    _stop_event.set()
    logger.info("AIS listener stop requested")


# ── Background thread ─────────────────────────────────────────────────────

def _thread_main(api_key: str) -> None:
    """Entry point for the daemon thread — owns its own asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_listen_loop(api_key))
    except Exception as e:
        logger.error("AIS listener thread crashed: %s", e)
    finally:
        _stats["connected"] = False
        loop.close()


async def _listen_loop(api_key: str) -> None:
    """Outer reconnect loop — reconnects after any WebSocket error."""
    subscribe_msg = {
        "APIKey":             api_key,
        "BoundingBoxes":      [[[-90, -180], [90, 180]]],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        "FilterShipType":     TANKER_TYPES,
    }

    while not _stop_event.is_set():
        try:
            # Import here so the module loads even if websockets isn't installed
            import websockets

            async with websockets.connect(
                WSS_URL,
                ping_interval=20,
                ping_timeout=30,
                close_timeout=10,
            ) as ws:
                _stats["connected"]       = True
                _stats["connected_since"] = datetime.now(timezone.utc).isoformat()
                logger.info("AIS WebSocket connected to aisstream.io")

                await ws.send(json.dumps(subscribe_msg))

                async for raw in ws:
                    if _stop_event.is_set():
                        break
                    try:
                        _handle_message(json.loads(raw))
                    except Exception as e:
                        _stats["errors"] += 1
                        logger.debug("AIS message parse error: %s", e)

        except Exception as e:
            _stats["connected"] = False
            _stats["errors"]   += 1
            logger.warning("AIS disconnected (%s) — reconnecting in 15s", e)
            _flush_buffer()
            await asyncio.sleep(15)

    _flush_buffer()
    _stats["connected"] = False


# ── Message handlers ──────────────────────────────────────────────────────

def _handle_message(msg: dict) -> None:
    _stats["messages_received"] += 1
    _stats["last_message_at"]    = datetime.now(timezone.utc).isoformat()

    msg_type = msg.get("MessageType")
    if msg_type == "PositionReport":
        pos = _parse_position(msg)
        if pos:
            _buffer.append(pos)
            _stats["positions_buffered"] += 1
            # Also update last-seen on ais_vessels
            import db
            db.update_ais_vessel_position(
                pos.mmsi, pos.lat, pos.lon,
                pos.sog or 0, pos.cog or 0,
                pos.nav_status or 0, 
                pos.position_ts.isoformat() if isinstance(pos.position_ts, datetime) else pos.position_ts,
            )
            if len(_buffer) >= BUFFER_SIZE:
                _flush_buffer()

    elif msg_type == "ShipStaticData":
        _handle_static(msg)


def _parse_position(msg: dict) -> schemas.AisPosition | None:
    meta = msg.get("MetaData", {})
    body = msg.get("Message", {}).get("PositionReport", {})

    mmsi = str(meta.get("MMSI", "")).strip()
    lat  = meta.get("latitude")
    lon  = meta.get("longitude")

    if not mmsi or lat is None or lon is None:
        return None
    # Sanity-check coordinates
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    ts_raw = meta.get("time_utc", "")
    try:
        ts = datetime.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)

    try:
        return schemas.AisPosition(
            mmsi=mmsi,
            vessel_name=(meta.get("ShipName") or "").strip() or None,
            vessel_type=meta.get("ShipType"),
            lat=lat,
            lon=lon,
            sog=body.get("Sog"),
            cog=body.get("Cog"),
            heading=body.get("TrueHeading"),
            nav_status=body.get("NavigationalStatus"),
            source="aisstream",
            position_ts=ts,
        )
    except Exception as e:
        logger.debug("Validation failed for position MMSI %s: %s", mmsi, e)
        return None


def _handle_static(msg: dict) -> None:
    meta   = msg.get("MetaData", {})
    static = msg.get("Message", {}).get("ShipStaticData", {})

    mmsi = str(meta.get("MMSI", "")).strip()
    if not mmsi:
        return

    imo_raw = str(static.get("ImoNumber", ""))
    imo     = _clean_imo(imo_raw)

    dim = static.get("Dimension", {}) or {}
    length = (dim.get("A") or 0) + (dim.get("B") or 0) or None
    width  = (dim.get("C") or 0) + (dim.get("D") or 0) or None

    try:
        vessel_data = schemas.AisVesselStatic(
            mmsi=mmsi,
            imo_number=imo,
            vessel_name=((static.get("Name") or meta.get("ShipName") or "")).strip() or None,
            vessel_type=static.get("Type"),
            call_sign=(static.get("CallSign") or "").strip() or None,
            length=length,
            width=width,
            draft=static.get("MaximumStaticDraught"),
            destination=(static.get("Destination") or "").strip() or None,
            eta=_format_eta(static.get("Eta")),
        )
        import db
        db.upsert_ais_vessel(mmsi, vessel_data.model_dump())
        _stats["static_updates"] += 1
    except Exception as e:
        logger.debug("Static update/validation failed for MMSI %s: %s", mmsi, e)


def _flush_buffer() -> None:
    global _buffer
    if not _buffer:
        return
    batch   = [p.model_dump() for p in _buffer]
    _buffer = []
    try:
        import db
        n = db.insert_ais_positions(batch)
        _stats["positions_inserted"] += n
        logger.debug("Flushed %d positions (%d inserted)", len(batch), n)
    except Exception as e:
        _stats["errors"] += 1
        logger.error("Position flush failed: %s", e)


# ── Helpers ───────────────────────────────────────────────────────────────

def _clean_imo(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 7 else None


def _format_eta(eta: dict | None) -> str | None:
    if not eta:
        return None
    try:
        return (
            f"{int(eta.get('Month', 0)):02d}/{int(eta.get('Day', 0)):02d} "
            f"{int(eta.get('Hour', 0)):02d}:{int(eta.get('Minute', 0)):02d}"
        )
    except Exception:
        return None
