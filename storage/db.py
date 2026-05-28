"""
storage/db.py
PostgreSQL (Supabase) avec fallback SQLite — Scorpius v2
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Connexion — PostgreSQL ou SQLite fallback
# ──────────────────────────────────────────────────────────────────────────────

DATABASE_URL  = os.getenv("DATABASE_URL", "")
_using_sqlite = False


def _create_engine_safe():
    global _using_sqlite

    if DATABASE_URL:
        try:
            eng = create_engine(
                DATABASE_URL,
                pool_size=3,
                max_overflow=5,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args={
                    "connect_timeout": 5,
                    "options": "-c timezone=utc",
                },
            )
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("DB -> PostgreSQL Supabase ✅")
            _using_sqlite = False
            return eng
        except Exception as e:
            logger.warning(f"PostgreSQL inaccessible : {e.__class__.__name__}")
            logger.warning("Fallback -> SQLite local")

    _using_sqlite = True
    sqlite_path = Path(__file__).parent.parent / "data" / "scorpius.db"
    sqlite_path.parent.mkdir(exist_ok=True)
    eng = create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
    )
    logger.info(f"DB -> SQLite ({sqlite_path}) ✅")
    return eng


engine = _create_engine_safe()


@contextmanager
def get_conn():
    with engine.connect() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def ping_db() -> bool:
    try:
        with get_conn() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB ping failed : {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Init DB
# ──────────────────────────────────────────────────────────────────────────────

def init_db():
    logger.info(f"Init DB -> {'SQLite' if _using_sqlite else 'PostgreSQL'}")
    with get_conn() as conn:
        if _using_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS utilisateurs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom           TEXT NOT NULL,
                    email         TEXT UNIQUE,
                    password_hash TEXT,
                    voice_auth    INTEGER DEFAULT 0,
                    date_creation TEXT DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS missions (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    titre          TEXT NOT NULL,
                    description    TEXT,
                    budget_min     REAL,
                    budget_max     REAL,
                    devise         TEXT DEFAULT 'EUR',
                    plateforme     TEXT NOT NULL,
                    url            TEXT NOT NULL UNIQUE,
                    client_nom     TEXT,
                    client_info    TEXT DEFAULT '{}',
                    score          INTEGER DEFAULT 0,
                    score_raisons  TEXT,
                    statut         TEXT DEFAULT 'proposee',
                    date_scraping  TEXT DEFAULT (datetime('now')),
                    date_statut    TEXT,
                    notes          TEXT,
                    gains_realises REAL DEFAULT 0,
                    competences    TEXT DEFAULT '[]',
                    notifiee       INTEGER DEFAULT 0
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS voice_profiles (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER,
                    embedding     TEXT NOT NULL,
                    date_creation TEXT DEFAULT (datetime('now')),
                    date_maj      TEXT
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS utilisateurs (
                    id            SERIAL PRIMARY KEY,
                    nom           TEXT NOT NULL,
                    email         TEXT UNIQUE,
                    password_hash TEXT,
                    voice_auth    BOOLEAN DEFAULT FALSE,
                    date_creation TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS calls (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    prospect_id   INTEGER NOT NULL,
                    audio_path    TEXT UNIQUE,
                    transcript    TEXT,
                    status        TEXT DEFAULT 'recording',
                    duration_sec  REAL,
                    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at    DATETIME,
                    privacy_mode  INTEGER DEFAULT 0,
                    audio_saved    INTEGER DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_calls_prospect
                    ON calls(prospect_id);
                CREATE INDEX IF NOT EXISTS idx_calls_status
                    ON calls(status);
                CREATE INDEX IF NOT EXISTS idx_calls_created
                    ON calls(created_at DESC);


                CREATE TABLE IF NOT EXISTS missions (
                    id             SERIAL PRIMARY KEY,
                    titre          TEXT NOT NULL,
                    description    TEXT,
                    budget_min     NUMERIC,
                    budget_max     NUMERIC,
                    devise         TEXT DEFAULT 'EUR',
                    plateforme     TEXT NOT NULL,
                    url            TEXT NOT NULL UNIQUE,
                    client_nom     TEXT,
                    client_info    JSONB DEFAULT '{}',
                    score          INTEGER DEFAULT 0,
                    score_raisons  TEXT,
                    statut         TEXT DEFAULT 'proposee',
                    date_scraping  TIMESTAMPTZ DEFAULT NOW(),
                    date_statut    TIMESTAMPTZ,
                    notes          TEXT,
                    gains_realises NUMERIC DEFAULT 0,
                    competences    JSONB DEFAULT '[]',
                    notifiee       BOOLEAN DEFAULT FALSE
                );

                CREATE INDEX IF NOT EXISTS idx_missions_statut
                    ON missions(statut);
                CREATE INDEX IF NOT EXISTS idx_missions_score
                    ON missions(score DESC);
                CREATE INDEX IF NOT EXISTS idx_missions_date
                    ON missions(date_scraping DESC);

                CREATE TABLE IF NOT EXISTS voice_profiles (
                    id            SERIAL PRIMARY KEY,
                    user_id       INTEGER REFERENCES utilisateurs(id),
                    embedding     JSONB NOT NULL,
                    date_creation TIMESTAMPTZ DEFAULT NOW(),
                    date_maj      TIMESTAMPTZ
                );
                CREATE TABLE IF NOT EXISTS calls (
                    id            SERIAL PRIMARY KEY,
                    prospect_id   INTEGER NOT NULL,
                    audio_path    TEXT UNIQUE,
                    transcript    TEXT,
                    status        TEXT DEFAULT 'recording',
                    duration_sec  NUMERIC,
                    created_at    TIMESTAMPTZ DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ,
                    privacy_mode  BOOLEAN DEFAULT FALSE,
                    audio_saved    BOOLEAN DEFAULT TRUE
                );

                CREATE INDEX IF NOT EXISTS idx_calls_prospect
                    ON calls(prospect_id);
                CREATE INDEX IF NOT EXISTS idx_calls_status
                    ON calls(status);
                CREATE INDEX IF NOT EXISTS idx_calls_created
                    ON calls(created_at DESC);

            """))
    ensure_calls_schema()
    logger.info("DB initialisee OK")


# ──────────────────────────────────────────────────────────────────────────────
# Missions
# ──────────────────────────────────────────────────────────────────────────────

def upsert_mission(mission: dict) -> Optional[int]:
    """Insère ou ignore si URL déjà présente."""
    params = {
        "titre":         mission.get("titre", "Sans titre")[:500],
        "description":   mission.get("description", ""),
        "budget_min":    mission.get("budget_min"),
        "budget_max":    mission.get("budget_max"),
        "devise":        mission.get("devise", "EUR"),
        "plateforme":    mission.get("plateforme", ""),
        "url":           mission.get("url", ""),
        "client_nom":    mission.get("client_nom", ""),
        "client_info":   json.dumps(mission.get("client_info", {})),
        "score":         mission.get("score", 0),
        "score_raisons": mission.get("score_raisons", ""),
        "competences":   json.dumps(mission.get("competences", [])),
    }

    with get_conn() as conn:
        if _using_sqlite:
            result = conn.execute(text("""
                INSERT OR IGNORE INTO missions (
                    titre, description, budget_min, budget_max, devise,
                    plateforme, url, client_nom, client_info,
                    score, score_raisons, competences
                ) VALUES (
                    :titre, :description, :budget_min, :budget_max, :devise,
                    :plateforme, :url, :client_nom, :client_info,
                    :score, :score_raisons, :competences
                )
            """), params)
            return result.lastrowid if result.rowcount > 0 else None
        else:
            result = conn.execute(text("""
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
            """), params)
            row = result.fetchone()
            return row[0] if row else None


def get_missions(
    statut:     Optional[str] = None,
    score_min:  int = 0,
    plateforme: Optional[str] = None,
    recherche:  Optional[str] = None,
    limit:      int = 100,
    offset:     int = 0,
) -> list[dict]:
    conditions = ["score >= :score_min"]
    params: dict = {"score_min": score_min, "limit": limit, "offset": offset}

    if statut:
        conditions.append("statut = :statut")
        params["statut"] = statut

    if plateforme:
        conditions.append("plateforme = :plateforme")
        params["plateforme"] = plateforme

    if recherche:
        if _using_sqlite:
            conditions.append("""
                (titre LIKE :recherche
                 OR description LIKE :recherche
                 OR client_nom  LIKE :recherche)
            """)
        else:
            conditions.append("""
                (titre ILIKE :recherche
                 OR description ILIKE :recherche
                 OR client_nom  ILIKE :recherche)
            """)
        params["recherche"] = f"%{recherche}%"

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT id, titre, description,
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
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM missions WHERE id = :id"),
            {"id": mission_id}
        ).fetchone()
        return _row_to_dict(row) if row else None


def update_statut_mission(
    mission_id: int,
    statut:     str,
    gains:      Optional[float] = None,
    notes:      Optional[str]   = None,
):
    STATUTS_VALIDES = {
        "proposee", "en_attente", "en_cours", "terminee", "refusee"
    }
    if statut not in STATUTS_VALIDES:
        raise ValueError(f"Statut invalide : '{statut}'")

    sets   = ["statut = :statut"]
    params: dict = {"statut": statut, "id": mission_id}

    if _using_sqlite:
        sets.append("date_statut = datetime('now')")
    else:
        sets.append("date_statut = NOW()")

    if gains is not None:
        sets.append("gains_realises = :gains")
        params["gains"] = gains

    if notes is not None:
        sets.append("notes = :notes")
        params["notes"] = notes

    with get_conn() as conn:
        conn.execute(
            text(f"UPDATE missions SET {', '.join(sets)} WHERE id = :id"),
            params
        )


def delete_mission(mission_id: int):
    with get_conn() as conn:
        conn.execute(
            text("DELETE FROM missions WHERE id = :id"),
            {"id": mission_id}
        )


def get_missions_non_notifiees() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(text("""
            SELECT * FROM missions
            WHERE notifiee = 0
            ORDER BY score DESC
            LIMIT 20
        """)).fetchall()
        return [_row_to_dict(r) for r in rows]


def marquer_notifiee(mission_id: int):
    with get_conn() as conn:
        conn.execute(
            text("UPDATE missions SET notifiee = 1 WHERE id = :id"),
            {"id": mission_id}
        )


# ──────────────────────────────────────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────────────────────────────────────

def get_stats_gains() -> dict:
    sql = text("""
        SELECT
            COALESCE(SUM(CASE WHEN statut = 'terminee'
                THEN gains_realises ELSE 0 END), 0)  AS acquis,
            COALESCE(SUM(CASE WHEN statut = 'en_cours'
                THEN gains_realises ELSE 0 END), 0)  AS en_cours,
            COALESCE(SUM(CASE WHEN statut = 'en_attente'
                THEN budget_min ELSE 0 END), 0)      AS potentiels,
            COUNT(CASE WHEN statut = 'terminee'
                THEN 1 END)                          AS missions_terminees,
            COUNT(CASE WHEN statut = 'en_cours'
                THEN 1 END)                          AS missions_actives
        FROM missions
    """)
    with get_conn() as conn:
        row = conn.execute(sql).fetchone()
        return dict(row._mapping) if row else {}


def get_compteurs_statut() -> dict:
    compteurs = {
        "proposee": 0, "en_attente": 0, "en_cours": 0,
        "terminee": 0, "refusee": 0, "total": 0,
    }
    with get_conn() as conn:
        rows = conn.execute(text("""
            SELECT statut, COUNT(*) as nb
            FROM missions GROUP BY statut
        """)).fetchall()
        for row in rows:
            s = row[0]
            n = row[1]
            if s in compteurs:
                compteurs[s] = n
            compteurs["total"] += n
    return compteurs


def get_evolution_mensuelle(mois: int = 6) -> list[dict]:
    if _using_sqlite:
        sql = text("""
            SELECT
                strftime('%Y-%m', date_statut) AS mois,
                COALESCE(SUM(gains_realises), 0) AS gains,
                COUNT(*) AS nb_missions
            FROM missions
            WHERE statut = 'terminee'
              AND date_statut IS NOT NULL
            GROUP BY mois
            ORDER BY mois DESC
            LIMIT :mois
        """)
    else:
        sql = text("""
            SELECT
                TO_CHAR(date_statut, 'YYYY-MM') AS mois,
                COALESCE(SUM(gains_realises), 0) AS gains,
                COUNT(*) AS nb_missions
            FROM missions
            WHERE statut = 'terminee'
              AND date_statut IS NOT NULL
            GROUP BY mois
            ORDER BY mois DESC
            LIMIT :mois
        """)
    with get_conn() as conn:
        rows = conn.execute(sql, {"mois": mois}).fetchall()
        return [dict(row._mapping) for row in rows]


def get_plateformes_disponibles() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT plateforme
            FROM missions ORDER BY plateforme
        """)).fetchall()
        return [row[0] for row in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Voice Auth
# ──────────────────────────────────────────────────────────────────────────────

def save_voice_embedding(user_id: int, embedding: list[float]):
    emb_json = json.dumps(embedding)
    with get_conn() as conn:
        existing = conn.execute(
            text("SELECT id FROM voice_profiles WHERE user_id = :uid"),
            {"uid": user_id}
        ).fetchone()
        if existing:
            conn.execute(text("""
                UPDATE voice_profiles
                SET embedding = :emb, date_maj = datetime('now')
                WHERE user_id = :uid
            """), {"emb": emb_json, "uid": user_id})
        else:
            conn.execute(text("""
                INSERT INTO voice_profiles (user_id, embedding)
                VALUES (:uid, :emb)
            """), {"uid": user_id, "emb": emb_json})


def get_voice_embedding(user_id: int) -> Optional[list[float]]:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT embedding FROM voice_profiles WHERE user_id = :uid"),
            {"uid": user_id}
        ).fetchone()
        if row:
            data = row[0]
            return json.loads(data) if isinstance(data, str) else data
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Utilisateurs
# ──────────────────────────────────────────────────────────────────────────────

def get_or_create_user(nom: str = "Admin", email: str = "") -> dict:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM utilisateurs LIMIT 1")
        ).fetchone()
        if row:
            return dict(row._mapping)

        if _using_sqlite:
            conn.execute(text("""
                INSERT INTO utilisateurs (nom, email)
                VALUES (:nom, :email)
            """), {"nom": nom, "email": email})
            row = conn.execute(
                text("SELECT * FROM utilisateurs LIMIT 1")
            ).fetchone()
        else:
            result = conn.execute(text("""
                INSERT INTO utilisateurs (nom, email)
                VALUES (:nom, :email)
                RETURNING *
            """), {"nom": nom, "email": email})
            row = result.fetchone()

        return dict(row._mapping)


# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ──────────────────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    d = dict(row._mapping)

    for field in ("client_info", "competences", "reputation"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = {}

    for field in ("date_scraping", "date_statut", "date_creation", "date_maj"):
        if field in d and d[field] is not None:
            if hasattr(d[field], "isoformat"):
                d[field] = d[field].isoformat()

    return d

# ══════════════════════════════════════════════════════════════════════════════
# SCORPIUS INBOX — Notifications internes
# ══════════════════════════════════════════════════════════════════════════════

def ensure_notifications_table():
    """
    Crée la table notifications si elle n'existe pas.
    Compatible SQLite fallback + PostgreSQL Supabase.
    """
    using_sqlite = globals().get("_using_sqlite", True)

    with get_conn() as conn:
        if using_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    type        TEXT NOT NULL,
                    title       TEXT NOT NULL,
                    body        TEXT,
                    source      TEXT DEFAULT 'scorpius',
                    link        TEXT,
                    read_at     TEXT,
                    created_at  TEXT DEFAULT (datetime('now')),
                    data_json   TEXT DEFAULT '{}'
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_notifications_read
                ON notifications(read_at)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_notifications_created
                ON notifications(created_at)
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id          SERIAL PRIMARY KEY,
                    type        TEXT NOT NULL,
                    title       TEXT NOT NULL,
                    body        TEXT,
                    source      TEXT DEFAULT 'scorpius',
                    link        TEXT,
                    read_at     TIMESTAMPTZ,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    data_json   JSONB DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_notifications_read
                ON notifications(read_at);

                CREATE INDEX IF NOT EXISTS idx_notifications_created
                ON notifications(created_at DESC);
            """))


def create_notification(
    type: str,
    title: str,
    body: str = "",
    source: str = "scorpius",
    link: str = "",
    data: Optional[dict] = None,
) -> Optional[int]:
    """
    Crée une notification interne Scorpius.

    Returns:
        id de la notification créée
    """
    ensure_notifications_table()
    using_sqlite = globals().get("_using_sqlite", True)

    payload = {
        "type": type,
        "title": title,
        "body": body,
        "source": source,
        "link": link,
        "data_json": json.dumps(data or {}),
    }

    with get_conn() as conn:
        if using_sqlite:
            result = conn.execute(text("""
                INSERT INTO notifications (
                    type, title, body, source, link, data_json
                ) VALUES (
                    :type, :title, :body, :source, :link, :data_json
                )
            """), payload)
            return result.lastrowid
        else:
            result = conn.execute(text("""
                INSERT INTO notifications (
                    type, title, body, source, link, data_json
                ) VALUES (
                    :type, :title, :body, :source, :link, :data_json
                )
                RETURNING id
            """), payload)
            row = result.fetchone()
            return row[0] if row else None


def get_notifications(
    unread_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Liste les notifications internes.
    """
    ensure_notifications_table()

    conditions = []
    params = {
        "limit": limit,
        "offset": offset,
    }

    if unread_only:
        conditions.append("read_at IS NULL")

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    with get_conn() as conn:
        rows = conn.execute(text(f"""
            SELECT
                id, type, title, body, source, link,
                read_at, created_at, data_json
            FROM notifications
            {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

    return [_notification_row_to_dict(r) for r in rows]


def get_unread_notifications_count() -> int:
    """
    Nombre de notifications non lues.
    """
    ensure_notifications_table()

    with get_conn() as conn:
        row = conn.execute(text("""
            SELECT COUNT(*) FROM notifications
            WHERE read_at IS NULL
        """)).fetchone()

    return int(row[0]) if row else 0


def mark_notification_read(notification_id: int):
    """
    Marque une notification comme lue.
    """
    ensure_notifications_table()
    using_sqlite = globals().get("_using_sqlite", True)

    with get_conn() as conn:
        if using_sqlite:
            conn.execute(text("""
                UPDATE notifications
                SET read_at = datetime('now')
                WHERE id = :id
            """), {"id": notification_id})
        else:
            conn.execute(text("""
                UPDATE notifications
                SET read_at = NOW()
                WHERE id = :id
            """), {"id": notification_id})


def mark_all_notifications_read():
    """
    Marque toutes les notifications comme lues.
    """
    ensure_notifications_table()
    using_sqlite = globals().get("_using_sqlite", True)

    with get_conn() as conn:
        if using_sqlite:
            conn.execute(text("""
                UPDATE notifications
                SET read_at = datetime('now')
                WHERE read_at IS NULL
            """))
        else:
            conn.execute(text("""
                UPDATE notifications
                SET read_at = NOW()
                WHERE read_at IS NULL
            """))


def delete_notification(notification_id: int):
    """
    Supprime une notification.
    """
    ensure_notifications_table()

    with get_conn() as conn:
        conn.execute(text("""
            DELETE FROM notifications
            WHERE id = :id
        """), {"id": notification_id})


def _notification_row_to_dict(row) -> dict:
    """
    Convertit une notification SQLAlchemy Row en dict propre.
    """
    if row is None:
        return {}

    d = dict(row._mapping)

    if isinstance(d.get("data_json"), str):
        try:
            d["data_json"] = json.loads(d["data_json"])
        except Exception:
            d["data_json"] = {}

    for field in ("read_at", "created_at"):
        if d.get(field) is not None and hasattr(d[field], "isoformat"):
            d[field] = d[field].isoformat()

    return d


# ──────────────────────────────────────────────────────────────────────────────
# Calls / Voice Prospecting
# ──────────────────────────────────────────────────────────────────────────────



# ──────────────────────────────────────────────────────────────────────────────
# Calls / Voice Prospecting - helpers STT
# ──────────────────────────────────────────────────────────────────────────────

def get_call_by_id(call_id: int) -> Optional[dict]:
    """Retourne un appel par id."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                text("SELECT * FROM calls WHERE id = :id"),
                {"id": call_id},
            ).mappings().first()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"❌ get_call_by_id failed: {e}")
        return None


def update_call_status(call_id: int, status: str) -> bool:
    """Met à jour le statut d'un appel."""
    try:
        with get_conn() as conn:
            conn.execute(text("""
                UPDATE calls
                SET status = :status,
                    updated_at = :updated_at
                WHERE id = :id
            """), {
                "id": call_id,
                "status": status,
                "updated_at": datetime.utcnow(),
            })
        return True
    except Exception as e:
        logger.error(f"❌ update_call_status failed: {e}")
        return False


def update_call_transcript(
    call_id: int,
    transcript: str,
    status: str = "transcribed",
    duration_sec: Optional[float] = None,
) -> bool:
    """Sauve la transcription d'un appel."""
    try:
        with get_conn() as conn:
            conn.execute(text("""
                UPDATE calls
                SET transcript = :transcript,
                    status = :status,
                    duration_sec = COALESCE(:duration_sec, duration_sec),
                    updated_at = :updated_at
                WHERE id = :id
            """), {
                "id": call_id,
                "transcript": transcript,
                "status": status,
                "duration_sec": duration_sec,
                "updated_at": datetime.utcnow(),
            })
        return True
    except Exception as e:
        logger.error(f"❌ update_call_transcript failed: {e}")
        return False



# ──────────────────────────────────────────────────────────────────────────────
# Calls / Voice Prospecting - privacy-aware persistence
# ──────────────────────────────────────────────────────────────────────────────

# Privacy-aware override for create_call_record
def create_call_record(
    prospect_id: int,
    audio_path: Optional[str] = None,
    duration_sec: Optional[float] = None,
    transcript: Optional[str] = None,
    status: str = "recording",
    privacy_mode: bool = False,
    audio_saved: bool = True,
) -> Optional[int]:
    """Crée un enregistrement d'appel, compatible mode privacy sans audio sauvegardé."""
    now = datetime.utcnow()

    params = {
        "prospect_id": prospect_id,
        "audio_path": audio_path,
        "duration_sec": duration_sec,
        "transcript": transcript,
        "status": status,
        "privacy_mode": bool(privacy_mode),
        "audio_saved": bool(audio_saved),
        "created_at": now,
        "updated_at": now,
    }

    try:
        with get_conn() as conn:
            if _using_sqlite:
                conn.execute(text("""
                    INSERT INTO calls (
                        prospect_id, audio_path, duration_sec,
                        transcript, status, privacy_mode, audio_saved,
                        created_at, updated_at
                    )
                    VALUES (
                        :prospect_id, :audio_path, :duration_sec,
                        :transcript, :status, :privacy_mode, :audio_saved,
                        :created_at, :updated_at
                    )
                """), params)
                call_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            else:
                call_id = conn.execute(text("""
                    INSERT INTO calls (
                        prospect_id, audio_path, duration_sec,
                        transcript, status, privacy_mode, audio_saved,
                        created_at, updated_at
                    )
                    VALUES (
                        :prospect_id, :audio_path, :duration_sec,
                        :transcript, :status, :privacy_mode, :audio_saved,
                        :created_at, :updated_at
                    )
                    RETURNING id
                """), params).scalar()

        logger.info(
            f"📞 Call DB créé id={call_id} prospect={prospect_id} "
            f"privacy={privacy_mode} audio_saved={audio_saved}"
        )
        return int(call_id) if call_id is not None else None

    except Exception as e:
        logger.error(f"❌ create_call_record failed: {e}")
        return None



# ──────────────────────────────────────────────────────────────────────────────
# Calls schema guard
# ──────────────────────────────────────────────────────────────────────────────

def ensure_calls_schema() -> None:
    """Garantit le schéma calls sur SQLite et PostgreSQL."""
    with get_conn() as conn:
        if _using_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calls (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    prospect_id         INTEGER NOT NULL,
                    date                DATETIME,
                    duree               INTEGER,
                    audio_path          TEXT,
                    transcript          TEXT,
                    probleme_detecte    TEXT,
                    solution_proposee   TEXT,
                    interet_percu       VARCHAR(80),
                    email_suivi_draft   TEXT,
                    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status              TEXT DEFAULT 'recording',
                    duration_sec        REAL,
                    updated_at          DATETIME,
                    privacy_mode        INTEGER DEFAULT 0,
                    audio_saved         INTEGER DEFAULT 1
                );
            """))

            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(calls)"))}

            if "audio_path" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN audio_path TEXT"))
            if "transcript" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN transcript TEXT"))
            if "created_at" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN created_at DATETIME"))
            if "status" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN status TEXT DEFAULT 'recording'"))
            if "duration_sec" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN duration_sec REAL"))
            if "updated_at" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN updated_at DATETIME"))
            if "privacy_mode" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN privacy_mode INTEGER DEFAULT 0"))
            if "audio_saved" not in cols:
                conn.execute(text("ALTER TABLE calls ADD COLUMN audio_saved INTEGER DEFAULT 1"))

            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_prospect ON calls(prospect_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at DESC)"))

        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calls (
                    id                  SERIAL PRIMARY KEY,
                    prospect_id         INTEGER NOT NULL,
                    audio_path          TEXT,
                    transcript          TEXT,
                    status              TEXT DEFAULT 'recording',
                    duration_sec        NUMERIC,
                    created_at          TIMESTAMPTZ DEFAULT NOW(),
                    updated_at          TIMESTAMPTZ,
                    privacy_mode        BOOLEAN DEFAULT FALSE,
                    audio_saved         BOOLEAN DEFAULT TRUE
                );
            """))

            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS audio_path TEXT"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS transcript TEXT"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'recording'"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS duration_sec NUMERIC"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS privacy_mode BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS audio_saved BOOLEAN DEFAULT TRUE"))

            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_prospect ON calls(prospect_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at DESC)"))

    logger.info("✅ calls schema OK")
