"""
Suite de 30 tests API Scorpius.

Variables d'environnement requises avant de lancer les tests :

  SCORPIUS_TEST_EMAIL / SCORPIUS_TEST_PASSWORD      -> compte valide (user_id != 0)
  SCORPIUS_OTHER_EMAIL / SCORPIUS_OTHER_PASSWORD    -> compte user_id=0 (pour les tests d'isolation)

Le serveur Flask doit tourner en local (SCORPIUS_BASE_URL, défaut http://localhost:5000).

Lancement : pytest tests/test_scorpius_api.py -v
Important : ces tests dépendent les uns des autres et doivent tourner dans l'ordre
du fichier (pas de plugin pytest-randomly actif).
"""

import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("SCORPIUS_BASE_URL", "http://localhost:5000")
EMAIL = os.environ["SCORPIUS_TEST_EMAIL"]
PASSWORD = os.environ["SCORPIUS_TEST_PASSWORD"]
OTHER_EMAIL = os.environ.get("SCORPIUS_OTHER_EMAIL")
OTHER_PASSWORD = os.environ.get("SCORPIUS_OTHER_PASSWORD")

state = {}


def url(path):
    return f"{BASE_URL}{path}"


# ---------- HEALTH ----------

def test_01_health():
    r = requests.get(url("/health"))
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- AUTH ----------

def test_02_auth_status_logged_out():
    s = requests.Session()
    r = s.get(url("/api/auth/status"))
    assert r.status_code == 200
    assert r.json()["data"]["authenticated"] is False


def test_03_login_ok():
    s = requests.Session()
    r = s.post(url("/login"), json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200
    state["session"] = s


def test_04_auth_status_logged_in():
    s = state["session"]
    r = s.get(url("/api/auth/status"))
    assert r.status_code == 200
    assert r.json()["data"]["authenticated"] is True


def test_05_login_wrong_password():
    s = requests.Session()
    r = s.post(url("/login"), json={"email": EMAIL, "password": "mot_de_passe_faux"})
    assert r.status_code == 401


# ---------- PROSPECTS - LECTURE ----------

def test_06_list_prospects():
    s = state["session"]
    r = s.get(url("/api/prospects"))
    assert r.status_code == 200
    data = r.json().get("data")
    assert isinstance(data, list)
    state["prospects"] = data


def test_07_filter_a_appeler():
    s = state["session"]
    r = s.get(url("/api/prospects"), params={"statut": "a_appeler"})
    assert r.status_code == 200
    for p in r.json().get("data", []):
        assert p["statut"] == "a_appeler"


def test_08_filter_mission():
    s = state["session"]
    r = s.get(url("/api/prospects"), params={"statut": "mission"})
    assert r.status_code == 200
    for p in r.json().get("data", []):
        assert p["statut"] == "mission"


def test_09_filter_appele():
    s = state["session"]
    r = s.get(url("/api/prospects"), params={"statut": "appele"})
    assert r.status_code == 200
    for p in r.json().get("data", []):
        assert p["statut"] == "appele"


def test_10_filter_gagne():
    s = state["session"]
    r = s.get(url("/api/prospects"), params={"statut": "gagne"})
    assert r.status_code == 200
    for p in r.json().get("data", []):
        assert p["statut"] == "gagne"


def test_11_pagination_limit():
    s = state["session"]
    r = s.get(url("/api/prospects"), params={"limit": 3})
    assert r.status_code == 200
    assert len(r.json().get("data", [])) <= 3


def test_12_get_existing_prospect():
    s = state["session"]
    assert state["prospects"], "Il faut au moins un prospect existant pour ce test"
    pid = state["prospects"][0]["id"]
    r = s.get(url(f"/api/prospects/{pid}"))
    assert r.status_code == 200
    state["existing_prospect_id"] = pid


def test_13_get_nonexistent_prospect():
    s = state["session"]
    r = s.get(url("/api/prospects/99999"))
    assert r.status_code == 404


# ---------- PROSPECTS - CREATION ----------

def test_14_search_prospects():
    s = state["session"]
    r = s.post(url("/api/prospects/search"), json={"message": "boulangeries Paris", "limit": 3})
    assert r.status_code == 200
    data = r.json().get("data", [])
    assert len(data) > 0
    state["search_prospect_id"] = data[0]["id"]


def test_15_search_empty_message():
    s = state["session"]
    r = s.post(url("/api/prospects/search"), json={"message": ""})
    assert r.status_code == 400


# ---------- PROSPECTS - MISE A JOUR ----------

def test_16_patch_statut_mission():
    s = state["session"]
    pid = state["search_prospect_id"]
    r = s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "mission"})
    assert r.status_code == 200


def test_17_patch_statut_a_appeler():
    s = state["session"]
    pid = state["search_prospect_id"]
    r = s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "a_appeler"})
    assert r.status_code == 200


def test_18_patch_statut_appele():
    s = state["session"]
    pid = state["search_prospect_id"]
    r = s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "appele"})
    assert r.status_code == 200


def test_19_patch_statut_gagne():
    s = state["session"]
    pid = state["search_prospect_id"]
    r = s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "gagne"})
    assert r.status_code == 200


def test_20_patch_statut_body_vide():
    s = state["session"]
    pid = state["search_prospect_id"]
    r = s.patch(url(f"/api/prospects/{pid}/statut"), json={})
    assert r.status_code == 400


# ---------- PROSPECTS - SUPPRESSION ----------

def test_21_archive_prospect():
    s = state["session"]
    pid = state["search_prospect_id"]
    r = s.delete(url(f"/api/prospects/{pid}"))
    assert r.status_code == 200
    r2 = s.get(url(f"/api/prospects/{pid}"))
    assert r2.json()["data"]["statut"] == "archive"


# ---------- STATS ----------

def test_22_stats():
    s = state["session"]
    r = s.get(url("/api/stats"))
    assert r.status_code == 200


# ---------- SETTINGS ----------

def test_23_theme_dark():
    s = state["session"]
    r = s.post(url("/api/settings/theme"), json={"theme": "dark"})
    assert r.status_code == 200


def test_24_theme_light():
    s = state["session"]
    r = s.post(url("/api/settings/theme"), json={"theme": "light"})
    assert r.status_code == 200


def test_25_db_status():
    s = state["session"]
    r = s.get(url("/api/settings/db-status"))
    assert r.status_code == 200
    assert r.json()["data"]["connected"] is True


# ---------- SECURITE - ISOLATION user_id ----------

def test_26_no_session_unauthorized():
    r = requests.get(url("/api/prospects"))
    assert r.status_code == 401


@pytest.mark.skipif(not OTHER_EMAIL, reason="SCORPIUS_OTHER_EMAIL non fourni")
def test_27_user_isolation():
    s_other = requests.Session()
    r = s_other.post(url("/login"), json={"email": OTHER_EMAIL, "password": OTHER_PASSWORD})
    assert r.status_code == 200
    r2 = s_other.get(url("/api/prospects"))
    other_ids = {p["id"] for p in r2.json().get("data", [])}
    mine_ids = {p["id"] for p in state["prospects"]}
    assert other_ids.isdisjoint(mine_ids)
    state["other_session"] = s_other
    state["other_prospect_ids"] = other_ids


@pytest.mark.skipif(not OTHER_EMAIL, reason="SCORPIUS_OTHER_EMAIL non fourni")
def test_28_cannot_patch_other_users_prospect():
    s = state["session"]
    assert state["other_prospect_ids"], "Le compte user_id=0 doit avoir au moins un prospect"
    other_pid = next(iter(state["other_prospect_ids"]))
    r = s.patch(url(f"/api/prospects/{other_pid}/statut"), json={"statut": "mission"})
    assert r.status_code == 404


# ---------- PARCOURS FONCTIONNELS ----------

def test_29_parcours_prospect_a_gagne():
    s = state["session"]
    r = s.post(url("/api/prospects/search"), json={"message": "coiffeurs Lyon", "limit": 1})
    pid = r.json()["data"][0]["id"]

    s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "mission"})
    s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "appele"})
    r2 = s.patch(url(f"/api/prospects/{pid}/statut"), json={"statut": "gagne"})
    assert r2.status_code == 200

    r3 = s.get(url("/api/prospects"), params={"statut": "gagne"})
    ids = {p["id"] for p in r3.json().get("data", [])}
    assert pid in ids


def test_30_nouveau_compte_vide():
    new_email = f"test_{uuid.uuid4().hex[:8]}@scorpius.test"
    new_password = "TestPassword123!"

    s = requests.Session()
    r = s.post(url("/register"), json={"email": new_email, "password": new_password})
    assert r.status_code == 200

    r2 = s.post(url("/login"), json={"email": new_email, "password": new_password})
    assert r2.status_code == 200

    r3 = s.get(url("/api/prospects"))
    assert r3.status_code == 200
    assert r3.json().get("data") == []
