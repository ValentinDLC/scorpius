from services.query_parser import _fallback_parse

def test_fallback_parse_basic():
    data = _fallback_parse("restaurants à Meaux sans site web")
    assert data["secteur"]
    assert data["ville"].lower() == "meaux"
    assert data["filtre_sans_site"] is True
    assert data["rayon_km"] == 10
