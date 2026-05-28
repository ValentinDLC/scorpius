"""
services/stt.py
Transcription audio via faster-whisper.
"""

import os
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL = None


def _get_model():
    global _MODEL

    if _MODEL is not None:
        return _MODEL

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper non installé. Lance: python3 -m pip install faster-whisper"
        ) from e

    model_size = os.getenv("WHISPER_MODEL", "small")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    logger.info(
        f"🧠 Chargement Whisper model={model_size} device={device} compute={compute_type}"
    )

    _MODEL = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
    )

    return _MODEL


def transcribe_audio(audio_path: str, language: str = "fr") -> dict:
    """
    Transcrit un fichier audio/webm.
    Retourne: {text, language, duration}
    """
    path = Path(audio_path)

    if not path.exists():
        raise FileNotFoundError(f"Audio introuvable: {audio_path}")

    model = _get_model()

    initial_prompt = os.getenv(
        "WHISPER_INITIAL_PROMPT",
        "Conversation téléphonique de prospection commerciale en français. "
        "Le vocabulaire peut inclure: site internet, automatisation, authentification, "
        "développement web, audit, SEO, performance, mobile, devis, rendez-vous, objection client."
    )

    segments, info = model.transcribe(
        str(path),
        language=language,
        vad_filter=True,
        beam_size=3,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt,
    )

    text_parts = []
    for segment in segments:
        txt = segment.text.strip()
        if txt:
            text_parts.append(txt)

    transcript = " ".join(text_parts).strip()

    return {
        "text": transcript,
        "language": getattr(info, "language", language),
        "duration": getattr(info, "duration", None),
    }



def transcribe_audio_bytes(audio_bytes: bytes, language: str = "fr") -> dict:
    """
    Transcrit un flux audio en mémoire.
    Aucun fichier disque n'est créé.
    """
    if not audio_bytes:
        return {"text": "", "language": language, "duration": None}

    model = _get_model()

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "live.webm"

    initial_prompt = os.getenv(
        "WHISPER_INITIAL_PROMPT",
        "Conversation téléphonique de prospection commerciale en français. "
        "Le vocabulaire peut inclure: site internet, automatisation, authentification, "
        "développement web, audit, SEO, performance, mobile, devis, rendez-vous, objection client."
    )

    segments, info = model.transcribe(
        audio_file,
        language=language,
        vad_filter=True,
        beam_size=3,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt,
    )

    text_parts = []
    for segment in segments:
        txt = segment.text.strip()
        if txt:
            text_parts.append(txt)

    transcript = " ".join(text_parts).strip()

    return {
        "text": transcript,
        "language": getattr(info, "language", language),
        "duration": getattr(info, "duration", None),
    }
