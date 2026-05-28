from flask_sock import Sock
import logging
import os
from datetime import datetime

from storage.db import create_call_record

sock = Sock()
logger = logging.getLogger(__name__)
_ws_audio_registered = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        save_audio = _env_bool("VOICE_SAVE_AUDIO", True) and not privacy_mode

        logger.info(
            f"🎙️ WS connecté → prospect {prospect_id} "
            f"(privacy={privacy_mode}, save_audio={save_audio})"
        )

        buffer = bytearray() if save_audio else None
        bytes_received = 0
        started_at = datetime.utcnow()

        try:
            while True:
                data = ws.receive(timeout=60)

                if data is None:
                    break

                if isinstance(data, bytes):
                    bytes_received += len(data)

                    # Mode démo : on garde l'audio complet pour fichier .webm
                    if save_audio and buffer is not None:
                        buffer.extend(data)

                    # Mode privacy : aucun audio n'est accumulé ni sauvegardé.
                    # Les chunks sont traités puis immédiatement oubliés.
                    # Le STT live sera branché ici à l'étape suivante.

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
                    status=status,
                    privacy_mode=privacy_mode,
                    audio_saved=audio_saved,
                )

                logger.info(
                    f"📞 Call terminé prospect={prospect_id} "
                    f"bytes={bytes_received/1024:.1f}KB duration={duration_sec:.1f}s "
                    f"call_id={call_id} audio_saved={audio_saved}"
                )

            else:
                logger.info(f"⚠️ Buffer trop petit ({bytes_received}B), ignoré")

            logger.info(f"🔌 WS fermé → prospect {prospect_id}")
