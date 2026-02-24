"""Flask application — Maritime OSINT Platform (Sessions 1–4: Sanctions + AIS + Reconciliation)."""

import os
import secrets
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import db
import ingest
import screening
import ais_listener
import dark_periods
import noaa_ingest
import sts_detection
import reconcile
import map_data
import schemas

from pydantic import ValidationError

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

db.init_db()

APP_PASSWORD = os.getenv("APP_PASSWORD")
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")

# Auto-start AIS listener if API key is configured
if AISSTREAM_API_KEY:
    ais_listener.start(AISSTREAM_API_KEY)


# ── Auth ──────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if APP_PASSWORD and not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def check_auth():
    open_paths = {"/login", "/static", "/health"}
    if APP_PASSWORD and not session.get("authenticated"):
        if not any(request.path.startswith(p) for p in open_paths):
            return redirect(url_for("login"))


@app.get("/login")
def login():
    if not APP_PASSWORD or session.get("authenticated"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.post("/login")
def login_post():
    if request.form.get("password", "") == APP_PASSWORD:
        session["authenticated"] = True
        return redirect(url_for("index"))
    return render_template("login.html", error="Incorrect password")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


# ── Dashboard ─────────────────────────────────────────────────────────────

@app.get("/")
@login_required
def index():
    return render_template("dashboard.html")


# ── Stats ─────────────────────────────────────────────────────────────────

@app.get("/api/stats")
@login_required
def api_stats():
    return jsonify(db.get_stats())


# ── Screening ─────────────────────────────────────────────────────────────

@app.post("/api/screen")
@login_required
def api_screen():
    """Screen a vessel by IMO, MMSI, or name against all sanctions lists."""
    try:
        data = schemas.ScreeningRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    result = screening.screen(data.query)
    return jsonify(result)


@app.get("/api/screen/<path:imo>")
@login_required
def api_screen_imo(imo):
    """Full screening report for a specific vessel by IMO number."""
    result = screening.screen_vessel_detail(imo)
    return jsonify(result)


# ── Sanctions browser ─────────────────────────────────────────────────────

@app.get("/api/sanctions")
@login_required
def api_sanctions():
    """
    List sanctions entries with optional filtering.
    Query params: list_name, program, entity_type, q, limit, offset
    """
    result = db.get_sanctions_entries(
        list_name=request.args.get("list_name") or None,
        program=request.args.get("program") or None,
        entity_type=request.args.get("entity_type") or None,
        q=request.args.get("q") or None,
        limit=min(int(request.args.get("limit", 200)), 500),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify(result)


@app.get("/api/sanctions/counts")
@login_required
def api_sanctions_counts():
    return jsonify(db.get_sanctions_counts())


# ── Vessels ───────────────────────────────────────────────────────────────

@app.get("/api/vessels")
@login_required
def api_vessels():
    vessels = db.get_vessels(
        q=request.args.get("q") or None,
        limit=min(int(request.args.get("limit", 100)), 500),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify(vessels)


@app.get("/api/vessels/<path:imo>")
@login_required
def api_vessel_detail(imo):
    vessel = db.get_vessel(imo)
    if not vessel:
        return jsonify({"error": "Vessel not found"}), 404
    hits = db.search_sanctions_by_imo(imo)
    return jsonify({"vessel": vessel, "sanctions_hits": hits})


# ── Ingest ────────────────────────────────────────────────────────────────

def _run_ingest(source: str, fetch_fn, list_name: str) -> dict:
    """Shared ingest logic: fetch → parse → upsert → log. Returns result dict."""
    log_id = db.log_ingest_start(source)
    try:
        entries = fetch_fn()
        inserted, updated = db.upsert_sanctions_entries(entries, list_name)
        db.log_ingest_complete(
            log_id, "success",
            processed=len(entries),
            inserted=inserted,
            updated=updated,
        )
        return {
            "status":    "success",
            "source":    source,
            "processed": len(entries),
            "inserted":  inserted,
            "updated":   updated,
        }
    except Exception as exc:
        db.log_ingest_complete(log_id, "error", error=str(exc))
        return {"status": "error", "source": source, "error": str(exc)}


@app.post("/api/ingest/ofac")
@login_required
def api_ingest_ofac():
    """Download and ingest the OFAC SDN vessel list (synchronous, ~5–15 s)."""
    result = _run_ingest("OFAC_SDN", ingest.fetch_ofac_sdn, "OFAC_SDN")
    code = 200 if result["status"] == "success" else 502
    return jsonify(result), code


@app.post("/api/ingest/opensanctions")
@login_required
def api_ingest_opensanctions():
    """
    Stream and ingest OpenSanctions consolidated vessel data (sync, 30–90 s).
    The gunicorn timeout is set to 120 s which is sufficient.
    """
    result = _run_ingest(
        "OpenSanctions",
        ingest.fetch_opensanctions_vessels,
        "OpenSanctions",
    )
    code = 200 if result["status"] == "success" else 502
    return jsonify(result), code


@app.get("/api/ingest/log")
@login_required
def api_ingest_log():
    return jsonify(db.get_ingest_log())


# ── AIS Listener ──────────────────────────────────────────────────────────

@app.post("/api/ais/start")
@login_required
def api_ais_start():
    """Start the AIS WebSocket listener. Requires AISSTREAM_API_KEY in body or env."""
    data = request.get_json(silent=True) or {}
    key = data.get("api_key", "").strip() or AISSTREAM_API_KEY
    if not key:
        return jsonify({"error": "api_key is required (or set AISSTREAM_API_KEY env var)"}), 400
    ais_listener.start(key)
    return jsonify({"status": "started", **ais_listener.get_stats()})


@app.post("/api/ais/stop")
@login_required
def api_ais_stop():
    """Stop the AIS WebSocket listener."""
    ais_listener.stop()
    return jsonify({"status": "stopped"})


@app.get("/api/ais/status")
@login_required
def api_ais_status():
    """Return AIS listener stats."""
    return jsonify(ais_listener.get_stats())


@app.get("/api/ais/positions")
@login_required
def api_ais_positions():
    """
    Recent AIS positions.
    Query params: mmsi, limit (max 1000), offset
    """
    mmsi = request.args.get("mmsi") or None
    limit = min(int(request.args.get("limit", 200)), 1000)
    offset = int(request.args.get("offset", 0))
    rows = db.get_ais_positions(mmsi=mmsi, limit=limit, offset=offset)
    return jsonify(rows)


@app.get("/api/ais/vessels")
@login_required
def api_ais_vessels():
    """
    AIS vessel roster (current state — one row per MMSI).
    Query params: q (name search), limit, offset
    """
    rows = db.get_ais_vessels(
        q=request.args.get("q") or None,
        limit=min(int(request.args.get("limit", 200)), 1000),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify(rows)


# ── Dark Periods ───────────────────────────────────────────────────────────

@app.post("/api/dark-periods/detect")
@login_required
def api_dark_periods_detect():
    """
    Run dark-period detection for one MMSI (or all if omitted).
    Body: {"mmsi": "123456789", "min_hours": 2}
    """
    try:
        data = schemas.DarkPeriodDetectRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if data.mmsi:
        periods = dark_periods.run_detection(data.mmsi, data.min_hours)
        summary = dark_periods.summarise(periods)
        return jsonify({"mmsi": data.mmsi, "periods_found": len(periods), "summary": summary})

    # Bulk: iterate all unique MMSIs seen in the last 30 days
    all_mmsis = db.get_active_mmsis(days=30)
    total = 0
    for m in all_mmsis:
        found = dark_periods.run_detection(m, data.min_hours)
        total += len(found)
    return jsonify({"mmsis_scanned": len(all_mmsis), "total_periods_found": total})


@app.get("/api/dark-periods")
@login_required
def api_dark_periods():
    """
    List detected dark periods.
    Query params: mmsi, risk_level (LOW/MEDIUM/HIGH/CRITICAL), limit, offset
    """
    rows = db.get_dark_periods(
        mmsi=request.args.get("mmsi") or None,
        risk_level=request.args.get("risk_level") or None,
        limit=min(int(request.args.get("limit", 200)), 1000),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify(rows)


# ── NOAA Ingest ────────────────────────────────────────────────────────────

@app.post("/api/ingest/noaa")
@login_required
def api_ingest_noaa():
    """
    Bulk-load a NOAA Marine Cadastre monthly AIS CSV.
    Body: {"year": 2024, "month": 6, "zone": 10, "all_vessel_types": false}
    Defaults to Zone 10 (Gulf of Mexico), tankers only.
    """
    data = request.get_json(silent=True) or {}
    try:
        year  = int(data.get("year",  2024))
        month = int(data.get("month", 6))
        zone  = int(data.get("zone",  10))
        all_types = bool(data.get("all_vessel_types", False))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid parameters: {exc}"}), 400

    log_id = db.log_ingest_start(f"NOAA_{year}_{month:02d}_zone{zone}")
    try:
        result = noaa_ingest.fetch_and_ingest(year, month, zone,
                                              all_vessel_types=all_types)
        db.log_ingest_complete(
            log_id, "success",
            processed=result.get("rows_processed", 0),
            inserted=result.get("rows_inserted", 0),
            updated=0,
        )
        return jsonify({"status": "success", **result})
    except Exception as exc:
        db.log_ingest_complete(log_id, "error", error=str(exc))
        return jsonify({"status": "error", "error": str(exc)}), 502


# ── STS Detection ─────────────────────────────────────────────────────────

@app.post("/api/sts/detect")
@login_required
def api_sts_detect():
    """
    Run STS proximity detection over recent AIS positions.
    Body (all optional): {"hours_back": 48, "max_distance_km": 0.926, "max_sog": 3.0}
    """
    try:
        data = schemas.StsDetectRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    events = sts_detection.run_detection(
        hours_back=data.hours_back,
        max_distance_km=data.max_distance_km,
        max_sog=data.max_sog,
    )
    summary = sts_detection.summarise(events)
    return jsonify({
        "events_found": len(events),
        "summary":      summary,
        "hours_back":   data.hours_back,
    })


@app.get("/api/sts/events")
@login_required
def api_sts_events():
    """
    List detected STS events.
    Query params: mmsi, risk_level, sanctions_only, limit, offset
    """
    rows = db.get_sts_events(
        mmsi=request.args.get("mmsi") or None,
        risk_level=request.args.get("risk_level") or None,
        sanctions_only=request.args.get("sanctions_only", "").lower() in ("1", "true"),
        limit=min(int(request.args.get("limit", 200)), 1000),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify(rows)


# ── Map ───────────────────────────────────────────────────────────────────

@app.get("/api/map/vessels")
@login_required
def api_map_vessels():
    """
    Vessel positions + composite risk for the live maritime map.

    Query params:
        hours        — AIS recency window in hours (default 720 = 30 days)
        dp_days      — dark-period look-back window in days (default 30)
        sts_days     — STS-event look-back window in days (default 30)
        risk_filter  — all | medium_plus | high_plus | sanctioned
                       (default: medium_plus — hides clean vessels with no signals)
    """
    try:
        hours       = int(request.args.get("hours",       720))
        dp_days     = int(request.args.get("dp_days",      30))
        sts_days    = int(request.args.get("sts_days",     30))
        risk_filter = request.args.get("risk_filter", "medium_plus")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid parameters: {exc}"}), 400

    vessels = map_data.get_map_vessels(
        hours=hours,
        dp_days=dp_days,
        sts_days=sts_days,
        risk_filter=risk_filter,
    )
    return jsonify({"vessels": vessels, "count": len(vessels)})


# ── Reconciliation ────────────────────────────────────────────────────────

@app.post("/api/reconcile")
@login_required
def api_reconcile():
    """
    Run post-ingest canonical reconciliation passes.

    Tier 1 — IMO safety sweep: collapses any duplicate canonical records
              that share the same IMO number (should not normally occur, but
              guards against edge cases in upstream data).

    Tier 2 — MMSI→IMO merge: finds MMSI-keyed canonicals whose MMSI value
              also appears in an IMO-keyed canonical, then merges them so the
              stronger identifier (IMO) wins.

    Returns a summary:
      {"tier1_imo_merges": N, "tier2_mmsi_merges": N}
    """
    try:
        summary = reconcile.run_reconciliation()
        return jsonify({"status": "success", **summary})
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 502


# ── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
