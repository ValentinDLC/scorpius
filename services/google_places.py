"""Google Places API v1 (2024)"""
import os, httpx, json, re
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

BASE_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.id,places.location,places.googleMapsUri"

def get_api_key() -> str:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not key:
        raise ValueError("GOOGLE_PLACES_API_KEY manquante dans .env")
    return key

def extract_ville_from_address(address: str) -> str:
    """Extrait la ville depuis l'adresse formatted (ex: '75011 Paris, France').
    Gère : 'Rue X, 75011 Paris, France' → 'Paris'
    """
    import re
    if not address:
        return ""
    # Stratégie 1 : code postal 5 chiffres suivi du nom de ville
    # Capture tout ce qui suit le CP jusqu'à la virgule ou fin de chaîne
    match = re.search(r"\b(\d{5})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\- ]*?)(?:\s*,|\s*$)", address)
    if match:
        ville_raw = match.group(2).strip()
        # Prendre uniquement le premier mot significatif (exclut "Cedex", arrondissements)
        mots = ville_raw.split()
        if mots:
            return mots[0]
    # Stratégie 2 : avant-dernier segment séparé par virgule (avant "France")
    EXCLUSIONS = {"france", "fr", ""}
    parts = [p.strip() for p in address.split(",")]
    # Parcourir à l'envers, ignorer "France" et codes postaux seuls
    for part in reversed(parts):
        if part.lower() in EXCLUSIONS:
            continue
        if re.match(r"^\d{5}\s*$", part):
            continue
        # Enlever un éventuel code postal en début de segment
        cleaned = re.sub(r"^\d{5}\s+", "", part).strip()
        if cleaned and cleaned.lower() not in EXCLUSIONS:
            return cleaned.split()[0]
    return ""

def search_places(text_query: str, language_code: str = "fr", max_results: int = 10) -> List[Dict]:
    api_key = get_api_key()
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
        "Content-Type": "application/json",
    }
    payload = {
        "textQuery": text_query,
        "languageCode": language_code,
        "maxResultCount": min(max_results, 20),
    }
    try:
        response = httpx.post(BASE_URL, headers=headers, json=payload, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        places = data.get("places", [])
        print(f"[INFO] Google Places — {len(places)} lieu(x) trouvé(s)")
        # Vérifie que chaque place est sérialisable
        for i, place in enumerate(places):
            if not isinstance(place, dict):
                places[i] = dict(place)
        
        return places
    except Exception as e:
        print(f"[ERROR] Google Places — {e}")
        return []

def parse_place_to_prospect(place: Dict, secteur: str = "", ville: str = "") -> Dict:
    # Debug : vérifie que place n'est pas vide
    if not place:
        print(f"[WARNING] parse_place_to_prospect reçu place vide !")
        place = {"debug": "empty_place"}
    
    # Sérialise IMMÉDIATEMENT avant toute opération
    import json
    raw_json = json.dumps(place, ensure_ascii=False, default=str)
    print(f"[DEBUG] raw_google_json length = {len(raw_json)}")
    address = place.get("formattedAddress", "")
    website = place.get("websiteUri", "")
    place_id = place.get("id", "")
    
    # Génère URL Google Maps
    maps_url = place.get("googleMapsUri", "")
    if not maps_url and place_id:
        maps_url = f"https://maps.google.com/?cid={place_id}"
    
    # Sauvegarde le JSON complet AVANT toute modification
    raw_json = json.dumps(place, ensure_ascii=False, indent=2)
    
    return {
        "nom": place.get("displayName", {}).get("text", "Inconnu"),
        "adresse": address,
        "telephone": place.get("nationalPhoneNumber", ""),
        "url_site": website,
        "place_id": place_id,
        "google_maps_url": maps_url,
        "ville": extract_ville_from_address(address) if address else ville,
        "secteur": secteur,
        "sans_site": not bool(website),
        "raw_google_json": raw_json,
    }

def search_prospects(secteur: str, ville: str, rayon_km: int = 10, filtre_sans_site: bool = False, limit: int = 10) -> List[Dict]:
    text_query = f"{secteur} {ville}"
    places = search_places(text_query=text_query, language_code="fr", max_results=limit * 2 if filtre_sans_site else limit)
    prospects = [parse_place_to_prospect(p, secteur=secteur, ville=ville) for p in places]
    
    if filtre_sans_site:
        sans_site = [p for p in prospects if p["sans_site"]]
        avec_site = [p for p in prospects if not p["sans_site"]]
        prospects = sans_site + avec_site
        prospects = prospects[:limit]
    
    return prospects


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper de compatibilité (pour prospects_routes.py)
# ──────────────────────────────────────────────────────────────────────────────

def search_google_places(secteur: str, ville: str, rayon_km: int = 10, filtre_sans_site: bool = False, max_results: int = 10) -> List[Dict]:
    """
    Ancienne signature pour compatibilité avec prospects_routes.py
    """
    return search_prospects(
        secteur=secteur,
        ville=ville,
        rayon_km=rayon_km,
        filtre_sans_site=filtre_sans_site,
        limit=max_results,
    )
