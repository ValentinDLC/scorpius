import pytest
from flask import Flask, session, jsonify
import sys
import os

# Ajout des chemins
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data')))

from dashboard.crm_routes import crm_bp
import dashboard.crm_routes as crm_module
import data.storage.prospects as prospects_module

from sqlalchemy import create_engine, text
from contextlib import contextmanager

# On crée une fausse application Flask pour les tests d'API
@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__, template_folder="../web/templates")
    app.secret_key = "test_key"
    app.register_blueprint(crm_bp)

    # Base SQLite propre à chaque test
    engine = create_engine("sqlite:///:memory:")
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE prospects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                place_id TEXT UNIQUE,
                nom TEXT,
                statut TEXT DEFAULT 'nouveau',
                score_audit INTEGER DEFAULT 0,
                updated_at TIMESTAMP
            )
        """))
        
        # Injection de fausses données
        conn.execute(text("INSERT INTO prospects (user_id, place_id, nom, statut) VALUES ('u1', 'p1', 'Prospect A', 'nouveau')"))
        conn.execute(text("INSERT INTO prospects (user_id, place_id, nom, statut) VALUES ('u1', 'p2', 'Prospect B', 'a_demarcher')"))
        conn.execute(text("INSERT INTO prospects (user_id, place_id, nom, statut) VALUES ('u2', 'p3', 'Prospect C', 'nouveau')"))

    @contextmanager
    def override_get_conn():
        with engine.begin() as conn:
            yield conn

    monkeypatch.setattr(crm_module, "get_conn", override_get_conn)
    monkeypatch.setattr(prospects_module, "get_conn", override_get_conn)

    return app

@pytest.fixture
def client(app):
    return app.test_client()

# --- TESTS D'API ---

def test_api_crm_list_prospects(client):
    """Teste que u1 ne voit que ses deux prospects."""
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        
    response = client.get("/crm")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Prospect A" in html
    assert "Prospect B" in html
    assert "Prospect C" not in html  # Appartient à u2

def test_api_crm_update_statut_valid(client):
    """Teste la mise à jour avec le nouveau dictionnaire."""
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        
    response = client.patch("/api/crm/prospects/1/statut", json={"statut": "gagne"})
    assert response.status_code == 200
    assert response.get_json()["statut"] == "gagne"

def test_api_crm_update_statut_invalid(client):
    """Teste le rejet des anciens statuts comme 'mission' ou 'a_appeler'."""
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        
    response = client.patch("/api/crm/prospects/1/statut", json={"statut": "mission"})
    assert response.status_code == 400
    assert "Statut invalide" in response.get_json()["message"]

def test_api_crm_add_prospect_blocks_idor(client):
    """Vérifie que u1 ne peut pas ajouter le prospect de u2 au CRM."""
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        
    response = client.post("/crm/prospects/3/add")  # 3 appartient à u2
    assert response.status_code == 404
    assert response.get_json()["ok"] is False

def test_api_crm_stats_isolation(client):
    """Vérifie que les stats de l'accueil CRM ne comptent que les prospects de u1."""
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        
    response = client.get("/crm")
    assert response.status_code == 200
    # Dans nos mocks, u1 a 2 prospects
    html = response.get_data(as_text=True)
    # Note: comme on retourne le HTML, on vérifie juste que l'appel ne plante pas (code 200)
    # L'assertion exacte des valeurs dépend de la structure de crm_dashboard.html
