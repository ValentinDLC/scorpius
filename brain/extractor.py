"""
brain/extractor.py
LLM Client + Extraction + Scoring — Scorpius v2
"""

import json
import re
import time
import logging
from typing import Optional

import httpx

from config.loader import get_config

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 04 — LLM CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class LLMClient:
    GROQ_MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    def __init__(self):
        cfg = get_config()
        self.provider    = cfg.llm.get("provider", "groq")
        self.model       = cfg.llm.get("model", "llama-3.3-70b-versatile")
        self.api_key     = cfg.llm.get("api_key", "")
        self.ollama_host = cfg.llm.get("ollama_host", "http://localhost:11434")
        self.timeout     = 60
        self._validate()

    def _validate(self):
        if self.provider == "groq" and not self.api_key:
            raise ValueError(
                "llm.api_key manquante dans profil.yaml\n"
                "Obtenez une clé gratuite sur https://console.groq.com"
            )
        if self.provider not in ("groq", "ollama"):
            raise ValueError(
                f"llm.provider invalide : '{self.provider}'\n"
                "Valeurs acceptées : 'groq' ou 'ollama'"
            )

    def complete(self, prompt, system=None, temperature=0.1, max_tokens=4096):
        logger.debug(f"LLM [{self.provider}/{self.model}] prompt={len(prompt)} chars")
        if self.provider == "groq":
            return self._call_groq(prompt, system, temperature, max_tokens)
        else:
            return self._call_ollama(prompt, system, temperature, max_tokens)

    def _call_groq(self, prompt, system, temperature, max_tokens, _retry=0):
        messages = self._build_messages(prompt, system)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            logger.debug(f"Groq réponse : {len(content)} chars")
            return content
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 and _retry == 0:
                retry_after = int(e.response.headers.get("retry-after", 60))
                logger.warning(f"Groq rate limit — attente {retry_after}s...")
                time.sleep(retry_after)
                return self._call_groq(prompt, system, temperature, max_tokens, _retry=1)
            if status == 401:
                raise RuntimeError("Clé API Groq invalide. Vérifiez llm.api_key dans profil.yaml.")
            raise RuntimeError(f"Erreur Groq API {status} : {e.response.text[:200]}")
        except httpx.TimeoutException:
            raise RuntimeError(f"Timeout Groq après {self.timeout}s")
        except httpx.ConnectError:
            raise RuntimeError("Impossible de joindre l'API Groq. Vérifiez votre connexion internet.")

    def _call_ollama(self, prompt, system, temperature, max_tokens):
        messages = self._build_messages(prompt, system)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            resp = httpx.post(f"{self.ollama_host}/api/chat", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except httpx.ConnectError:
            raise RuntimeError(
                f"Impossible de joindre Ollama sur {self.ollama_host}\n"
                "Vérifiez que 'ollama serve' est lancé."
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise RuntimeError(f"Modèle Ollama '{self.model}' introuvable.\nLancez : ollama pull {self.model}")
            raise RuntimeError(f"Erreur Ollama {e.response.status_code}")

    @staticmethod
    def _build_messages(prompt, system):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def ping(self):
        try:
            resp = self.complete("Réponds uniquement: OK", temperature=0.0, max_tokens=5)
            return "OK" in resp.upper()
        except Exception as e:
            logger.error(f"LLM ping failed : {e}")
            return False

    def __repr__(self):
        return f"<LLMClient provider={self.provider} model={self.model}>"


# ══════════════════════════════════════════════════════════════════════════════
# STEP 05 — EXTRACTION HTML → MISSIONS
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_EXTRACT = """Tu es un assistant d'extraction de données structurées.
Tu analyses du HTML brut de plateformes freelance.
Tu extrais toutes les missions visibles sur la page.
Tu réponds UNIQUEMENT avec du JSON valide, sans markdown, sans explication."""

PROMPT_EXTRACT = """
Voici le HTML d'une page de missions freelance.
Plateforme : {plateforme}

Extrais TOUTES les missions présentes et retourne un tableau JSON.
Structure exacte de chaque objet :

[
  {{
    "titre": "string — titre de la mission",
    "description": "string — résumé en 2-3 phrases max, null si absent",
    "budget_min": number ou null,
    "budget_max": number ou null,
    "devise": "EUR" ou "USD" ou "CHF" etc., "EUR" par défaut,
    "client_nom": "string ou null",
    "url": "string — URL complète ou chemin relatif de la mission",
    "competences": ["tag1", "tag2"],
    "duree": "string ou null — ex: '3 mois', '1 semaine'"
  }}
]

Règles :
- Si une info est absente → null
- Ne fabrique pas d'informations
- Retourne [] si aucune mission trouvée
- Retourne UNIQUEMENT le JSON, rien d'autre

HTML :
{html}
"""


def _clean_html(html):
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    html = re.sub(r"<svg[^>]*>.*?</svg>", " ", html, flags=re.DOTALL | re.I)
    html = re.sub(r'\s(class|style|data-[a-z-]+)="[^"]*"', " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def _parse_json_response(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"[{\[]", raw)
    if match:
        try:
            return json.loads(raw[match.start():])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Impossible de parser le JSON du LLM.\nRéponse brute : {raw[:200]}")


def extract_missions_from_html(html, plateforme, llm=None, max_chars=2500):
    if llm is None:
        llm = LLMClient()
    html_clean = _clean_html(html)
    if len(html_clean) > max_chars:
        html_clean = html_clean[:max_chars]
        logger.warning(f"HTML tronqué à {max_chars} chars pour {plateforme}")
    prompt = PROMPT_EXTRACT.format(plateforme=plateforme, html=html_clean)
    logger.info(f"Extraction — {plateforme} ({len(html_clean)} chars HTML)")
    try:
        raw = llm.complete(prompt, system=SYSTEM_EXTRACT)
        data = _parse_json_response(raw)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            logger.error(f"LLM n'a pas retourné une liste : {type(data)}")
            return []
        logger.info(f"  → {len(data)} mission(s) extraite(s) de {plateforme}")
        return data
    except ValueError as e:
        logger.error(f"Erreur parsing JSON [{plateforme}] : {e}")
        return []
    except Exception as e:
        logger.error(f"Erreur extraction [{plateforme}] : {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# STEP 05 — SCORING
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_SCORE = """Tu es un expert en matching freelance.
Tu évalues objectivement la pertinence d'une mission pour un freelancer.
Tu réponds UNIQUEMENT avec du JSON valide."""

PROMPT_SCORE = """
Évalue la pertinence de cette mission pour ce freelancer.
Donne un score de 0 à 100.

─── PROFIL FREELANCER ───
Métier      : {metier}
Compétences : {competences}
Budget min  : {budget_min} {devise}
Langue      : {langue}
Description : {description_profil}

─── MISSION ───
Titre       : {titre}
Description : {description}
Budget      : {budget}
Compétences : {competences_mission}
Durée       : {duree}

─── BARÈME ───
Correspondance compétences   : 50 points max
Budget ≥ budget_min          : 20 points max
Adéquation métier / domaine  : 20 points max
Clarté et qualité de l'offre : 10 points max

Retourne UNIQUEMENT ce JSON :
{{
  "score": <entier entre 0 et 100>,
  "raisons": "<explication courte en 1-2 phrases>"
}}
"""


def score_mission(mission, llm=None):
    if llm is None:
        llm = LLMClient()
    cfg = get_config()
    profil = cfg.profil
    budget_str = _format_budget(mission)
    prompt = PROMPT_SCORE.format(
        metier=profil.get("metier", "Non précisé"),
        competences=", ".join(profil.get("competences", [])) or "Non précisé",
        budget_min=profil.get("budget_min", 0),
        devise="EUR",
        langue=profil.get("langue", "fr"),
        description_profil=profil.get("description", "")[:300],
        titre=mission.get("titre", "Sans titre"),
        description=(mission.get("description") or "")[:500],
        budget=budget_str,
        competences_mission=", ".join(mission.get("competences") or []) or "Non précisé",
        duree=mission.get("duree") or "Non précisé",
    )
    try:
        raw = llm.complete(prompt, system=SYSTEM_SCORE, temperature=0.0)
        data = _parse_json_response(raw)
        score = max(0, min(100, int(data.get("score", 0))))
        raisons = str(data.get("raisons", ""))
        logger.debug(f"Score [{score}/100] {mission.get('titre', '')[:50]}")
        return score, raisons
    except Exception as e:
        logger.error(f"Erreur scoring '{mission.get('titre', '')}' : {e}")
        return 0, f"Erreur de scoring : {e}"


def _format_budget(mission):
    bmin = mission.get("budget_min")
    bmax = mission.get("budget_max")
    devise = mission.get("devise", "EUR")
    if bmin and bmax:
        return f"{bmin}–{bmax} {devise}"
    elif bmin:
        return f"À partir de {bmin} {devise}"
    elif bmax:
        return f"Jusqu'à {bmax} {devise}"
    return "Non précisé"


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE COMPLET
# ══════════════════════════════════════════════════════════════════════════════

def process_page(html, plateforme_url, plateforme_nom):
    llm = LLMClient()
    cfg = get_config()
    budget_min = cfg.profil.get("budget_min", 0)

    missions_brutes = extract_missions_from_html(html, plateforme_nom, llm)
    if not missions_brutes:
        logger.warning(f"Aucune mission extraite de {plateforme_nom}")
        return []

    missions_filtrees = []
    for m in missions_brutes:
        bmax = m.get("budget_max")
        if budget_min and bmax and bmax < budget_min:
            logger.debug(f"  Skip budget trop bas ({bmax}) : {m.get('titre', '')[:40]}")
            continue
        missions_filtrees.append(m)

    logger.info(f"{plateforme_nom} : {len(missions_brutes)} extraites → {len(missions_filtrees)} après filtre budget")

    results = []
    for m in missions_filtrees:
        score, raisons = score_mission(m, llm)
        m["score"]          = score
        m["score_raisons"]  = raisons
        m["plateforme"]     = plateforme_nom
        m["plateforme_url"] = plateforme_url
        m["url"]            = _normalize_url(m.get("url", ""), plateforme_url)
        results.append(m)
        logger.info(f"  [{score:3d}/100] {m.get('titre', '')[:55]}")
        time.sleep(0.5)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _normalize_url(url, plateforme_url):
    if not url:
        return plateforme_url
    if url.startswith("http"):
        return url
    from urllib.parse import urlparse
    parsed = urlparse(plateforme_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base + (url if url.startswith("/") else "/" + url)
