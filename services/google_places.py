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
    """Extrait la ville depuis l'adresse formatted (ex: '75011 Paris')."""
    import re
    match = re.search(r"(\d{5})\s+([A-Za-zÀ-ÿ\-]+)", address)
    if match:
        return match.group(2)
    parts = address.split(",")
    for part in parts:
        part = part.strip()
        if re.match(r"^\d{5}", part):
            return part.split(maxsplit=1)[1] if len(part.split()) > 1 else ""
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
