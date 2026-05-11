"""
dashboard/app.py
Flask API REST + PWA — Scorpius v2 (Version Blindée)
"""

import os
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory
)
from dotenv import load_dotenv

from config.loader import get_config
import storage.db as db_module

load_dotenv()
logger = logging.getLogger(__name__)

# ─── ADAPTATEURS DYNAMIQUES DB (Sécurité anti-crash) ──────────────────────────
init_db           = getattr(db_module, "init_db", lambda: None)
ping_db           = getattr(db_module, "ping_db", lambda: True)
get_missions      = getattr(db_module, "get_missions", lambda **k: [])
get_mission_by_id = getattr(db_module, "get_mission_by_id", lambda id: None)
delete_mission    = getattr(db_module, "delete_mission", lambda id: None)
upsert_mission    = getattr(db_module, "upsert_mission", lambda m: None)

def get_stats_gains():
    if hasattr(db_module, "get_stats_gains"): return db_module.get_stats_gains()
    st = getattr(db_module, "get_stats", lambda: {})()
    return {"mois": st.get("gains_mois", 0), "total": st.get("gains_total", 0), "en_attente": st.get("en_attente", 0)}

def get_compteurs_statut():
    if hasattr(db_module, "get_compteurs_statut"): return db_module.get_compteurs_statut()
    st = getattr(db_module, "get_stats", lambda: {})()
    missions = get_missions()
    c = {"total": len(missions), "proposee": 0, "en_attente": 0, "en_cours": 0, "terminee": 0, "refusee": 0}
    for m in missions:
        s = m.get("statut", "proposee")
        c[s] = c.get(s, 0) + 1
    return c

def get_evolution_mensuelle():
    if hasattr(db_module, "get_evolution_mensuelle"): return db_module.get_evolution_mensuelle()
    if hasattr(db_module, "get_stats_graphique"): return db_module.get_stats_graphique()
    return []

def get_plateformes_disponibles():
    if hasattr(db_module, "get_plateformes_disponibles"): return db_module.get_plateformes_disponibles()
    return sorted(list({m.get("plateforme") for m in get_missions() if m.get("plateforme")}))

def update_statut_mission(mission_id, statut, gains=None, notes=None):
    if hasattr(db_module, "update_statut_mission"): return db_module.update_statut_mission(mission_id, statut, gains, notes)
    if hasattr(db_module, "update_mission_statut"): db_module.update_mission_statut(mission_id, statut)
    if gains is not None and hasattr(db_module, "update_mission_gains"): db_module.update_mission_gains(mission_id, gains)
    if notes is not None and hasattr(db_module, "update_mission_notes"): db_module.update_mission_notes(mission_id, notes)

# ─── INIT FLASK ───────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "scorpius-dev-key")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"): return jsonify({"ok": False, "message": "Non authentifié"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def notify_async(func_name, *args):
    import notifications.telegram as tg
    func = getattr(tg, func_name, None)
    if func: threading.Thread(target=lambda: asyncio.run(func(*args)), daemon=True).start()

def get_theme():
    return session.get("theme", get_config().dashboard.get("theme", "dark"))

# ─── PWA ROUTES ───────────────────────────────────────────────────────────────
@app.route("/manifest.json")
def manifest(): return send_from_directory("static", "manifest.json")

@app.route("/sw.js")
def service_worker():
    resp = send_from_directory("static", "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp

@app.route("/offline")
def offline(): return render_template("offline.html", theme=get_theme())

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"): return redirect(url_for("missions"))
    if request.method == "POST":
        pwd = request.get_json().get("password", "") if request.is_json else request.form.get("password", "")
        if pwd == os.getenv("SCORPIUS_PASSWORD", "scorpius"):
            session["authenticated"] = True
            return jsonify({"ok": True, "message": "Connecté"}) if request.is_json else redirect(url_for("missions"))
        flash("Mot de passe incorrect.", "error")
    return render_template("login.html", theme=get_theme())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── PAGES HTML ───────────────────────────────────────────────────────────────
@app.route("/")
@app.route("/missions")
@login_required
def missions():
    return render_template(
        "missions.html",
        missions=get_missions(),
        theme=get_theme(),
        plateformes_dispo=get_plateformes_disponibles(),
        compteurs=get_compteurs_statut(),
        stats=get_stats_gains(),
    )

@app.route("/stats")
@login_required
def stats():
    return render_template(
        "stats.html", theme=get_theme(), gains=get_stats_gains(), evolution=get_evolution_mensuelle(), compteurs=get_compteurs_statut()
    )

@app.route("/settings")
@login_required
def settings():
    cfg = get_config()
    return render_template(
        "settings.html", theme=get_theme(), config=cfg, profil=cfg.profil, llm=cfg.llm, scraping=cfg.scraping,
        plateformes=getattr(cfg, 'plateformes', [])
    )

# ─── API REST ─────────────────────────────────────────────────────────────────
@app.route("/api/missions")
@login_required
def api_missions(): return jsonify({"ok": True, "data": get_missions()})

@app.route("/api/missions/<int:mission_id>/statut", methods=["PATCH"])
@login_required
def api_update_statut(mission_id):
    data = request.get_json(silent=True) or {}
    update_statut_mission(mission_id, data.get("statut"), data.get("gains"), data.get("notes"))
    return jsonify({"ok": True, "message": "Statut mis à jour"})

@app.route("/api/settings/theme", methods=["POST"])
@login_required
def api_set_theme():
    session["theme"] = request.get_json().get("theme", "dark")
    return jsonify({"ok": True})

# ─── FILTRES JINJA ────────────────────────────────────────────────────────────
@app.context_processor
def inject_globals(): return {"theme": get_theme()}

@app.template_filter("score_emoji")
def score_emoji(s): return "🟢" if s >= 80 else "🟡" if s >= 60 else "🟠" if s >= 40 else "🔴"

@app.template_filter("format_euros")
def format_euros(m): return f"{float(m):,.0f} €".replace(",", " ") if m is not None else "—"

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
