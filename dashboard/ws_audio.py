from flask_sock import Sock
import logging
import os
import json
from datetime import datetime

from storage.db import create_call_record
from services.stt import transcribe_audio_bytes

sock = Sock()
logger = logging.getLogger(__name__)
_ws_audio_registered = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _safe_ws_send(ws, payload: dict) -> None:
    try:
        ws.send(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"WS send ignored: {e}")


def init_ws_audio(app):
    global _ws_audio_registered

    if _ws_audio_registered:
        logger.info("🎙️ WS audio déjà initialisé")
        return

    sock.init_app(app)
    _ws_audio_registered = True
    logger.info("🎙️ WS audio initialisé")

    @sock.route('/ws/audio/<int:prospect_id>')
    def audio_stream(ws, prospect_id):
        privacy_mode = _env_bool("VOICE_PRIVACY_MODE", False)
        live_stt = _env_bool("VOICE_LIVE_STT", False)

        # En privacy, on force zéro sauvegarde audio.
        save_audio = _env_bool("VOICE_SAVE_AUDIO", True) and not privacy_mode

        live_interval_sec = _env_float("VOICE_LIVE_STT_INTERVAL_SEC", 5.0)
        live_min_bytes = _env_int("VOICE_LIVE_STT_MIN_BYTES", 12000)

        logger.info(
            f"🎙️ WS connecté → prospect {prospect_id} "
            f"(privacy={privacy_mode}, save_audio={save_audio}, live_stt={live_stt})"
        )

        _safe_ws_send(ws, {
            "type": "server_status",
            "privacy_mode": privacy_mode,
            "save_audio": save_audio,
            "live_stt": live_stt,
        })

        buffer = bytearray() if save_audio else None

        # Buffer RAM temporaire pour STT live.
        # En mode privacy, il n'est jamais écrit sur disque et sera clear() en finally.
        live_buffer = bytearray() if live_stt else None

        bytes_received = 0
        started_at = datetime.utcnow()
        last_stt_at = started_at
        last_transcript = ""

        try:
            while True:
                data = ws.receive(timeout=60)

                if data is None:
                    break

                if isinstance(data, bytes):
                    bytes_received += len(data)

                    if save_audio and buffer is not None:
                        buffer.extend(data)

                    if live_stt and live_buffer is not None:
                        live_buffer.extend(data)

                        elapsed_since_stt = (
                            datetime.utcnow() - last_stt_at
                        ).total_seconds()

                        if (
                            len(live_buffer) >= live_min_bytes
                            and elapsed_since_stt >= live_interval_sec
                        ):
                            try:
                                result = transcribe_audio_bytes(bytes(live_buffer))
                                text = (result.get("text") or "").strip()

                                if text and text != last_transcript:
                                    last_transcript = text
                                    _safe_ws_send(ws, {
                                        "type": "transcript",
                                        "partial": True,
                                        "text": text,
                                        "privacy_mode": privacy_mode,
                                    })
                                    logger.info(
                                        f"📝 Live transcript prospect={prospect_id}: "
                                        f"{text[:120]}"
                                    )

                                last_stt_at = datetime.utcnow()

                            except Exception as stt_e:
                                logger.warning(f"⚠️ STT live failed: {stt_e}")
                                _safe_ws_send(ws, {
                                    "type": "stt_error",
                                    "error": str(stt_e),
                                })
                                last_stt_at = datetime.utcnow()

                kb = bytes_received / 1024
                if kb > 0 and int(kb) % 32 == 0 and kb - int(kb) < 0.5:
                    logger.info(f"📦 {prospect_id}: {kb:.1f} KB reçus")

        except Exception as e:
            msg = str(e)
            if "Connection closed: 1005" in msg or "Connection closed: 1001" in msg:
                logger.info(f"🔌 WS fermé normalement {prospect_id}: {msg}")
            else:
                logger.error(f"❌ WS erreur {prospect_id}: {e}")

        finally:
            duration_sec = max(0.0, (datetime.utcnow() - started_at).total_seconds())

            if bytes_received > 512:
                path = None

                if save_audio and buffer is not None and len(buffer) > 512:
                    tmp_dir = "tmp_audio"
                    os.makedirs(tmp_dir, exist_ok=True)

                    ts = datetime.now().strftime("%H%M%S_%f")
                    path = os.path.join(tmp_dir, f"call_{prospect_id}_{ts}.webm")

                    with open(path, "wb") as f:
                        f.write(buffer)

                    status = "recording"
                    audio_saved = True
                    logger.info(f"💾 Audio sauvegardé → {path}")

                else:
                    status = "privacy_no_audio"
                    audio_saved = False
                    logger.info("🔒 Mode privacy actif : aucun audio sauvegardé")

                call_id = create_call_record(
                    prospect_id=prospect_id,
                    audio_path=path,
                    duration_sec=duration_sec,
                    transcript=None if privacy_mode else last_transcript or None,
                    status=status,
                    privacy_mode=privacy_mode,
                    audio_saved=audio_saved,
                )

                _safe_ws_send(ws, {
                    "type": "call_saved",
                    "call_id": call_id,
                    "status": status,
                    "audio_saved": audio_saved,
                    "privacy_mode": privacy_mode,
                    "duration_sec": duration_sec,
                })

                logger.info(
                    f"📞 Call terminé prospect={prospect_id} "
                    f"bytes={bytes_received/1024:.1f}KB duration={duration_sec:.1f}s "
                    f"call_id={call_id} audio_saved={audio_saved}"
                )

            else:
                logger.info(f"⚠️ Buffer trop petit ({bytes_received}B), ignoré")

            if live_buffer is not None:
                live_buffer.clear()

            if buffer is not None:
                buffer.clear()

            logger.info(f"🔌 WS fermé → prospect {prospect_id}")
