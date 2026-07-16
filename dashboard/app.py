"""
dashboard/app.py
Flask API REST + PWA — Scorpius v2
"""

import sys
import os as os_sys
sys.path.insert(0, os_sys.path.join(os_sys.path.dirname(__file__), '..', 'data'))

import os
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps

from dashboard.ws_audio import init_ws_audio
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, flash, send_from_directory
)
from dotenv import load_dotenv
import storage.db as storage_db

from config.loader import get_config
from storage.db import (
    init_db, ping_db,
    get_missions, get_mission_by_id,
    get_stats_gains, get_compteurs_statut,
    get_evolution_mensuelle, get_plateformes_disponibles,
    update_statut_mission, delete_mission, upsert_mission,
)

from dashboard.prospects_routes import register_prospects_routes
from dashboard.business_routes import register_business_routes
from dashboard.calls_routes import register_calls_routes
from dashboard.voice_profile_routes import register_voice_profile_routes
from storage.prospects import init_prospects_db

load_dotenv()
logger = logging.getLogger(__name__)
print("DEBUG SMTP_USER:", repr(os.getenv("SMTP_USER")))
print("DEBUG SMTP_PASSWORD len:", len(os.getenv("SMTP_PASSWORD") or ""))






# ══════════════════════════════════════════════════════════════════════════════
# INIT FLASK
# ══════════════════════════════════════════════════════════════════════════════

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)  # racine scorpius

app = Flask(__name__, 
            template_folder=os.path.join(ROOT_DIR, "web", "templates"), 
            static_folder=os.path.join(ROOT_DIR, "web", "static"))
init_ws_audio(app)  # init websocket audio for run.py
register_calls_routes(app)  # calls API
register_voice_profile_routes(app)  # voice profile API
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
# PROSPECTS — SPRINT 1
# ══════════════════════════════════════════════════════════════════════════════
register_prospects_routes(app, login_required, ok, err, run_async)
register_business_routes(app, login_required, get_theme)


# ══════════════════════════════════════════════════════════════════════════════
# PWA
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/health', methods=['GET'])
def health():
    return {"status": "ok"}, 200

@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js")
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
            payload  = request.get_json(silent=True) or {}
            password = payload.get("password", "") or ""
            email    = payload.get("email", "") or ""
        else:
            password = request.form.get("password", "") or ""
            email    = request.form.get("email", "") or ""

        password = str(password)
        email    = (email or "").strip().lower()

        if email:
            from storage.users import get_user_by_email, verify_user_password
            user = get_user_by_email(email)

            if user and verify_user_password(user, password):
                # Compte non verifie
                if not user.get("email_verified"):
                    from storage.users import generate_verification_code, set_verification_code
                    from services.email_service import send_verification_code as send_code
                    code = generate_verification_code()
                    set_verification_code(email, code)
                    send_code(email, code)
                    session["pending_verify_email"] = email
                    if request.is_json:
                        return err("Email non verifie — code renvoye", 403)
                    flash("Votre email n\'est pas verifie. Un nouveau code vous a ete envoye.", "error")
                    return redirect(url_for("verify_email"))

                session["authenticated"] = True
                session.permanent        = True
                session["user_id"]       = int(user["id"])
                session["user_nom"]      = user.get("nom") or "Utilisateur"
                if request.is_json:
                    return ok(message="Connecte")
                flash("Connexion reussie.", "success")
                return redirect(url_for("missions"))

            if request.is_json:
                return err("Email ou mot de passe incorrect", 401)
            flash("Email ou mot de passe incorrect.", "error")
            return render_template("login.html", theme=get_theme())

        # Connexion admin par mot de passe seul
        expected = os.getenv("SCORPIUS_PASSWORD", "scorpius")
        if password == expected:
            session["authenticated"] = True
            session.permanent        = True
            session["user_id"]       = 0
            session["user_nom"]      = "Admin"
            if request.is_json:
                return ok(message="Connecte")
            flash("Connexion reussie.", "success")
            return redirect(url_for("missions"))

        if request.is_json:
            return err("Mot de passe incorrect", 401)
        flash("Mot de passe incorrect.", "error")
        return render_template("login.html", theme=get_theme())

    return render_template("login.html", theme=get_theme())


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("authenticated"):
        return redirect(url_for("missions"))

    if request.method == "POST":
        nom      = (request.form.get("nom") or "").strip()
        email    = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm  = request.form.get("confirm_password") or ""

        if not nom or not email or not password:
            flash("Nom, email et mot de passe sont requis.", "error")
            return render_template("register.html", theme=get_theme())

        if password != confirm:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("register.html", theme=get_theme())

        from storage.users import create_user, generate_verification_code, set_verification_code
        from services.email_service import send_verification_code as send_code

        user_id = create_user(nom=nom, email=email, password=password)
        if not user_id:
            flash("Impossible de creer le compte (email deja utilise ?).", "error")
            return render_template("register.html", theme=get_theme())

        code = generate_verification_code()
        set_verification_code(email, code)
        send_code(email, code)

        session["pending_verify_email"] = email
        flash("Compte cree. Verifiez votre email et entrez le code.", "success")
        return redirect(url_for("verify_email"))

    return render_template("register.html", theme=get_theme())


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email = session.get("pending_verify_email", "")

    if request.method == "POST":
        code = (request.form.get("code") or "").strip()

        if not email:
            flash("Session expiree. Reconnectez-vous.", "error")
            return redirect(url_for("login"))

        from storage.users import verify_email_code
        if verify_email_code(email, code):
            session.pop("pending_verify_email", None)
            flash("Email verifie. Vous pouvez vous connecter.", "success")
            return redirect(url_for("login"))

        flash("Code incorrect ou expire.", "error")

    return render_template("verify_email.html", email=email, theme=get_theme())


@app.route("/resend-code")
def resend_code():
    email = session.get("pending_verify_email", "")
    if not email:
        flash("Session expiree.", "error")
        return redirect(url_for("login"))

    from storage.users import generate_verification_code, set_verification_code, get_user_by_email
    from services.email_service import send_verification_code as send_code

    user = get_user_by_email(email)
    if not user:
        flash("Compte introuvable.", "error")
        return redirect(url_for("login"))

    if user.get("email_verified"):
        flash("Cet email est deja verifie.", "success")
        return redirect(url_for("login"))

    code = generate_verification_code()
    set_verification_code(email, code)
    send_code(email, code)
    flash("Un nouveau code a ete envoye.", "success")
    return redirect(url_for("verify_email"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()

        if email:
            from storage.users import get_user_by_email
            from services.email_service import send_password_reset_link
            from itsdangerous import URLSafeTimedSerializer

            user = get_user_by_email(email)
            if user:
                s         = URLSafeTimedSerializer(app.secret_key)
                token     = s.dumps(email, salt="password-reset")
                base_url  = os.getenv("APP_BASE_URL", "http://localhost:5000")
                reset_url = f"{base_url}/reset-password/{token}"
                send_password_reset_link(email, reset_url)

        # Reponse identique que l'email existe ou non
        flash("Si un compte existe pour cet email, un lien a ete envoye.", "success")
        return render_template("forgot_password.html", theme=get_theme())

    return render_template("forgot_password.html", theme=get_theme())


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

    s     = URLSafeTimedSerializer(app.secret_key)
    email = None

    try:
        email = s.loads(token, salt="password-reset", max_age=3600)
    except SignatureExpired:
        flash("Ce lien a expire. Faites une nouvelle demande.", "error")
        return render_template("reset_password.html", valid_token=False, token=token, theme=get_theme())
    except BadSignature:
        flash("Lien invalide.", "error")
        return render_template("reset_password.html", valid_token=False, token=token, theme=get_theme())

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm  = request.form.get("confirm_password") or ""

        if not password:
            flash("Le mot de passe ne peut pas etre vide.", "error")
            return render_template("reset_password.html", valid_token=True, token=token, theme=get_theme())

        if password != confirm:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("reset_password.html", valid_token=True, token=token, theme=get_theme())

        from storage.users import update_password
        if update_password(email, password):
            flash("Mot de passe mis a jour. Vous pouvez vous connecter.", "success")
            return redirect(url_for("login"))

        flash("Erreur lors de la mise a jour.", "error")

    return render_template("reset_password.html", valid_token=True, token=token, theme=get_theme())

@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for("index"))


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
def index():
    """Page d'accueil publique — vitrine commerciale Scorpius."""
    return render_template("index.html", theme=get_theme())


@app.route("/missions")
@login_required
def missions():
    from storage.prospects import list_prospects

    # Une session authentifiée doit toujours avoir un utilisateur identifié.
    # On ne bascule surtout pas automatiquement vers user_id=0.
    user_id = session.get("user_id")
    if user_id is None:
        session.clear()
        flash("Session invalide. Merci de vous reconnecter.", "error")
        return redirect(url_for("login"))

    missions_list = list_prospects(
        user_id=int(user_id),
        statut="mission",
        limit=1000,
    )

    # Sécurise le rendu HTML même si une ancienne ligne de base est incomplète.
    # Les données restent des prospects, pas des anciennes missions freelance.
    for mission in missions_list:
        mission.setdefault("id", 0)
        mission.setdefault("nom", "Entreprise sans nom")
        mission.setdefault("score_audit", 0)
        mission.setdefault("secteur", "")
        mission.setdefault("ville", "")
        mission.setdefault("telephone", "")
        mission.setdefault("url_site", "")
        mission.setdefault("google_maps_url", "")
        mission.setdefault("audit_mobile", False)
        mission.setdefault("audit_gmb", False)
        mission.setdefault("seo_title", False)

    return render_template(
        "missions.html",
        theme=get_theme(),
        missions=missions_list,
    )






@app.route("/prospects")
@login_required
def prospects():
    """Page prospects — Google Places cold calling (Sprint 1)"""
    return render_template("prospects.html", theme=get_theme())

@app.route("/stats")
@login_required
def stats():
    from storage.prospects import get_prospect_stats

    user_id = session.get("user_id", -1)

    return render_template(
        "stats.html",
        theme=get_theme(),
        stats=get_prospect_stats(user_id),
    )

@app.route("/settings")
@login_required
def settings():
    return render_template(
        "settings.html",
        theme=get_theme(),
        account_id=session.get("user_id"),
    )

# ══════════════════════════════════════════════════════════════════════════════
# API — MISSIONS LEGACY (TEMPORAIREMENT DÉSACTIVÉE)
# Les missions à venir utilisent maintenant les prospects sélectionnés
# depuis la page Prospects. Les anciennes données restent en base,
# mais elles ne sont plus accessibles depuis le dashboard.

@app.route("/api/missions", defaults={"legacy_path": ""}, methods=["GET", "POST"])
@app.route(
    "/api/missions/<path:legacy_path>",
    methods=["GET", "POST", "PATCH", "DELETE"],
)
@login_required
def api_legacy_missions_disabled(legacy_path):
    return err(
        "Ancien module Missions temporairement désactivé. "
        "Utilise Prospects puis Missions à venir.",
        410,
    )


# API — STATS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/stats")
@login_required
def api_stats():
    from storage.prospects import get_prospect_stats

    user_id = session.get("user_id", -1)
    return ok(get_prospect_stats(user_id))

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
    return ok({
        "active": False,
        "message": (
            "Fonction mise de côté : les entreprises sont désormais "
            "recherchées depuis la page Prospects."
        ),
    })

@app.route("/api/scraping/trigger", methods=["POST"])
@login_required
def api_scraping_trigger():
    return err(
        "Cette fonction est temporairement désactivée. "
        "Utilise la recherche d'entreprises dans Prospects.",
        410,
    )

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
# API — CONNEXION PLATEFORMES
# ══════════════════════════════════════════════════════════════════════════════


DEFAULT_PLATEFORMES_LOGIN_URLS = {
    "codeur": "https://www.codeur.com/login",
    "malt": "https://www.malt.fr/login",
    "upwork": "https://www.upwork.com/ab/account-security/login",
    "freelancer": "https://www.freelancer.com/login",
    "free-work": "https://www.free-work.com/fr/login",
}


def _plateformes_config_list():
    cfg = get_config()
    plateformes = None

    if hasattr(cfg, "get"):
        try:
            plateformes = cfg.get("plateformes", None)
        except Exception:
            plateformes = None

    if plateformes is None:
        plateformes = getattr(cfg, "plateformes", None)

    if plateformes is None:
        plateformes = getattr(cfg, "plateformes_actives", [])

    if callable(plateformes):
        plateformes = plateformes()

    return plateformes or []


def _plateforme_value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _slug_from_platform_url(url: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    for suffix in (".com", ".fr", ".io", ".net", ".co", ".eu"):
        if host.endswith(suffix):
            host = host[:-len(suffix)]
            break
    return host.replace(".", "-").strip("-")


def _domain_from_platform_url(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def _get_plateforme_config(plateforme: str):
    for item in _plateformes_config_list():
        slug = _plateforme_value(item, "slug", "")
        if slug and str(slug).strip().lower() == plateforme:
            return item

        url = _plateforme_value(item, "url", "")
        if url and _slug_from_platform_url(url) == plateforme:
            return item

    return None


def _get_plateforme_label(plateforme: str) -> str:
    item = _get_plateforme_config(plateforme)
    if item:
        label = _plateforme_value(item, "label", "")
        if label:
            return str(label)
    return plateforme.replace("-", " ").title()


def _get_plateforme_login_url(plateforme: str) -> str:
    item = _get_plateforme_config(plateforme)
    if item:
        login_url = _plateforme_value(item, "login_url", "")
        if login_url:
            return str(login_url)

        url = _plateforme_value(item, "url", "")
        if url:
            return str(url)

    return DEFAULT_PLATEFORMES_LOGIN_URLS.get(plateforme, "")


def _get_plateforme_domain(plateforme: str) -> str:
    item = _get_plateforme_config(plateforme)
    if item:
        domain = _plateforme_value(item, "domain", "")
        if domain:
            return str(domain).lower().replace("www.", "")

        login_url = _plateforme_value(item, "login_url", "")
        if login_url:
            return _domain_from_platform_url(login_url)

        url = _plateforme_value(item, "url", "")
        if url:
            return _domain_from_platform_url(url)

    login_url = DEFAULT_PLATEFORMES_LOGIN_URLS.get(plateforme, "")
    if login_url:
        return _domain_from_platform_url(login_url)

    return ""


def _get_plateforme_auth_mode(plateforme: str) -> str:
    item = _get_plateforme_config(plateforme)
    if item:
        return str(_plateforme_value(item, "auth_mode", "browser_cookies") or "browser_cookies")
    return "browser_cookies"

@app.route("/api/plateformes/<plateforme>/login-popup")
@login_required
def api_plateforme_login_popup(plateforme: str):
    url = _get_plateforme_login_url(plateforme)
    if not url:
        return err("Plateforme non supportée", 404)
    return render_template(
        "plateforme_login.html",
        plateforme=plateforme,
        login_url=url,
        theme=get_theme(),
    )


@app.route("/api/plateformes/<plateforme>/sauvegarder-session", methods=["POST"])
@login_required
def api_sauvegarder_session(plateforme: str):
    import subprocess
    def _save():
        url = _get_plateforme_login_url(plateforme)
        if url:
            subprocess.run(["python3", "worker.py", "--login", url])
    threading.Thread(target=_save, daemon=True).start()
    return ok(message=f"Session {plateforme} en cours de sauvegarde...")


@app.route("/api/plateformes/<plateforme>/status")
@login_required
def api_plateforme_status(plateforme: str):
    from pathlib import Path
    import time
    session_file = Path("data/sessions") / f"{plateforme}_session.json"
    if session_file.exists():
        age_days = int((time.time() - session_file.stat().st_mtime) / 86400)
        return ok({
            "connected": True,
            "session_age_days": age_days,
            "expires_soon": age_days > 60,
        })
    return ok({"connected": False})

# ══════════════════════════════════════════════════════════════════════════════

def _plateformes_config_list():
    cfg = get_config()
    plateformes = None

    if hasattr(cfg, "get"):
        try:
            plateformes = cfg.get("plateformes", None)
        except Exception:
            plateformes = None

    if plateformes is None:
        plateformes = getattr(cfg, "plateformes", None)

    if plateformes is None:
        plateformes = getattr(cfg, "plateformes_actives", [])

    if callable(plateformes):
        plateformes = plateformes()

    return plateformes or []


def _plateforme_value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _slug_from_platform_url(url: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    for suffix in (".com", ".fr", ".io", ".net", ".co", ".eu"):
        if host.endswith(suffix):
            host = host[:-len(suffix)]
            break
    return host.replace(".", "-").strip("-")


def _domain_from_platform_url(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def _get_plateforme_config(plateforme: str):
    for item in _plateformes_config_list():
        url = _plateforme_value(item, "url", "")
        if url and _slug_from_platform_url(url) == plateforme:
            return item
    return None


@app.route("/api/plateformes/<plateforme>/importer-cookies", methods=["POST"])
@login_required
def api_importer_cookies_plateforme(plateforme: str):
    import subprocess

    payload = request.get_json(silent=True) or {}
    browser = str(payload.get("browser", "auto")).strip().lower() or "auto"
    domain = _get_plateforme_domain(plateforme)

    if not domain:
        return err("Domaine plateforme introuvable", 404)

    cmd = [
        "python3",
        "tools/import_browser_session.py",
        "--slug", plateforme,
        "--domain", domain,
        "--browser", browser,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout or result.stderr or "").strip()

    if result.returncode != 0:
        return err(output or f"Import cookies impossible pour {plateforme}", 400)

    return ok(
        {"plateforme": plateforme, "browser": browser, "domain": domain},
        output or f"Session {plateforme} importée",
    )
# LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

def create_app():
    init_db()
    init_prospects_db()
    return app



@app.route("/test-audio")
def test_audio():
    return render_template("test_audio.html")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg  = get_config()
    port = cfg.dashboard.get("port", 5000)

    init_db()
    init_prospects_db()

    db_label = (
        "SQLite local (fallback)"
        if storage_db._using_sqlite
        else "PostgreSQL (Supabase)"
    )

    print(f"""
╔══════════════════════════════════════════╗
║       Scorpius v2 — Dashboard PWA        ║
╠══════════════════════════════════════════╣
║  URL  : http://localhost:{port}             ║
║  DB   : {db_label:<34}║
╚══════════════════════════════════════════╝
    """)

    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
