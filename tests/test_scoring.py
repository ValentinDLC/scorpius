import pytest
from services.audit_service import compute_audit_score

def test_score_no_site():
    """Un prospect sans rien doit avoir 0."""
    assert compute_audit_score(has_site=False, audit_mobile=False, audit_performance=0, audit_seo=0, audit_gmb=False) == 0

def test_score_only_site():
    """Un prospect avec juste un site (sans analyse réussie) a 20 points."""
    assert compute_audit_score(has_site=True, audit_mobile=False, audit_performance=0, audit_seo=0, audit_gmb=False) == 20

def test_score_max():
    """Un prospect parfait doit avoir exactement 100 naturellement."""
    assert compute_audit_score(has_site=True, audit_mobile=True, audit_performance=100, audit_seo=100, audit_gmb=True) == 100

def test_score_out_of_bounds():
    """Vérifie que des valeurs négatives ou excessives de l'API ne cassent pas le calcul."""
    assert compute_audit_score(has_site=False, audit_mobile=False, audit_performance=-50, audit_seo=-10, audit_gmb=False) == 0
    assert compute_audit_score(has_site=True, audit_mobile=True, audit_performance=150, audit_seo=200, audit_gmb=False) == 100

def test_score_partial():
    """Site (20) + Perf 50 (50*0.35 = 17.5) = 37.5, arrondi à 38."""
    assert compute_audit_score(has_site=True, audit_mobile=False, audit_performance=50, audit_seo=0, audit_gmb=False) == 38

