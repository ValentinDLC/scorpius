"""
dashboard/voice_profile_routes.py
Enrollment du profil vocal propriétaire.
"""

import logging
from flask import Blueprint, jsonify, render_template, request

from services.speaker_guard import enroll_me, has_me_profile

logger = logging.getLogger(__name__)

bp_voice_profile = Blueprint("voice_profile", __name__)


@bp_voice_profile.route("/voice-enroll")
def voice_enroll_page():
    return render_template("voice_enroll.html")


@bp_voice_profile.route("/api/voice-profile/status", methods=["GET"])
def voice_profile_status():
    return jsonify({
        "ok": True,
        "has_profile": has_me_profile(),
    })


@bp_voice_profile.route("/api/voice-profile/enroll", methods=["POST"])
def voice_profile_enroll():
    audio = request.get_data(cache=False)

    if not audio or len(audio) < 2048:
        return jsonify({
            "ok": False,
            "error": "audio trop court",
        }), 400

    try:
        result = enroll_me(audio)
        return jsonify(result)

    except Exception as e:
        logger.exception("❌ voice enroll failed")
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


def register_voice_profile_routes(app):
    if getattr(app, "_voice_profile_routes_registered", False):
        return

    app.register_blueprint(bp_voice_profile)
    app._voice_profile_routes_registered = True
    logger.info("🗣️ Routes voice profile enregistrées")
