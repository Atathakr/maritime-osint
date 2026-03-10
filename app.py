"""Flask application — Maritime OSINT Platform (Sessions 1–4: Sanctions + AIS + Reconciliation)."""

import csv as _csv
import io as _io
import os
import sys

# Load .env for local dev (no-op in production where env vars are set by the platform).
# Set DOTENV_DISABLED=1 to suppress this (used by test_inf4_startup.py subprocess tests).
if not os.environ.get("DOTENV_DISABLED"):
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=True)

# ── Startup enforcement — must run before any heavy imports ──────────────────
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    print("[maritime-osint] SECRET_KEY is required. Set it in your environment or .env file. See .env.example.")
    sys.exit(1)
_app_password = os.environ.get("APP_PASSWORD")
if not _app_password:
    print("[maritime-osint] APP_PASSWORD is required. Set it in your environment or .env file. See .env.example.")
    sys.exit(1)
# ── End startup enforcement ──────────────────────────────────────────────────

from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import db
import ingest
import screening
import ais_listener
import dark_periods
import noaa_ingest
import sts_detection
import spoofing
import reconcile
import map_data
import schemas
import loitering
import ports

from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import ValidationError

from security import limiter, csrf, init_security

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# ── Indicator metadata — all 31 Shadow Fleet Framework indicators ──────────
# 12 implemented (have entries in indicator_json when fired).
# 19 are placeholders — always shown as not-fired in the breakdown table.
INDICATOR_META = [
    {"id": "IND1",  "name": "AIS Dark Period",           "category": "Behavior",   "max_pts": 40},
    {"id": "IND2",  "name": "Indicator 2",               "category": "—",          "max_pts": 0},
    {"id": "IND3",  "name": "Indicator 3",               "category": "—",          "max_pts": 0},
    {"id": "IND4",  "name": "Indicator 4",               "category": "—",          "max_pts": 0},
    {"id": "IND5",  "name": "Indicator 5",               "category": "—",          "max_pts": 0},
    {"id": "IND6",  "name": "Indicator 6",               "category": "—",          "max_pts": 0},
    {"id": "IND7",  "name": "STS Transfer",              "category": "Behavior",   "max_pts": 45},
    {"id": "IND8",  "name": "STS in Risk Zone",          "category": "Behavior",   "max_pts": 10},
    {"id": "IND9",  "name": "Open-water Loitering",      "category": "Behavior",   "max_pts": 15},
    {"id": "IND10", "name": "Speed Anomaly (Spoofing)",  "category": "Behavior",   "max_pts": 24},
    {"id": "IND11", "name": "Indicator 11",              "category": "—",          "max_pts": 0},
    {"id": "IND12", "name": "Indicator 12",              "category": "—",          "max_pts": 0},
    {"id": "IND13", "name": "Indicator 13",              "category": "—",          "max_pts": 0},
    {"id": "IND14", "name": "Indicator 14",              "category": "—",          "max_pts": 0},
    {"id": "IND15", "name": "Flag Hopping",              "category": "Registry",   "max_pts": 16},
    {"id": "IND16", "name": "Name Discrepancy",          "category": "Identity",   "max_pts": 0},
    {"id": "IND17", "name": "Flag Risk Tier",            "category": "Registry",   "max_pts": 21},
    {"id": "IND18", "name": "Indicator 18",              "category": "—",          "max_pts": 0},
    {"id": "IND19", "name": "Indicator 19",              "category": "—",          "max_pts": 0},
    {"id": "IND20", "name": "Indicator 20",              "category": "—",          "max_pts": 0},
    {"id": "IND21", "name": "Ownership-chain Sanctions", "category": "Ownership",  "max_pts": 40},
    {"id": "IND22", "name": "Indicator 22",              "category": "—",          "max_pts": 0},
    {"id": "IND23", "name": "Vessel Age",                "category": "Identity",   "max_pts": 15},
    {"id": "IND24", "name": "Indicator 24",              "category": "—",          "max_pts": 0},
    {"id": "IND25", "name": "Indicator 25",              "category": "—",          "max_pts": 0},
    {"id": "IND26", "name": "Indicator 26",              "category": "—",          "max_pts": 0},
    {"id": "IND27", "name": "Indicator 27",              "category": "—",          "max_pts": 0},
    {"id": "IND28", "name": "Indicator 28",              "category": "—",          "max_pts": 0},
    {"id": "IND29", "name": "Sanctioned Port Call",      "category": "Behavior",   "max_pts": 40},
    {"id": "IND30", "name": "Indicator 30",              "category": "—",          "max_pts": 0},
    {"id": "IND31", "name": "PSC Detention Record",      "category": "Compliance", "max_pts": 20},
]

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = _secret_key

db.init_db()
init_security(app)

APP_PASSWORD = _app_password
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")

# Auto-start AIS listener if API key is configured
if AISSTREAM_API_KEY:
    ais_listener.start(AISSTREAM_API_KEY)


# ── APScheduler — background jobs ─────────────────────────────────────────
# _SCHEDULER_ADVISORY_LOCK_ID = 42 prevents duplicate job runs across
# the 2 Gunicorn workers on Railway. Each worker starts its own scheduler;
# the advisory lock ensures only one worker executes the job body per cycle.
_SCHEDULER_ADVISORY_LOCK_ID = 42


def _refresh_all_scores_job() -> None:
    """
    APScheduler entry-point: refresh composite risk scores for all vessels
    that have an existing vessel_scores row.
    Uses pg_try_advisory_xact_lock to prevent double-run across Gunicorn workers.
    """
    import logging
    log = logging.getLogger(__name__)
    try:
        if db._BACKEND == "postgres":
            with db._conn() as conn:
                c = conn.cursor()
                c.execute("SELECT pg_try_advisory_xact_lock(%s)", (_SCHEDULER_ADVISORY_LOCK_ID,))
                if not c.fetchone()[0]:
                    return  # another worker is running this job
                _do_score_refresh()
                # advisory lock auto-released when transaction commits at end of 'with' block
        else:
            # SQLite (local dev): no lock needed; single process
            _do_score_refresh()
    except Exception:
        log.exception("[scheduler] score refresh failed")


def _do_score_refresh() -> None:
    """Iterate over all known vessel_scores rows and recompute each score."""
    import logging
    log = logging.getLogger(__name__)
    rows = db.get_all_vessel_scores()
    refreshed = 0
    for row in rows:
        imo = row.get("imo_number")
        if not imo:
            continue
        try:
            fresh = screening.compute_vessel_score(imo)
            db.upsert_vessel_score(imo, fresh)
            db.append_score_history(imo, fresh)
            refreshed += 1
        except Exception:
            log.exception("[scheduler] failed to refresh score for IMO %s", imo)
    log.info("[scheduler] score refresh complete: %d vessels refreshed", refreshed)


def _archive_ais_job() -> None:
    """APScheduler entry-point: delete ais_positions rows older than 90 days."""
    import logging
    log = logging.getLogger(__name__)
    try:
        deleted = db.archive_old_ais_positions(days=90)
        log.info("[scheduler] AIS archive complete: %d rows deleted", deleted)
    except Exception:
        log.exception("[scheduler] AIS archive failed")


def _prune_history_job() -> None:
    """APScheduler entry-point: delete vessel_score_history rows older than 90 days."""
    import logging
    log = logging.getLogger(__name__)
    try:
        deleted = db.prune_score_history(days=90)
        log.info("[scheduler] history prune complete: %d rows deleted", deleted)
    except Exception:
        log.exception("[scheduler] history prune failed")


# Start scheduler after db.init_db() so tables exist before first job fires.
# BackgroundScheduler runs in a daemon thread — does not block app shutdown.
# Both Gunicorn workers start their own scheduler instance; the advisory lock
# in _refresh_all_scores_job prevents double-execution on PostgreSQL.
_scheduler = BackgroundScheduler(daemon=True)
_scheduler.add_job(
    _refresh_all_scores_job,
    trigger="interval",
    minutes=15,
    id="score_refresh",
    replace_existing=True,
)
_scheduler.add_job(
    _archive_ais_job,
    trigger="cron",
    hour=3,
    minute=0,
    id="ais_archive",
    replace_existing=True,
)
_scheduler.add_job(
    _prune_history_job,
    trigger="cron",
    hour=3,
    minute=5,
    id="history_prune",
    replace_existing=True,
)
_scheduler.start()


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
@limiter.limit("10 per minute")
def login_post():
    if request.form.get("password", "") == APP_PASSWORD:
        session["authenticated"] = True
        return redirect(url_for("index"))
    return render_template("login.html", error="Incorrect password")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.errorhandler(429)
def ratelimit_exceeded(e):
    return jsonify({"error": "Too many login attempts. Try again in 1 minute."}), 429


# ── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/csp-report")
@csrf.exempt
def csp_report():
    """Receive CSP violation reports (report-only mode in Plan 04-02).
    Reports are currently discarded — add logging in a future pass if needed.
    """
    return "", 204


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
@csrf.exempt
@login_required
def api_screen():
    """Screen a vessel by IMO, MMSI, or name against all sanctions lists."""
    try:
        data = schemas.ScreeningRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    result = screening.screen(data.query)
    return jsonify(result.model_dump())


@app.get("/api/screen/<path:imo>")
@login_required
def api_screen_imo(imo):
    """Full screening report for a specific vessel by IMO number."""
    result = screening.screen_vessel_detail(imo)
    return jsonify(result.model_dump())


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


# N+1 audit (INF-1): all multi-vessel endpoints confirmed batch-query only.
# api_vessels           → db.get_vessels() batch
# api_map_vessels       → map_data.get_map_vessels_raw() batch JOIN
# api_vessels_ranking   → db.get_all_vessel_scores() batch JOIN (this endpoint)
@app.get("/api/vessels/ranking")
@login_required
def api_vessels_ranking():
    """
    Vessel ranking by pre-computed composite risk score.

    Returns all vessels in vessel_scores sorted by composite_score descending.
    Uses a single batch JOIN query — no per-vessel SELECT loops (INF-1).

    Query params:
        limit         — max vessels to return (default 100, cap 500)
        sanctioned_only — "1" or "true" to filter to sanctioned vessels only
    """
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        sanctioned_only = request.args.get("sanctioned_only", "").lower() in ("1", "true")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid parameters: {exc}"}), 400

    rows = db.get_all_vessel_scores()  # single batch JOIN — sorted DESC by composite_score

    if sanctioned_only:
        rows = [r for r in rows if r.get("is_sanctioned")]

    rows = rows[:limit]

    return jsonify({
        "vessels": rows,
        "count": len(rows),
        "note": "Scores refresh every 15 minutes via background scheduler",
    })


@app.get("/vessel/<path:imo>")
@login_required
def vessel_profile(imo):
    """
    Vessel profile permalink (FE-5).
    Registered BEFORE /api/vessels/<path:imo> to avoid catch-all shadowing.
    """
    vessel = db.get_vessel(imo)
    score = db.get_vessel_score(imo)
    if not vessel and not score:
        return render_template("vessel.html", imo=imo, vessel=None, score=None,
                               indicator_meta=INDICATOR_META), 404
    return render_template("vessel.html", imo=imo, vessel=vessel, score=score,
                           indicator_meta=INDICATOR_META)


@app.get("/export/vessels.csv")
@login_required
def export_vessels_csv():
    """
    CSV export of all scored vessels (FE-6).
    Columns: vessel_name, imo, mmsi, flag, composite_score, risk_level,
             evidence_count, computed_at, is_stale
    """
    rows = db.get_all_vessel_scores()
    out = _io.StringIO()
    w = _csv.writer(out)
    w.writerow([
        "vessel_name", "imo", "mmsi", "flag",
        "composite_score", "risk_level", "evidence_count",
        "computed_at", "is_stale",
    ])
    for r in rows:
        score = r.get("composite_score") or 0
        ind   = r.get("indicator_json") or {}
        ev    = sum(1 for v in ind.values() if isinstance(v, dict) and v.get("fired"))
        # Derive risk_level from composite_score (not stored in vessel_scores schema)
        if score >= 100:
            risk_level = "CRITICAL"
        elif score >= 70:
            risk_level = "HIGH"
        elif score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        w.writerow([
            r.get("entity_name") or "",
            r.get("imo_number") or "",
            r.get("mmsi") or "",
            r.get("flag_normalized") or "",
            score,
            risk_level,
            ev,
            r.get("computed_at") or "",
            "true" if r.get("is_stale") else "false",
        ])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="maritime-osint-vessels.csv"'
    return resp


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
        # Invalidate pre-computed scores for affected vessels so staleness fallback
        # triggers on next profile load (DB-5).
        _affected_imos = [e.get("imo_number") for e in entries if e.get("imo_number")]
        if _affected_imos:
            db.mark_risk_scores_stale(_affected_imos)
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
@csrf.exempt
@login_required
def api_ingest_ofac():
    """Download and ingest the OFAC SDN vessel list (synchronous, ~5–15 s)."""
    result = _run_ingest("OFAC_SDN", ingest.fetch_ofac_sdn, "OFAC_SDN")
    code = 200 if result["status"] == "success" else 502
    return jsonify(result), code


@app.post("/api/ingest/opensanctions")
@csrf.exempt
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


@app.post("/api/ingest/psc/<source>")
@csrf.exempt
@login_required
def api_ingest_psc(source):
    """
    Download and ingest PSC detention records from Paris MOU or Tokyo MOU.
    <source> must be 'paris' or 'tokyo'.
    """
    if source not in ("paris", "tokyo"):
        return jsonify({"error": "Unknown PSC source. Use 'paris' or 'tokyo'."}), 400
    label = f"PSC_{source.upper()}"
    log_id = db.log_ingest_start(label)
    try:
        records  = ingest.fetch_psc_detentions(source)
        inserted = db.upsert_psc_detentions(records)
        db.log_ingest_complete(log_id, "success",
                               processed=len(records), inserted=inserted, updated=0)
        return jsonify({
            "status":    "success",
            "source":    label,
            "processed": len(records),
            "inserted":  inserted,
        })
    except Exception as exc:
        db.log_ingest_complete(log_id, "error", error=str(exc))
        return jsonify({"status": "error", "source": label, "error": str(exc)}), 502


@app.get("/api/ingest/log")
@login_required
def api_ingest_log():
    return jsonify(db.get_ingest_log())


# ── AIS Listener ──────────────────────────────────────────────────────────

@app.post("/api/ais/start")
@csrf.exempt
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
@csrf.exempt
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


@app.get("/api/ais/vessels/<mmsi>/track")
@login_required
def api_vessel_track(mmsi):
    """Historical track for a specific vessel (default 72h)."""
    hours = min(int(request.args.get("hours", 72)), 168)  # Cap at 1 week
    track = db.get_vessel_track(mmsi, hours=hours)
    return jsonify({"mmsi": mmsi, "count": len(track), "track": track})


# ── Dark Periods ───────────────────────────────────────────────────────────

@app.post("/api/dark-periods/detect")
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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


# ── Loitering Detection ───────────────────────────────────────────────────

@app.post("/api/ais/detect-loitering")
@csrf.exempt
@login_required
def api_detect_loitering():
    """
    Run open-water loitering detection (IND9) over recent AIS positions.
    Body (all optional): {"sog_threshold_kt": 2.0, "min_hours": 12, "hours_back": 168}
    """
    data = request.get_json(silent=True) or {}
    threshold = float(data.get("sog_threshold_kt", 2.0))
    min_hours  = float(data.get("min_hours", 12.0))
    hours_back = int(data.get("hours_back", 168))
    result = loitering.run_loitering_detection(threshold, min_hours, hours_back)
    return jsonify(result)


# ── Sanctioned Port Detection ─────────────────────────────────────────────

@app.post("/api/ports/detect-calls")
@csrf.exempt
@login_required
def api_detect_port_calls():
    """
    Run sanctioned port call detection (IND29) over recent AIS positions.
    Body (all optional): {"hours_back": 720}
    Defaults to 30-day look-back (720 h).
    """
    data = request.get_json(silent=True) or {}
    hours_back = int(data.get("hours_back", 720))
    result = ports.run_port_call_detection(hours_back)
    return jsonify(result)


# ── AIS Anomaly Detection ─────────────────────────────────────────────────

@app.post("/api/ais/detect-anomalies")
@csrf.exempt
@login_required
def api_detect_anomalies():
    """
    Run speed-anomaly detection (IND10) over recent AIS positions.
    Body (all optional): {"threshold_kt": 50.0, "hours_back": 168}
    """
    data = request.get_json(silent=True) or {}
    threshold = float(data.get("threshold_kt", 50.0))
    hours_back = int(data.get("hours_back", 168))
    result = spoofing.run_speed_anomaly_detection(threshold, hours_back)
    return jsonify(result)


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
@csrf.exempt
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
