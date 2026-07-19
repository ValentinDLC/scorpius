from services.query_parser import _fallback_parse

def test_fallback_parse_basic():
    data = _fallback_parse("restaurants à Meaux")
    assert data["secteur"]
    assert data["ville"].lower() == "meaux"
