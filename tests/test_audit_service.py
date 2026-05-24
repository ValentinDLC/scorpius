from services.audit_service import compute_audit_score

def test_compute_audit_score_full():
    score = compute_audit_score(
        has_site=True,
        audit_mobile=True,
        audit_performance=80,
        audit_seo=100,
        audit_gmb=True,
    )
    assert 80 <= score <= 100

def test_compute_audit_score_without_site():
    score = compute_audit_score(
        has_site=False,
        audit_mobile=False,
        audit_performance=0,
        audit_seo=0,
        audit_gmb=True,
    )
    assert score < 30
