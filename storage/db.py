"""
storage/db.py
Couche base de données PostgreSQL (Supabase) — Scorpius v2

STEP 09 :
- SQLAlchemy Core (pas d'ORM, requêtes SQL directes)
- Tables : missions, entreprises, voice_profiles, utilisateurs
- Compatible Supabase PostgreSQL
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    text,
    MetaData,
)
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Connexion
# ──────────────────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL manquant dans .env\n"
        "Format : postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres"
    )

# SQLAlchemy engine avec pool de connexions
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,      # Vérifie la connexion avant usage
    pool_recycle=300,        # Recycle les connexions toutes les 5 min
    connect_args={
        "connect_timeout": 10,
        "options": "-c timezone=utc",
    },
)


@contextmanager
def get_conn():
    """
    Context manager — connexion PostgreSQL via SQLAlchemy.
    Commit automatique, rollback en cas d'erreur.

    Usage :
        with get_conn() as conn:
            conn.execute(text("SELECT 1"))
    """
    with engine.connect() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ══════════════════════════════════════════════════════════════════════════════
# INIT — Création des tables
# ══════════════════════════════════════════════════════════════════════════════

def init_db():
    """
    Crée toutes les tables si elles n'existent pas.
    Idempotent — peut être appelé plusieurs fois sans problème.
    """
    logger.info("Initialisation base de données PostgreSQL...")

    with get_conn() as conn:
        conn.execute(text("""
        -- ─────────────────────────────────────────
        -- Utilisateurs dashboard
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id              SERIAL PRIMARY KEY,
            nom             TEXT NOT NULL,
            email           TEXT UNIQUE,
            password_hash   TEXT,
            voice_auth      BOOLEAN DEFAULT FALSE,
            date_creation   TIMESTAMPTZ DEFAULT NOW()
        );

        -- ─────────────────────────────────────────
        -- Missions scrapées
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS missions (
            id              SERIAL PRIMARY KEY,
            titre           TEXT NOT NULL,
            description     TEXT,
            budget_min      NUMERIC,
            budget_max      NUMERIC,
            devise          TEXT DEFAULT 'EUR',
            plateforme      TEXT NOT NULL,
            url             TEXT NOT NULL UNIQUE,
            client_nom      TEXT,
            client_info     JSONB DEFAULT '{}',
            score           INTEGER DEFAULT 0,
            score_raisons   TEXT,
            statut          TEXT DEFAULT 'proposee',
            date_scraping   TIMESTAMPTZ DEFAULT NOW(),
            date_statut     TIMESTAMPTZ,
            notes           TEXT,
            gains_realises  NUMERIC DEFAULT 0,
            competences     JSONB DEFAULT '[]'
        );

        CREATE INDEX IF NOT EXISTS idx_missions_statut
            ON missions(statut);
        CREATE INDEX IF NOT EXISTS idx_missions_score
            ON missions(score DESC);
        CREATE INDEX IF NOT EXISTS idx_missions_date
            ON missions(date_scraping DESC);
        CREATE INDEX IF NOT EXISTS idx_missions_plateforme
            ON missions(plateforme);

        -- ─────────────────────────────────────────
        -- Entreprises (cache recherche)
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS entreprises (
            id          SERIAL PRIMARY KEY,
            nom         TEXT NOT NULL UNIQUE,
            secteur     TEXT,
            taille      TEXT,
            site_web    TEXT,
            reputation  JSONB DEFAULT '{}',
            date_maj    TIMESTAMPTZ DEFAULT NOW()
        );

        -- ─────────────────────────────────────────
        -- Empreintes vocales
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS voice_profiles (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER REFERENCES utilisateurs(id),
            embedding       JSONB NOT NULL,
            date_creation   TIMESTAMPTZ DEFAULT NOW(),
            date_maj        TIMESTAMPTZ
        );
        """))

    logger.info("Tables créées / vérifiées ✅")


# ══════════════════════════════════════════════════════════════════════════════
# MISSIONS — CRUD
# ══════════════════════════════════════════════════════════════════════════════

def upsert_mission(mission: dict) -> Optional[int]:
    """
    Insère une mission ou ignore si l'URL existe déjà (déduplication).

    Returns:
        int  : id de la mission insérée
        None : mission déjà en base (doublon)
    """
    sql = text("""
        INSERT INTO missions (
            titre, description, budget_min, budget_max, devise,
            plateforme, url, client_nom, client_info,
            score, score_raisons, competences, date_scraping
        ) VALUES (
            :titre, :description, :budget_min, :budget_max, :devise,
            :plateforme, :url, :client_nom, :client_info,
            :score, :score_raisons, :competences, NOW()
        )
        ON CONFLICT (url) DO NOTHING
        RETURNING id
    """)

    params = {
        "titre":        mission.get("titre", "Sans titre")[:500],
        "description":  mission.get("description", ""),
        "budget_min":   mission.get("budget_min"),
        "budget_max":   mission.get("budget_max"),
        "devise":       mission.get("devise", "EUR"),
        "plateforme":   mission.get("plateforme", ""),
        "url":          mission.get("url", ""),
        "client_nom":   mission.get("client_nom", ""),
        "client_info":  json.dumps(mission.get("client_info", {})),
        "score":        mission.get("score", 0),
        "score_raisons": mission.get("score_raisons", ""),
        "competences":  json.dumps(mission.get("competences", [])),
    }

    with get_conn() as conn:
        result = conn.execute(sql, params)
        row = result.fetchone()
        return row[0] if row else None


def get_missions(
    statut: Optional[str] = None,
    score_min: int = 0,
    plateforme: Optional[str] = None,
    recherche: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Récupère les missions avec filtres.

    Args:
        statut      : filtre par statut
        score_min   : score minimum
        plateforme  : filtre par plateforme
        recherche   : recherche texte (titre + description)
        limit       : nombre max de résultats
        offset      : pagination

    Returns:
        list[dict] : missions triées par score décroissant
    """
    conditions = ["score >= :score_min"]
    params: dict = {
        "score_min": score_min,
        "limit":     limit,
        "offset":    offset,
    }

    if statut:
        conditions.append("statut = :statut")
        params["statut"] = statut

    if plateforme:
        conditions.append("plateforme = :plateforme")
        params["plateforme"] = plateforme

    if recherche:
        conditions.append("""
            (titre ILIKE :recherche
             OR description ILIKE :recherche
             OR client_nom ILIKE :recherche)
        """)
        params["recherche"] = f"%{recherche}%"

    where = " AND ".join(conditions)

    sql = text(f"""
        SELECT
            id, titre, description,
            budget_min, budget_max, devise,
            plateforme, url, client_nom,
            score, score_raisons, statut,
            date_scraping, date_statut,
            notes, gains_realises, competences
        FROM missions
        WHERE {where}
        ORDER BY score DESC, date_scraping DESC
        LIMIT :limit OFFSET :offset
    """)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_mission_by_id(mission_id: int) -> Optional[dict]:
    """Récupère une mission par son ID."""
    sql = text("SELECT * FROM missions WHERE id = :id")
    with get_conn() as conn:
        row = conn.execute(sql, {"id": mission_id}).fetchone()
        return _row_to_dict(row) if row else None


def update_statut_mission(
    mission_id: int,
    statut: str,
    gains: Optional[float] = None,
    notes: Optional[str] = None,
):
    """
    Met à jour le statut d'une mission.

    Args:
        mission_id : ID de la mission
        statut     : nouveau statut
        gains      : gains réalisés (si terminée)
        notes      : notes libres
    """
    STATUTS_VALIDES = {
        "proposee", "en_attente", "en_cours", "terminee", "refusee"
    }
    if statut not in STATUTS_VALIDES:
        raise ValueError(
            f"Statut invalide : '{statut}'. "
            f"Valides : {STATUTS_VALIDES}"
        )

    # Construit la requête dynamiquement selon les champs fournis
    sets = ["statut = :statut", "date_statut = NOW()"]
    params: dict = {"statut": statut, "id": mission_id}

    if gains is not None:
        sets.append("gains_realises = :gains")
        params["gains"] = gains

    if notes is not None:
        sets.append("notes = :notes")
        params["notes"] = notes

    sql = text(f"""
        UPDATE missions
        SET {', '.join(sets)}
        WHERE id = :id
    """)

    with get_conn() as conn:
        conn.execute(sql, params)


def delete_mission(mission_id: int):
    """Supprime une mission."""
    with get_conn() as conn:
        conn.execute(
            text("DELETE FROM missions WHERE id = :id"),
            {"id": mission_id}
        )


# ══════════════════════════════════════════════════════════════════════════════
# STATS & GAINS
# ══════════════════════════════════════════════════════════════════════════════

def get_stats_gains() -> dict:
    """
    Calcule les gains acquis, en cours et potentiels.

    Returns:
        dict : {acquis, en_cours, potentiels,
                missions_terminees, missions_actives}
    """
    sql = text("""
        SELECT
            COALESCE(SUM(CASE WHEN statut = 'terminee'
                THEN gains_realises ELSE 0 END), 0)   AS acquis,
            COALESCE(SUM(CASE WHEN statut = 'en_cours'
                THEN gains_realises ELSE 0 END), 0)   AS en_cours,
            COALESCE(SUM(CASE WHEN statut = 'en_attente'
                THEN budget_min ELSE 0 END), 0)       AS potentiels,
            COUNT(CASE WHEN statut = 'terminee'
                THEN 1 END)                           AS missions_terminees,
            COUNT(CASE WHEN statut = 'en_cours'
                THEN 1 END)                           AS missions_actives
        FROM missions
    """)
    with get_conn() as conn:
        row = conn.execute(sql).fetchone()
        return dict(row._mapping) if row else {}


def get_compteurs_statut() -> dict:
    """Compte les missions par statut."""
    sql = text("""
        SELECT statut, COUNT(*) as nb
        FROM missions
        GROUP BY statut
    """)
    compteurs = {
        "proposee":   0,
        "en_attente": 0,
        "en_cours":   0,
        "terminee":   0,
        "refusee":    0,
        "total":      0,
    }
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
        for row in rows:
            statut = row[0]
            nb     = row[1]
            if statut in compteurs:
                compteurs[statut] = nb
            compteurs["total"] += nb
    return compteurs


def get_evolution_mensuelle(mois: int = 6) -> list[dict]:
    """
    Gains par mois sur les N derniers mois.

    Returns:
        list[dict] : [{mois, gains, nb_missions}]
    """
    sql = text("""
        SELECT
            TO_CHAR(date_statut, 'YYYY-MM')  AS mois,
            COALESCE(SUM(gains_realises), 0) AS gains,
            COUNT(*)                         AS nb_missions
        FROM missions
        WHERE statut = 'terminee'
          AND date_statut IS NOT NULL
          AND date_statut >= NOW() - INTERVAL ':mois months'
        GROUP BY mois
        ORDER BY mois DESC
    """)
    with get_conn() as conn:
        rows = conn.execute(sql, {"mois": mois}).fetchall()
        return [dict(row._mapping) for row in rows]


def get_plateformes_disponibles() -> list[str]:
    """Liste des plateformes présentes en base."""
    sql = text("""
        SELECT DISTINCT plateforme
        FROM missions
        ORDER BY plateforme
    """)
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
        return [row[0] for row in rows]


# ══════════════════════════════════════════════════════════════════════════════
# VOICE AUTH
# ══════════════════════════════════════════════════════════════════════════════

def save_voice_embedding(
    user_id: int,
    embedding: list[float],
):
    """Sauvegarde ou met à jour l'empreinte vocale."""
    embedding_json = json.dumps(embedding)

    sql_check = text(
        "SELECT id FROM voice_profiles WHERE user_id = :user_id"
    )
    with get_conn() as conn:
        existing = conn.execute(
            sql_check, {"user_id": user_id}
        ).fetchone()

        if existing:
            conn.execute(text("""
                UPDATE voice_profiles
                SET embedding = :emb, date_maj = NOW()
                WHERE user_id = :user_id
            """), {"emb": embedding_json, "user_id": user_id})
        else:
            conn.execute(text("""
                INSERT INTO voice_profiles (user_id, embedding)
                VALUES (:user_id, :emb)
            """), {"user_id": user_id, "emb": embedding_json})


def get_voice_embedding(user_id: int) -> Optional[list[float]]:
    """Récupère l'empreinte vocale. None si pas encore enrôlé."""
    sql = text(
        "SELECT embedding FROM voice_profiles WHERE user_id = :user_id"
    )
    with get_conn() as conn:
        row = conn.execute(sql, {"user_id": user_id}).fetchone()
        if row:
            data = row[0]
            if isinstance(data, str):
                return json.loads(data)
            return data
        return None


# ══════════════════════════════════════════════════════════════════════════════
# UTILISATEURS
# ══════════════════════════════════════════════════════════════════════════════

def get_or_create_user(nom: str, email: str = "") -> dict:
    """
    Récupère ou crée l'utilisateur principal.
    Scorpius v2 = 1 utilisateur par instance.
    """
    with get_conn() as conn:
        # Cherche user existant
        row = conn.execute(
            text("SELECT * FROM utilisateurs LIMIT 1")
        ).fetchone()

        if row:
            return dict(row._mapping)

        # Crée le premier utilisateur
        result = conn.execute(text("""
            INSERT INTO utilisateurs (nom, email)
            VALUES (:nom, :email)
            RETURNING *
        """), {"nom": nom, "email": email})

        row = result.fetchone()
        return dict(row._mapping)


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES INTERNES
# ══════════════════════════════════════════════════════════════════════════════

def _row_to_dict(row) -> dict:
    """Convertit une Row SQLAlchemy en dict propre."""
    if row is None:
        return {}
    d = dict(row._mapping)

    # Désérialise les champs JSON si nécessaire
    for field in ("client_info", "competences", "reputation"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = {}

    # Convertit les dates en string ISO
    for field in ("date_scraping", "date_statut", "date_creation", "date_maj"):
        if field in d and d[field] is not None:
            if hasattr(d[field], "isoformat"):
                d[field] = d[field].isoformat()

    return d


def ping_db() -> bool:
    """Vérifie que la DB est accessible. True si OK."""
    try:
        with get_conn() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB inaccessible : {e}")
        return False