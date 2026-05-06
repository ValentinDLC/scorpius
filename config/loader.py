import os
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "profil.yaml")

@dataclass
class ScorpiusConfig:
    profil: Dict[str, Any] = field(default_factory=dict)
    plateformes: List[Dict] = field(default_factory=list)
    llm: Dict[str, Any] = field(default_factory=dict)
    notifications: Dict[str, Any] = field(default_factory=dict)
    scraping: Dict[str, Any] = field(default_factory=dict)
    vocal_id: Dict[str, Any] = field(default_factory=dict)
    voice_auth: Dict[str, Any] = field(default_factory=dict)
    dashboard: Dict[str, Any] = field(default_factory=dict)

    @property
    def plateformes_actives(self) -> List[Dict]:
        return [p for p in self.plateformes if p.get("actif", False)]

    def __repr__(self):
        metier = self.profil.get("metier", "?")
        provider = self.llm.get("provider", "?")
        nb = len(self.plateformes_actives)
        return f"<ScorpiusConfig | métier={metier} | provider={provider} | plateformes={nb} actives>"


DEFAULTS = {
    "scraping": {
        "frequence_minutes": 60,
        "delai_min_secondes": 3,
        "delai_max_secondes": 8,
        "heures_creuses": False,
    },
    "dashboard": {
        "theme": "dark",
        "port": 5000,
    },
    "vocal_id": {
        "actif": False,
        "voix": "feminine",
        "langue": "fr",
        "stt_model": "base",
        "tts_engine": "edge-tts",
    },
    "voice_auth": {
        "actif": False,
        "seuil_similarite": 0.85,
        "max_tentatives": 3,
    },
}


def get_config() -> ScorpiusConfig:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Fichier de config introuvable : {CONFIG_PATH}\n"
            f"→ Copie config/profil.yaml.example vers config/profil.yaml"
        )

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError("profil.yaml est vide ou invalide")

    for key, defaults in DEFAULTS.items():
        if key not in raw:
            raw[key] = defaults
        else:
            for k, v in defaults.items():
                raw[key].setdefault(k, v)

    profil = raw.get("profil", {})
    if not profil.get("metier"):
        raise ValueError("profil.metier est requis dans profil.yaml")

    return ScorpiusConfig(
        profil=profil,
        plateformes=raw.get("plateformes", []),
        llm=raw.get("llm", {}),
        notifications=raw.get("notifications", {}),
        scraping=raw["scraping"],
        vocal_id=raw["vocal_id"],
        voice_auth=raw["voice_auth"],
        dashboard=raw["dashboard"],
    )
