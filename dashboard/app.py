"""
dashboard/app.py
Flask API REST + PWA — Scorpius v2
"""

import os
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, flash, send_from_directory
)
from dotenv import load_dotenv

from config.loader import get_config
from storage.db import (
    init_db, ping_db,
    get_missions, get_mission_by_id,
    get_stats_gains, get_compteurs_statut,
    get_evolution_mensuelle, get_plateformes_disponibles,
    update_statut_mission, delete_mission, upsert_mission,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# INIT FLASK
# ══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "scorpius-dev-key")
app.config.update(
    SESSION_COOKIE_HTTPONLY  = True,
    SESSION_COOKIE_SAMESITE  = "Lax",
    PERMANENT_SESSION_LIFETIME = timedelta(days=7),
)

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "Non authentifié"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def notify_async(func_name, *args):
    """Notification Telegram non bloquante."""
    import notifications.telegram as tg
    func = getattr(tg, func_name, None)
    if func:
        threading.Thread(
            target=lambda: asyncio.run(func(*args)),
            daemon=True
        ).start()


def get_theme() -> str:
    return session.get("theme", get_config().dashboard.get("theme", "dark"))


def ok(data=None, message="OK"):
    r = {"ok": True, "message": message}
    if data is not None:
        r["data"] = data
    return jsonify(r)


def err(message: str, code: int = 400):
    return jsonify({"ok": False, "message": message}), code


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ══════════════════════════════════════════════════════════════════════════════
# PWA
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory("static", "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/offline")
def offline():
    return render_template("offline.html", theme=get_theme())


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("missions"))

    if request.method == "POST":
        if request.is_json:
            password = (request.get_json() or {}).get("password", "")
        else:
            password = request.form.get("password", "")

        expected = os.getenv("SCORPIUS_PASSWORD", "scorpius")

        if password == expected:
            session["authenticated"] = True
            session.permanent = True
            if request.is_json:
                return ok(message="Connecté")
            flash("Connexion réussie.", "success")
            return redirect(url_for("missions"))
        else:
            if request.is_json:
                return err("Mot de passe incorrect", 401)
            flash("Mot de passe incorrect.", "error")

    return render_template("login.html", theme=get_theme())


@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for("login"))


@app.route("/api/auth/status")
def api_auth_status():
    return ok({
        "authenticated": bool(session.get("authenticated")),
        "theme": get_theme(),
    })


@app.route("/api/auth/voice-login", methods=["POST"])
def voice_login():
    return err("Voice auth pas encore activé", 501)


# ══════════════════════════════════════════════════════════════════════════════
# PAGES HTML
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
@app.route("/missions")
@login_required
def missions():
    statut    = request.args.get("statut", "")
    score_min = int(request.args.get("score_min", 0))
    plateforme = request.args.get("plateforme", "")
    recherche  = request.args.get("q", "").strip()

    toutes = get_missions(
        statut     = statut or None,
        score_min  = score_min,
        plateforme = plateforme or None,
        recherche  = recherche or None,
    )

    return render_template(
        "missions.html",
        missions          = toutes,
        theme             = get_theme(),
        filtre_statut     = statut,
        filtre_score_min  = score_min,
        filtre_plateforme = plateforme,
        filtre_recherche  = recherche,
        plateformes_dispo = get_plateformes_disponibles(),
        compteurs         = get_compteurs_statut(),
        stats             = get_stats_gains(),
    )


@app.route("/stats")
@login_required
def stats():
    return render_template(
        "stats.html",
        theme     = get_theme(),
        gains     = get_stats_gains(),
        evolution = get_evolution_mensuelle(),
        compteurs = get_compteurs_statut(),
    )


@app.route("/settings")
@login_required
def settings():
    cfg = get_config()

    def cfg_value(name, default=None):
        """
        Compatibilité avec plusieurs versions de ScorpiusConfig :
        - cfg.get("clé")
        - cfg.profil / cfg.llm / cfg.scraping
        - cfg.plateformes_actives
        """
        if hasattr(cfg, "get"):
            try:
                return cfg.get(name, default)
            except Exception:
                pass
        return getattr(cfg, name, default)

    profil = cfg_value("profil", {})
    llm = cfg_value("llm", {})
    scraping = cfg_value("scraping", {})
    vocal = cfg_value("vocal_id", {})

    plateformes = cfg_value("plateformes", None)
    if plateformes is None:
        plateformes = getattr(cfg, "plateformes_actives", [])

    if callable(plateformes):
        plateformes = plateformes()

    return render_template(
        "settings.html",
        theme=get_theme(),
        config=cfg,
        profil=profil,
        llm=llm,
        scraping=scraping,
        vocal=vocal,
        plateformes=plateformes or [],
    )


# ══════════════════════════════════════════════════════════════════════════════
# API — MISSIONS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/missions")
@login_required
def api_missions():
    missions = get_missions(
        statut     = request.args.get("statut") or None,
        score_min  = int(request.args.get("score_min", 0)),
        plateforme = request.args.get("plateforme") or None,
        recherche  = request.args.get("q") or None,
        limit      = int(request.args.get("limit", 100)),
    )
    return ok(missions)


@app.route("/api/missions", methods=["POST"])
def api_create_mission():
    """
    Reçoit les missions depuis le worker PC.
    Auth par X-Worker-Key (pas de session).
    """
    if not _check_worker_key():
        return err("Clé worker invalide", 403)

    data = request.get_json(silent=True)
    if not data:
        return err("Body JSON manquant")

    missions = data if isinstance(data, list) else [data]

    inserted = 0
    nouvelles = []
    for m in missions:
        if not m.get("url"):
            continue
        mission_id = upsert_mission(m)
        if mission_id:
            inserted += 1
            nouvelles.append(m)

    if inserted > 0:
        notify_async("notify_nouvelles_missions", nouvelles)

    return ok(
        {"inserted": inserted, "total": len(missions)},
        f"{inserted} nouvelle(s) mission(s)"
    )


@app.route("/api/missions/<int:mission_id>")
@login_required
def api_mission_detail(mission_id: int):
    mission = get_mission_by_id(mission_id)
    if not mission:
        return err("Mission introuvable", 404)
    return ok(mission)


@app.route("/api/missions/<int:mission_id>/statut", methods=["PATCH"])
@login_required
def api_update_statut(mission_id: int):
    data = request.get_json(silent=True) or {}
    nouveau_statut = data.get("statut")
    if not nouveau_statut:
        return err("Champ 'statut' manquant")

    mission = get_mission_by_id(mission_id)
    if not mission:
        return err("Mission introuvable", 404)

    ancien_statut = mission["statut"]

    try:
        update_statut_mission(
            mission_id = mission_id,
            statut     = nouveau_statut,
            gains      = float(data["gains"]) if data.get("gains") else None,
            notes      = data.get("notes"),
        )
    except ValueError as e:
        return err(str(e))

    if ancien_statut != nouveau_statut:
        notify_async(
            "notify_statut_change",
            mission["titre"],
            ancien_statut,
            nouveau_statut,
        )

    return ok(message=f"Statut → {nouveau_statut}")


@app.route("/api/missions/<int:mission_id>", methods=["DELETE"])
@login_required
def api_delete_mission(mission_id: int):
    if not get_mission_by_id(mission_id):
        return err("Mission introuvable", 404)
    delete_mission(mission_id)
    return ok(message="Mission supprimée")


@app.route("/api/missions/<int:mission_id>/relance", methods=["POST"])
@login_required
def api_relance(mission_id: int):
    mission = get_mission_by_id(mission_id)
    if not mission:
        return err("Mission introuvable", 404)

    data  = request.get_json(silent=True) or {}
    jours = int(data.get("jours", 0))

    if not jours and mission.get("date_statut"):
        try:
            date_statut = datetime.fromisoformat(
                str(mission["date_statut"]).replace("Z", "+00:00")
            )
            jours = (datetime.utcnow() - date_statut.replace(tzinfo=None)).days
        except Exception:
            jours = 0

    notify_async(
        "notify_relance",
        mission.get("client_nom", "Client inconnu"),
        mission["titre"],
        jours,
        mission.get("url", ""),
    )
    return ok(message="Relance envoyée sur Telegram")


# ══════════════════════════════════════════════════════════════════════════════
# API — STATS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/stats")
@login_required
def api_stats():
    return ok({
        "gains":     get_stats_gains(),
        "compteurs": get_compteurs_statut(),
        "evolution": get_evolution_mensuelle(),
    })


# ══════════════════════════════════════════════════════════════════════════════
# API — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/settings/theme", methods=["POST"])
@login_required
def api_set_theme():
    data  = request.get_json(silent=True) or {}
    theme = data.get("theme", "dark")
    if theme not in ("dark", "light"):
        return err("Thème invalide")
    session["theme"] = theme
    return ok({"theme": theme}, "Thème mis à jour")


@app.route("/api/settings/telegram-test", methods=["POST"])
@login_required
def api_telegram_test():
    from notifications.telegram import send_message, verify_bot
    info = run_async(verify_bot())
    if not info["ok"]:
        return err(f"Bot invalide : {info['erreur']}")
    cfg  = get_config()
    sent = run_async(send_message(
        cfg.telegram_chat_id,
        f"🦂 <b>Scorpius</b> — Test OK ✅\n"
        f"<i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>",
    ))
    return ok(message="Message test envoyé ✅") if sent else err("Échec Telegram")


@app.route("/api/settings/db-status")
@login_required
def api_db_status():
    connected = ping_db()
    return ok({"connected": connected})


# ══════════════════════════════════════════════════════════════════════════════
# API — SCRAPING
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/scraping/status")
@login_required
def api_scraping_status():
    compteurs = get_compteurs_statut()
    missions  = get_missions(limit=1)
    dernier   = missions[0].get("date_scraping") if missions else None
    return ok({
        "dernier_scraping": dernier,
        "total_missions":   compteurs["total"],
        "worker_actif":     bool(_last_worker_ping),
    })


@app.route("/api/scraping/trigger", methods=["POST"])
@login_required
def api_scraping_trigger():
    """Dashboard → envoie commande scrape au worker PC."""
    _enqueue_command("scrape_now")
    return ok(message="Commande scrape_now envoyée au worker")


# ══════════════════════════════════════════════════════════════════════════════
# WORKER — Communication PC ↔ Serveur
# (auth par X-Worker-Key, pas de session Flask)
# ══════════════════════════════════════════════════════════════════════════════

_worker_commands: list[dict] = []
_worker_lock     = threading.Lock()
_last_worker_ping: str = ""


def _check_worker_key() -> bool:
    """Vérifie le header X-Worker-Key."""
    expected   = os.getenv("WORKER_API_KEY", "scorpius-worker-key")
    worker_key = request.headers.get("X-Worker-Key", "")
    return worker_key == expected


def _enqueue_command(cmd: str):
    with _worker_lock:
        _worker_commands.append({
            "command":   cmd,
            "timestamp": datetime.utcnow().isoformat(),
        })


@app.route("/api/worker/ping", methods=["POST"])
def api_worker_ping():
    """
    Worker PC signale qu'il est actif.
    Appelé toutes les 30s par le worker.
    """
    if not _check_worker_key():
        return err("Clé worker invalide", 403)

    global _last_worker_ping
    data = request.get_json(silent=True) or {}
    _last_worker_ping = datetime.utcnow().isoformat()

    logger.info(f"Worker ping — {data.get('hostname', 'unknown')}")
    return ok({"status": "pong", "timestamp": _last_worker_ping})


@app.route("/api/worker/commands")
def api_worker_commands():
    """
    Worker poll ses commandes toutes les 30s.
    Retourne la liste et la vide.
    """
    if not _check_worker_key():
        return err("Clé worker invalide", 403)

    with _worker_lock:
        cmds = list(_worker_commands)
        _worker_commands.clear()

    return ok(cmds)


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXT PROCESSORS & FILTRES JINJA
# ══════════════════════════════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    try:
        profil_metier = get_config().profil.get("metier", "Freelancer")
    except Exception:
        profil_metier = "Freelancer"
    return {
        "theme":         get_theme(),
        "profil_metier": profil_metier,
        "annee":         datetime.now().year,
        "version":       "2.0.0",
        "now":           datetime.now(),
    }


@app.template_filter("score_class")
def score_class(score: int) -> str:
    if score >= 80: return "score-high"
    if score >= 60: return "score-medium"
    if score >= 40: return "score-low"
    return "score-very-low"


@app.template_filter("score_emoji")
def score_emoji(score: int) -> str:
    if score >= 80: return "🟢"
    if score >= 60: return "🟡"
    if score >= 40: return "🟠"
    return "🔴"


@app.template_filter("statut_label")
def statut_label(statut: str) -> str:
    return {
        "proposee":   "Proposée",
        "en_attente": "En attente",
        "en_cours":   "En cours",
        "terminee":   "Terminée",
        "refusee":    "Refusée",
    }.get(statut, statut.capitalize())


@app.template_filter("format_date")
def format_date(date_str) -> str:
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return str(date_str)[:16]


@app.template_filter("format_euros")
def format_euros(montant) -> str:
    if montant is None:
        return "—"
    try:
        return f"{float(montant):,.0f} €".replace(",", " ")
    except Exception:
        return str(montant)


@app.template_filter("format_budget")
def format_budget(mission) -> str:
    if not isinstance(mission, dict):
        return "—"
    bmin   = mission.get("budget_min")
    bmax   = mission.get("budget_max")
    devise = mission.get("devise", "€")
    if bmin and bmax and int(float(bmin)) != int(float(bmax)):
        return f"{int(float(bmin))}–{int(float(bmax))} {devise}"
    elif bmin:
        return f"{int(float(bmin))}+ {devise}"
    elif bmax:
        return f"≤{int(float(bmax))} {devise}"
    return "Non précisé"


# ══════════════════════════════════════════════════════════════════════════════
# ERREURS
# ══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return err("Route introuvable", 404)
    return render_template("404.html", theme=get_theme()), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 : {e}")
    if request.path.startswith("/api/"):
        return err("Erreur serveur", 500)
    return render_template("500.html", theme=get_theme()), 500


# ══════════════════════════════════════════════════════════════════════════════
# LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

def create_app():
    init_db()
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg  = get_config()
    port = cfg.dashboard.get("port", 5000)

    init_db()

    print(f"""
╔══════════════════════════════════════════╗
║       Scorpius v2 — Dashboard PWA        ║
╠══════════════════════════════════════════╣
║  URL  : http://localhost:{port}             ║
║  DB   : PostgreSQL (Supabase)             ║
╚══════════════════════════════════════════╝
    """)

    # Run
port = int(os.getenv("PORT", 8080))  # Force 8080
app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)