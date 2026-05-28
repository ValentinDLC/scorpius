"""
dashboard/calls_routes.py
API appels / transcription.
"""

import os
import logging
from flask import Blueprint, jsonify

from storage.db import (
    get_call_by_id,
    update_call_status,
    update_call_transcript,
)
from services.stt import transcribe_audio

logger = logging.getLogger(__name__)

bp_calls = Blueprint("calls", __name__)


@bp_calls.route("/api/calls/<int:call_id>/transcribe", methods=["POST"])
def transcribe_call(call_id: int):
    call = get_call_by_id(call_id)

    if not call:
        return jsonify({
            "ok": False,
            "error": f"call_id {call_id} introuvable",
        }), 404

    audio_path = call.get("audio_path")

    if not audio_path or not os.path.exists(audio_path):
        update_call_status(call_id, "error")
        return jsonify({
            "ok": False,
            "error": f"audio_path introuvable: {audio_path}",
        }), 404

    try:
        update_call_status(call_id, "transcribing")

        result = transcribe_audio(audio_path)

        update_call_transcript(
            call_id=call_id,
            transcript=result["text"],
            status="transcribed",
            duration_sec=result.get("duration") or call.get("duration_sec"),
        )

        return jsonify({
            "ok": True,
            "call_id": call_id,
            "status": "transcribed",
            "language": result.get("language"),
            "duration": result.get("duration"),
            "transcript": result["text"],
        })

    except Exception as e:
        logger.exception(f"❌ Transcription failed call_id={call_id}")
        update_call_status(call_id, "error")
        return jsonify({
            "ok": False,
            "call_id": call_id,
            "error": str(e),
        }), 500


def register_calls_routes(app):
    if getattr(app, "_calls_routes_registered", False):
        return

    app.register_blueprint(bp_calls)
    app._calls_routes_registered = True
    logger.info("📞 Routes calls enregistrées")
