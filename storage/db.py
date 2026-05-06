import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scorpius.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    c = conn.cursor()

    # Table missions
    c.execute("""
        CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plateforme TEXT NOT NULL,
            titre TEXT NOT NULL,
            url TEXT UNIQUE,
            budget TEXT,
            budget_min REAL DEFAULT 0,
            description TEXT,
            competences TEXT,
            score INTEGER DEFAULT 0,
            statut TEXT DEFAULT 'nouvelle',
            date_scraped TEXT,
            date_postule TEXT,
            notes TEXT
        )
    """)

    # Table entreprises
    c.execute("""
        CREATE TABLE IF NOT EXISTS entreprises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            secteur TEXT,
            taille TEXT,
            site TEXT,
            linkedin TEXT,
            score_fit INTEGER DEFAULT 0,
            notes TEXT,
            date_ajout TEXT
        )
    """)

    # Table voice (empreintes vocales)
    c.execute("""
        CREATE TABLE IF NOT EXISTS voice_prints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            embedding BLOB NOT NULL,
            date_enregistrement TEXT
        )
    """)

    # Table users
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT DEFAULT 'user',
            date_creation TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_mission(plateforme, titre, url, budget="", description="", competences="", score=0):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO missions
            (plateforme, titre, url, budget, description, competences, score, statut, date_scraped)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'nouvelle', ?)
        """, (plateforme, titre, url, budget, description, competences, score,
              datetime.now().isoformat()))
        conn.commit()
        return c.lastrowid
    except Exception as e:
        print(f"Erreur save_mission: {e}")
        return None
    finally:
        conn.close()


def get_missions(statut=None, limit=50):
    conn = get_connection()
    c = conn.cursor()
    if statut:
        c.execute("SELECT * FROM missions WHERE statut = ? ORDER BY score DESC LIMIT ?",
                  (statut, limit))
    else:
        c.execute("SELECT * FROM missions ORDER BY score DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def update_mission_statut(mission_id, statut, notes=None):
    conn = get_connection()
    c = conn.cursor()
    if notes:
        c.execute("UPDATE missions SET statut = ?, notes = ? WHERE id = ?",
                  (statut, notes, mission_id))
    else:
        c.execute("UPDATE missions SET statut = ? WHERE id = ?", (statut, mission_id))
    conn.commit()
    conn.close()


def get_stats_gains():
    conn = get_connection()
    c = conn.cursor()
    stats = {}

    c.execute("SELECT COALESCE(SUM(budget_min), 0) FROM missions WHERE statut = 'gagnee'")
    stats['acquis'] = round(c.fetchone()[0], 2)

    c.execute("SELECT COALESCE(SUM(budget_min), 0) FROM missions WHERE statut = 'en_cours'")
    stats['en_cours'] = round(c.fetchone()[0], 2)

    c.execute("SELECT COALESCE(SUM(budget_min), 0) FROM missions WHERE statut = 'nouvelle'")
    stats['potentiels'] = round(c.fetchone()[0], 2)

    c.execute("SELECT COUNT(*) FROM missions")
    stats['total_missions'] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM missions WHERE statut = 'nouvelle'")
    stats['nouvelles'] = c.fetchone()[0]

    conn.close()
    return stats
