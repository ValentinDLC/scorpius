import pytest
import sys
import os
from sqlalchemy import create_engine, text
from contextlib import contextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data')))
import storage.prospects as prospects_module

@pytest.fixture
def mock_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE prospects (
                id TEXT PRIMARY KEY,
                user_id INTEGER DEFAULT 0,
                nom TEXT,
                place_id TEXT,
                score_audit INTEGER DEFAULT 0,
                audit_mobile BOOLEAN DEFAULT 0,
                audit_performance INTEGER DEFAULT 0,
                audit_seo INTEGER DEFAULT 0,
                audit_gmb BOOLEAN DEFAULT 0,
                seo_title BOOLEAN DEFAULT 0,
                seo_meta_description BOOLEAN DEFAULT 0,
                seo_h1 BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP
            )
        """))

    @contextmanager
    def override_get_conn():
        with engine.begin() as conn:
            yield conn

    monkeypatch.setattr(prospects_module, "get_conn", override_get_conn)
    yield engine

def test_update_prospect_audit_persistence(mock_db):
    prospect_id = "prospect_123"
    
    # On injecte le prospect avec user_id = 0 pour correspondre au comportement par défaut de la fonction
    with mock_db.begin() as conn:
        conn.execute(text("INSERT INTO prospects (id, user_id, nom, place_id) VALUES (:id, 0, :n, :p)"),
                     {"id": prospect_id, "n": "Test", "p": "place_123"})
    
    fake_audit_result = {
        "score_audit": 85,
        "audit_mobile": True,
        "audit_performance": 90,
        "audit_seo": 75,
        "audit_gmb": True,
        "seo_title": True,
        "seo_meta_description": False,
        "seo_h1": True
    }
    
    prospects_module.update_prospect_audit(prospect_id, fake_audit_result)
    
    with mock_db.connect() as conn:
        row = conn.execute(text("SELECT * FROM prospects WHERE id = :id"), {"id": prospect_id}).mappings().fetchone()
        
    assert row["score_audit"] == 85
    assert row["audit_mobile"] in (1, True)
    assert row["audit_performance"] == 90
    assert row["audit_seo"] == 75
    assert row["audit_gmb"] in (1, True)
    assert row["seo_title"] in (1, True)
    assert row["seo_meta_description"] in (0, False)
    assert row["seo_h1"] in (1, True)

