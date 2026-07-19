"""
storage/prospects.py
Gestion des prospects — Scorpius v2
Compatible PostgreSQL + SQLite
Isolation par user_id
"""

import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from storage.db import get_conn, _using_sqlite

logger = logging.getLogger(__name__)


def init_prospects_db():
    """Initialise la table prospects si elle n'existe pas."""
    with get_conn() as conn:
        if _using_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS prospects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    place_id VARCHAR(255) NOT NULL,
                    nom VARCHAR(255) NOT NULL,
                    secteur VARCHAR(255),
                    telephone VARCHAR(80),
                    adresse TEXT,
                    ville VARCHAR(120),
                    url_site TEXT,
                    google_maps_url TEXT,
                    score_audit INTEGER DEFAULT 0,
                    audit_mobile BOOLEAN DEFAULT 0,
                    audit_performance INTEGER DEFAULT 0,
                    audit_seo INTEGER DEFAULT 0,
                    audit_gmb BOOLEAN DEFAULT 0,
                    seo_title BOOLEAN DEFAULT 0,
                    seo_meta_description BOOLEAN DEFAULT 0,
                    seo_h1 BOOLEAN DEFAULT 0,
                    statut VARCHAR(50) DEFAULT 'a_appeler',
                    raw_google_json TEXT,
                    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                    UNIQUE(place_id, user_id)
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS prospects (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    place_id VARCHAR(255) NOT NULL,
                    nom VARCHAR(255) NOT NULL,
                    secteur VARCHAR(255),
                    telephone VARCHAR(80),
                    adresse TEXT,
                    ville VARCHAR(120),
                    url_site TEXT,
                    google_maps_url TEXT,
                    score_audit INTEGER DEFAULT 0,
                    audit_mobile BOOLEAN DEFAULT FALSE,
                    audit_performance INTEGER DEFAULT 0,
                    audit_seo INTEGER DEFAULT 0,
                    audit_gmb BOOLEAN DEFAULT FALSE,
                    seo_title BOOLEAN DEFAULT FALSE,
                    seo_meta_description BOOLEAN DEFAULT FALSE,
                    seo_h1 BOOLEAN DEFAULT FALSE,
                    statut VARCHAR(50) DEFAULT 'a_appeler',
                    raw_google_json TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(place_id, user_id)
                )
            """))

        # Migration : ajouter user_id si colonne absente
        try:
            if _using_sqlite:
                conn.execute(text("ALTER TABLE prospects ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0"))
                logger.info("Migration : colonne user_id ajoutée ✅")
        except Exception:
            pass

        logger.info("Table prospects initialisée ✅")


def upsert_prospect(data: Dict[str, Any], user_id: int = 0) -> Optional[int]:
    """Insère ou met à jour un prospect pour un utilisateur donné."""
    try:
        place_id = data.get("place_id") or data.get("id", "")
        if not place_id:
            logger.warning("place_id manquant")
            return None

        with get_conn() as conn:
            result = conn.execute(
                text("SELECT id FROM prospects WHERE place_id = :place_id AND user_id = :user_id"),
                {"place_id": place_id, "user_id": user_id}
            ).fetchone()

            params = {
                "place_id":        place_id,
                "user_id":         user_id,
                "nom":             data.get("nom", ""),
                "secteur":         data.get("secteur"),
                "telephone":       data.get("telephone"),
                "adresse":         data.get("adresse"),
                "ville":           data.get("ville"),
                "url_site":        data.get("url_site"),
                "google_maps_url": data.get("google_maps_url"),
                "statut": data.get("statut") or "a_appeler",
                "raw_google_json": json.dumps(data),
            }

            if result:
                conn.execute(text("""
                    UPDATE prospects SET
                        nom = :nom,
                        secteur = :secteur,
                        telephone = :telephone,
                        adresse = :adresse,
                        ville = :ville,
                        url_site = :url_site,
                        google_maps_url = :google_maps_url,
                        raw_google_json = :raw_google_json,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE place_id = :place_id AND user_id = :user_id
                """), params)
                return result[0]
            else:
                if _using_sqlite:
                    conn.execute(text("""
                        INSERT INTO prospects (
                            user_id, place_id, nom, secteur, telephone,
                            adresse, ville, url_site, google_maps_url, statut, raw_google_json
                        ) VALUES (
                            :user_id, :place_id, :nom, :secteur, :telephone,
                            :adresse, :ville, :url_site, :google_maps_url, :statut, :raw_google_json
                        )
                    """), params)
                    row = conn.execute(
                        text("SELECT id FROM prospects WHERE place_id = :place_id AND user_id = :user_id"),
                        {"place_id": place_id, "user_id": user_id}
                    ).fetchone()
                    return row[0] if row else None
                else:
                    row = conn.execute(text("""
                        INSERT INTO prospects (
                            user_id, place_id, nom, secteur, telephone,
                            adresse, ville, url_site, google_maps_url, statut, raw_google_json
                        ) VALUES (
                            :user_id, :place_id, :nom, :secteur, :telephone,
                            :adresse, :ville, :url_site, :google_maps_url, :statut, :raw_google_json
                        ) RETURNING id
                    """), params).fetchone()
                    return row[0] if row else None

    except Exception as e:
        logger.error(f"Erreur upsert prospect: {e}")
        return None


def list_prospects(
    user_id: int = 0,
    limit: int = 100,
    statut: Optional[str] = None
) -> List[Dict]:
    """Liste les prospects d'un utilisateur, triés par score ASC."""
    try:
        with get_conn() as conn:
            if statut:
                rows = conn.execute(text("""
                    SELECT * FROM prospects
                    WHERE user_id = :user_id AND statut = :statut
                    ORDER BY score_audit ASC
                    LIMIT :limit
                """), {"user_id": user_id, "statut": statut, "limit": limit}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT * FROM prospects
                    WHERE user_id = :user_id
                      AND LOWER(COALESCE(statut, '')) <> 'archive'
                    ORDER BY score_audit ASC
                    LIMIT :limit
                """), {"user_id": user_id, "limit": limit}).fetchall()

            return [dict(row._mapping) for row in rows]
    except Exception as e:
        logger.error(f"Erreur list prospects: {e}")
        return []


def get_prospect_by_id(prospect_id: int, user_id: int = 0) -> Optional[Dict]:
    """Récupère un prospect par ID."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                text("SELECT * FROM prospects WHERE id = :id AND user_id = :user_id"),
                {"id": prospect_id, "user_id": user_id}
            ).fetchone()
            return dict(row._mapping) if row else None
    except Exception as e:
        logger.error(f"Erreur get prospect: {e}")
        return None


def update_prospect_statut(prospect_id: int, statut: str, user_id: int = 0):
    """Met à jour le statut d'un prospect."""
    try:
        with get_conn() as conn:
            conn.execute(text("""
                UPDATE prospects SET
                    statut = :statut,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND user_id = :user_id
            """), {"id": prospect_id, "statut": statut, "user_id": user_id})
            logger.info(f"Prospect {prospect_id} statut -> {statut}")
    except Exception as e:
        logger.error(f"Erreur update statut: {e}")
        raise


def update_prospect_audit(prospect_id: int, audit: Dict[str, Any], user_id: int = 0):
    """Met à jour les résultats d'audit."""
    try:
        with get_conn() as conn:
            conn.execute(text("""
                UPDATE prospects SET
                    score_audit          = :score_audit,
                    audit_mobile         = :audit_mobile,
                    audit_performance    = :audit_performance,
                    audit_seo            = :audit_seo,
                    audit_gmb            = :audit_gmb,
                    seo_title            = :seo_title,
                    seo_meta_description = :seo_meta_description,
                    seo_h1               = :seo_h1,
                    updated_at           = CURRENT_TIMESTAMP
                WHERE id = :id AND user_id = :user_id
            """), {
                "id":                   prospect_id,
                "user_id":              user_id,
                "score_audit":          max(0, min(100, int(audit.get("score_audit", 0)))),
                "audit_mobile":         bool(audit.get("audit_mobile", False)),
                "audit_performance":    max(0, min(100, int(audit.get("audit_performance", 0)))),
                "audit_seo":            max(0, min(100, int(audit.get("audit_seo", 0)))),
                "audit_gmb":            bool(audit.get("audit_gmb", False)),
                "seo_title":            audit.get("seo_title", False),
                "seo_meta_description": audit.get("seo_meta_description", False),
                "seo_h1":               audit.get("seo_h1", False),
            })
            logger.info(f"Prospect {prospect_id} audit -> score {audit.get('score', 0)}")
    except Exception as e:
        logger.error(f"Erreur update audit: {e}")
        raise


def count_prospects(user_id: int = 0) -> Dict[str, int]:
    """Compte les prospects par statut pour un utilisateur."""
    try:
        with get_conn() as conn:
            rows = conn.execute(text("""
                SELECT statut, COUNT(*) as nb
                FROM prospects
                WHERE user_id = :user_id
                GROUP BY statut
            """), {"user_id": user_id}).fetchall()

            counts = {"total": 0}
            for row in rows:
                statut = (row[0] or "inconnu").lower()
                nb = row[1]
                counts[statut] = nb
                counts["total"] += nb
            return counts
    except Exception as e:
        logger.error(f"Erreur count prospects: {e}")
        return {"total": 0}


def get_prospect_stats(user_id: int) -> Dict[str, Any]:
    """
    Statistiques du pipeline de prospection pour un utilisateur.
    Les anciennes missions freelance ne sont volontairement pas utilisées.
    """
    empty = {
        "total": 0,
        "nouveaux": 0,
        "a_appeler": 0,
        "a_traiter": 0,
        "missions": 0,
        "appele": 0,
        "relance": 0,
        "gagne": 0,
        "perdu": 0,
        "sans_site": 0,
        "avec_site": 0,
        "avec_telephone": 0,
        "score_moyen": 0,
        "taux_selection": 0,
    }

    try:
        with get_conn() as conn:
            row = conn.execute(text("""
                SELECT
                    COUNT(*) AS total,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'nouveau'
                        THEN 1 ELSE 0
                    END) AS nouveaux,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'a_appeler'
                        THEN 1 ELSE 0
                    END) AS a_appeler,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'mission'
                        THEN 1 ELSE 0
                    END) AS missions,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'appele'
                        THEN 1 ELSE 0
                    END) AS appele,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'relance'
                        THEN 1 ELSE 0
                    END) AS relance,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'gagne'
                        THEN 1 ELSE 0
                    END) AS gagne,

                    SUM(CASE
                        WHEN LOWER(COALESCE(statut, '')) = 'perdu'
                        THEN 1 ELSE 0
                    END) AS perdu,

                    SUM(CASE
                        WHEN TRIM(COALESCE(url_site, '')) = ''
                        THEN 1 ELSE 0
                    END) AS sans_site,

                    SUM(CASE
                        WHEN TRIM(COALESCE(telephone, '')) <> ''
                        THEN 1 ELSE 0
                    END) AS avec_telephone,

                    AVG(COALESCE(score_audit, 0)) AS score_moyen

                FROM prospects
                WHERE user_id = :user_id
                  AND LOWER(COALESCE(statut, '')) <> 'archive'
            """), {"user_id": user_id}).fetchone()

        if not row:
            return empty

        raw = dict(row._mapping)

        def to_int(value):
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        def to_float(value):
            try:
                return round(float(value or 0), 1)
            except (TypeError, ValueError):
                return 0

        stats = {
            "total": to_int(raw.get("total")),
            "nouveaux": to_int(raw.get("nouveaux")),
            "a_appeler": to_int(raw.get("a_appeler")),
            "missions": to_int(raw.get("missions")),
            "appele": to_int(raw.get("appele")),
            "relance": to_int(raw.get("relance")),
            "gagne": to_int(raw.get("gagne")),
            "perdu": to_int(raw.get("perdu")),
            "sans_site": to_int(raw.get("sans_site")),
            "avec_telephone": to_int(raw.get("avec_telephone")),
            "score_moyen": to_float(raw.get("score_moyen")),
        }

        stats["a_traiter"] = stats["nouveaux"] + stats["a_appeler"]
        stats["avec_site"] = max(0, stats["total"] - stats["sans_site"])
        stats["taux_selection"] = round(
            (stats["missions"] / stats["total"] * 100)
            if stats["total"] else 0,
            1,
        )

        return stats

    except Exception as e:
        logger.error(f"Erreur get_prospect_stats: {e}")
        return empty
