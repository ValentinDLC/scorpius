import pytest
import sys
import os

# On indique à Python où trouver le dossier 'storage' (qui est dans 'data')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data')))

from flask import Flask, session
from dashboard.crm_routes import crm_bp
from sqlalchemy import create_engine, text
from contextlib import contextmanager
import dashboard.crm_routes as crm_module

@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "super_secret_test_key"
    app.register_blueprint(crm_bp)

    # Création d'une base SQLite en mémoire simulée pour le test
    engine = create_engine("sqlite:///:memory:")
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE prospects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                nom TEXT,
                statut TEXT DEFAULT 'Nouveau',
                score_audit INTEGER DEFAULT 0,
                updated_at TIMESTAMP
            )
        """))
        
        # Utilisateur A possède le prospect 1
        conn.execute(text("INSERT INTO prospects (id, user_id, nom, statut) VALUES (1, 'user_A', 'Entreprise A', 'Nouveau')"))
        
        # Utilisateur B possède le prospect 2
        conn.execute(text("INSERT INTO prospects (id, user_id, nom, statut) VALUES (2, 'user_B', 'Entreprise B', 'Nouveau')"))

    @contextmanager
    def override_get_conn():
        with engine.begin() as conn:
            yield conn

    monkeypatch.setattr(crm_module, "get_conn", override_get_conn)
    monkeypatch.setattr(crm_module.storage_db, "_using_sqlite", True)

    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_idor_update_status_blocked(client, app):
    """Vérifie que B ne peut pas modifier le statut du prospect de A."""
    
    # 1. On se connecte en tant que l'utilisateur B
    with client.session_transaction() as sess:
        sess["user_id"] = "user_B"

    # 2. B tente de modifier le prospect 1 (qui appartient à A)
    response = client.patch(
        "/api/crm/prospects/1/statut",
        json={"statut": "Gagné"}
    )
    
    # 3. L'application doit répondre 404
    assert response.status_code == 404
    data = response.get_json()
    assert data["ok"] is False
    assert data["message"] == "Prospect non trouvé"

def test_idor_update_status_allowed_for_owner(client, app):
    """Vérifie que B PEUT modifier le statut de son PROPRE prospect."""
    
    with client.session_transaction() as sess:
        sess["user_id"] = "user_B"

    response = client.patch(
        "/api/crm/prospects/2/statut",
        json={"statut": "Gagné"}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["statut"] == "Gagné"

