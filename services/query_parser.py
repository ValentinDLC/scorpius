import json
import os
import re
from typing import Any

import httpx

SYSTEM_PROMPT = """
Tu es un parseur de requêtes commerciales.
Tu dois transformer une demande utilisateur en JSON strict avec les clés :
- secteur (string)
- ville (string)
- rayon_km (integer)
- filtre_sans_site (boolean)

Exemple :
"restaurants à Meaux qui n'ont pas de site web"
=
{"secteur":"restaurants","ville":"Meaux","rayon_km":10,"filtre_sans_site":true}

Retourne uniquement du JSON valide.
"""

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("JSON introuvable dans la réponse LLM")
    return json.loads(match.group(0))

def _fallback_parse(message: str) -> dict[str, Any]:
    msg = message.strip()

    ville = ""
    m = re.search(r"\b(?:à|a|dans|autour de)\s+([A-Za-zÀ-ÿ' -]+)", msg, re.I)
    if m:
        ville = m.group(1).strip()

    filtre_sans_site = bool(
        re.search(r"sans site|pas de site|n'ont pas de site|n ont pas de site", msg, re.I)
    )

    secteur = msg
    secteur = re.sub(r"\b(?:à|a|dans|autour de)\s+[A-Za-zÀ-ÿ' -]+", "", secteur, flags=re.I).strip()
    secteur = re.sub(
        r"\b(sans site|pas de site|qui n'ont pas de site web|qui n ont pas de site web)\b",
        "",
        secteur,
        flags=re.I,
    ).strip(" ,.-")

    return {
        "secteur": secteur or "entreprises",
        "ville": ville or "Paris",
        "rayon_km": 10,
        "filtre_sans_site": filtre_sans_site,
    }

def _call_groq(message: str) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY absent")

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    }

    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(content)

def parse_prospect_query(message: str) -> dict[str, Any]:
    if not message or not message.strip():
        raise ValueError("Message vide")

    try:
        data = _call_groq(message)
    except Exception:
        data = _fallback_parse(message)

    return {
        "secteur": str(data.get("secteur", "entreprises")).strip(),
        "ville": str(data.get("ville", "Paris")).strip(),
        "rayon_km": int(data.get("rayon_km", 10) or 10),
        "filtre_sans_site": bool(data.get("filtre_sans_site", False)),
    }
