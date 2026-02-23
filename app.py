"""Flask application — Maritime OSINT Platform (Session 1: Sanctions Foundation)."""

import os
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import db
import ingest
import screening

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

db.init_db()

APP_PASSWORD = os.getenv("APP_PASSWORD")


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
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    result = screening.screen(query)
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


# ── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
