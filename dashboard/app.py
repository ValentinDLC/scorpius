
# ══════════════════════════════════════════════════════════════════════════════
# API — CONNEXION PLATEFORMES
# ══════════════════════════════════════════════════════════════════════════════

PLATEFORMES_LOGIN_URLS = {
    "codeur": "https://www.codeur.com/login",
    "malt": "https://www.malt.fr/login",
    "upwork": "https://www.upwork.com/ab/account-security/login",
    "freelancer": "https://www.freelancer.com/login",
    "free-work": "https://www.free-work.com/fr/login",
}


@app.route("/api/plateformes/<plateforme>/login-popup")
@login_required
def api_plateforme_login_popup(plateforme: str):
    url = PLATEFORMES_LOGIN_URLS.get(plateforme)
    if not url:
        return err("Plateforme non supportée", 404)
    return render_template("plateforme_login.html", plateforme=plateforme, login_url=url, theme=get_theme())


@app.route("/api/plateformes/<plateforme>/sauvegarder-session", methods=["POST"])
@login_required
def api_sauvegarder_session(plateforme: str):
    import subprocess
    def _save():
        url = PLATEFORMES_LOGIN_URLS.get(plateforme, "")
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
        return ok({"connected": True, "session_age_days": age_days, "expires_soon": age_days > 60})
    return ok({"connected": False})

