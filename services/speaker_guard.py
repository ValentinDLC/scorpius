"""
services/speaker_guard.py
Speaker Guard privacy-first:
- stocke uniquement l'empreinte vocale ME
- ne stocke jamais audio/empreinte UNKNOWN
- évite torchaudio.load / torchcodec
"""

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import torch

logger = logging.getLogger(__name__)

PROFILE_PATH = Path(os.getenv("VOICE_PROFILE_PATH", "data/voice_profile_me.json"))
MODEL_DIR = os.getenv("SPEAKER_MODEL_DIR", "models/spkrec-ecapa-voxceleb")
SPEAKER_MODEL = os.getenv("SPEAKER_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
DEFAULT_THRESHOLD = float(os.getenv("VOICE_ME_THRESHOLD", "0.72"))

_CLASSIFIER = None


def _get_classifier():
    global _CLASSIFIER

    if _CLASSIFIER is not None:
        return _CLASSIFIER

    try:
        from speechbrain.inference.speaker import EncoderClassifier
    except Exception:
        from speechbrain.pretrained import EncoderClassifier

    logger.info(f"🧬 Chargement Speaker Guard model={SPEAKER_MODEL}")

    _CLASSIFIER = EncoderClassifier.from_hparams(
        source=SPEAKER_MODEL,
        savedir=MODEL_DIR,
    )

    return _CLASSIFIER


def has_me_profile() -> bool:
    return PROFILE_PATH.exists()


def load_me_profile() -> Optional[dict]:
    if not PROFILE_PATH.exists():
        return None

    try:
        return json.loads(PROFILE_PATH.read_text())
    except Exception as e:
        logger.error(f"❌ Impossible de lire le profil vocal ME: {e}")
        return None


def delete_me_profile() -> bool:
    try:
        if PROFILE_PATH.exists():
            PROFILE_PATH.unlink()
        return True
    except Exception as e:
        logger.error(f"❌ Suppression profil vocal failed: {e}")
        return False


def _convert_webm_bytes_to_wav(audio_bytes: bytes) -> str:
    if not audio_bytes or len(audio_bytes) < 1500:
        raise ValueError("Audio trop court pour créer une empreinte vocale")

    tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    tmp_in.write(audio_bytes)
    tmp_in.close()

    wav_path = tmp_in.name + ".wav"

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", tmp_in.name,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-f", "wav",
            wav_path,
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        return wav_path

    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Conversion ffmpeg webm→wav failed: {err}") from e

    finally:
        try:
            os.unlink(tmp_in.name)
        except OSError:
            pass


def _embedding_from_wav(wav_path: str) -> list[float]:
    # IMPORTANT: soundfile évite torchaudio.load donc pas besoin de torchcodec
    audio, sr = sf.read(wav_path, dtype="float32", always_2d=False)

    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    if sr != 16000:
        raise ValueError(f"Sample rate inattendu: {sr}, attendu 16000")

    if audio.size < 16000:
        raise ValueError("Audio trop court: parle au moins 8-10 secondes")

    signal = torch.from_numpy(audio).float().unsqueeze(0)

    classifier = _get_classifier()

    with torch.no_grad():
        emb = classifier.encode_batch(signal)
        emb = emb.squeeze().detach().cpu().numpy().astype("float32")

    return emb.tolist()


def embedding_from_webm_bytes(audio_bytes: bytes) -> list[float]:
    wav_path = None

    try:
        wav_path = _convert_webm_bytes_to_wav(audio_bytes)
        return _embedding_from_wav(wav_path)

    finally:
        if wav_path:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)

    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))

    if denom <= 0:
        return 0.0

    return float(np.dot(va, vb) / denom)


def enroll_me(audio_bytes: bytes) -> dict:
    """
    Crée le profil vocal local ME.
    Stocke uniquement l'embedding de ta voix.
    """
    embedding = embedding_from_webm_bytes(audio_bytes)

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "speaker": "ME",
        "created_at": datetime.utcnow().isoformat(),
        "model": SPEAKER_MODEL,
        "threshold": DEFAULT_THRESHOLD,
        "embedding": embedding,
        "embedding_dim": len(embedding),
    }

    PROFILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    logger.info(
        f"✅ Profil vocal ME créé: {PROFILE_PATH} dim={len(embedding)}"
    )

    return {
        "ok": True,
        "speaker": "ME",
        "profile_path": str(PROFILE_PATH),
        "threshold": DEFAULT_THRESHOLD,
        "embedding_dim": len(embedding),
    }


def compare_to_me(audio_bytes: bytes) -> dict:
    """
    Compare un chunk audio à ME.
    Ne stocke rien pour UNKNOWN.
    """
    profile = load_me_profile()

    if not profile:
        return {
            "ok": False,
            "speaker": "UNKNOWN",
            "error": "Aucun profil vocal ME enregistré",
        }

    current_embedding = embedding_from_webm_bytes(audio_bytes)
    similarity = _cosine(profile["embedding"], current_embedding)
    threshold = float(profile.get("threshold", DEFAULT_THRESHOLD))

    speaker = "ME" if similarity >= threshold else "UNKNOWN"

    return {
        "ok": True,
        "speaker": speaker,
        "similarity": round(similarity, 4),
        "threshold": threshold,
    }


def classify_speaker(audio_bytes: bytes) -> dict:
    return compare_to_me(audio_bytes)


def classify_webm_bytes(audio_bytes: bytes) -> dict:
    return compare_to_me(audio_bytes)


def get_me_profile_status() -> dict:
    profile = load_me_profile()

    if not profile:
        return {
            "ok": True,
            "exists": False,
            "speaker": None,
        }

    return {
        "ok": True,
        "exists": True,
        "speaker": "ME",
        "created_at": profile.get("created_at"),
        "model": profile.get("model"),
        "threshold": profile.get("threshold"),
        "embedding_dim": profile.get("embedding_dim"),
    }
