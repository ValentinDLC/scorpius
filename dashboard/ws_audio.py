from flask_sock import Sock
import logging
import os
from datetime import datetime

from storage.db import create_call_record

sock = Sock()
logger = logging.getLogger(__name__)
_ws_audio_registered = False


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
        logger.info(f"🎙️ WS connecté → prospect {prospect_id}")

        buffer = bytearray()
        started_at = datetime.utcnow()

        try:
            while True:
                data = ws.receive(timeout=60)

                if data is None:
                    break

                if isinstance(data, bytes):
                    buffer.extend(data)

                kb = len(buffer) / 1024
                if kb > 0 and int(kb) % 32 == 0 and kb - int(kb) < 0.5:
                    logger.info(f"📦 {prospect_id}: {kb:.1f} KB")

        except Exception as e:
            msg = str(e)
            if "Connection closed: 1005" in msg or "Connection closed: 1001" in msg:
                logger.info(f"🔌 WS fermé normalement {prospect_id}: {msg}")
            else:
                logger.error(f"❌ WS erreur {prospect_id}: {e}")

        finally:
            duration_sec = max(0.0, (datetime.utcnow() - started_at).total_seconds())

            if len(buffer) > 512:
                tmp_dir = "tmp_audio"
                os.makedirs(tmp_dir, exist_ok=True)

                ts = datetime.now().strftime("%H%M%S_%f")
                path = os.path.join(tmp_dir, f"call_{prospect_id}_{ts}.webm")

                with open(path, "wb") as f:
                    f.write(buffer)

                call_id = create_call_record(
                    prospect_id=prospect_id,
                    audio_path=path,
                    duration_sec=duration_sec,
                    status="recording",
                )

                logger.info(
                    f"💾 {len(buffer)/1024:.1f} KB → {path} "
                    f"(duration={duration_sec:.1f}s, call_id={call_id})"
                )
            else:
                logger.info(f"⚠️ Buffer trop petit ({len(buffer)}B), ignoré")

            logger.info(f"🔌 WS fermé → prospect {prospect_id}")
