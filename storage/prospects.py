from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, Boolean, DateTime,
    select, insert, update
)

from storage.db import engine

metadata = MetaData()

prospects = Table(
    "prospects",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("place_id", String(255), unique=True, nullable=False),
    Column("nom", String(255), nullable=False),
    Column("secteur", String(255)),
    Column("telephone", String(80)),
    Column("adresse", Text),
    Column("ville", String(120)),
    Column("url_site", Text, nullable=True),
    Column("google_maps_url", Text, nullable=True),
    Column("score_audit", Integer, default=0),
    Column("audit_mobile", Boolean, default=False),
    Column("audit_performance", Integer, default=0),
    Column("audit_seo", Integer, default=0),
    Column("audit_gmb", Boolean, default=True),
    Column("seo_title", Boolean, default=False),
    Column("seo_meta_description", Boolean, default=False),
    Column("seo_h1", Boolean, default=False),
    Column("statut", String(50), default="a_appeler"),
    Column("raw_google_json", Text),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow),
)

calls = Table(
    "calls",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("prospect_id", Integer, nullable=False),
    Column("date", DateTime, default=datetime.utcnow),
    Column("duree", Integer, default=0),
    Column("audio_path", Text),
    Column("transcript", Text),
    Column("probleme_detecte", Text),
    Column("solution_proposee", Text),
    Column("interet_percu", String(80)),
    Column("email_suivi_draft", Text),
    Column("created_at", DateTime, default=datetime.utcnow),
)

def init_prospects_db():
    metadata.create_all(engine)

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    data = dict(row._mapping)
    if data.get("raw_google_json"):
        try:
            data["raw_google"] = json.loads(data["raw_google_json"])
        except Exception:
            data["raw_google"] = None
    return data

def upsert_prospect(data: dict) -> Optional[int]:
    place_id = data.get("place_id")
    if not place_id:
        return None

    payload = {
        "place_id": place_id,
        "nom": data.get("nom", ""),
        "secteur": data.get("secteur"),
        "telephone": data.get("telephone"),
        "adresse": data.get("adresse"),
        "ville": data.get("ville"),
        "url_site": data.get("url_site"),
        "google_maps_url": data.get("google_maps_url"),
        "audit_gmb": bool(data.get("audit_gmb", True)),
        "raw_google_json": data.get("raw_google_json", "{}"),  # Préserve le JSON original
        "updated_at": datetime.utcnow(),
    }

    with engine.begin() as conn:
        existing = conn.execute(
            select(prospects.c.id).where(prospects.c.place_id == place_id)
        ).first()

        if existing:
            prospect_id = existing[0]
            conn.execute(
                update(prospects)
                .where(prospects.c.id == prospect_id)
                .values(**payload)
            )
            return prospect_id

        result = conn.execute(
            insert(prospects).values(**payload, created_at=datetime.utcnow())
        )
        return result.inserted_primary_key[0]

def list_prospects(limit: int = 100, statut: str | None = None) -> list[dict]:
    query = select(prospects).order_by(prospects.c.created_at.desc()).limit(limit)
    if statut:
        query = query.where(prospects.c.statut == statut)

    with engine.begin() as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_dict(r) for r in rows]

def get_prospect_by_id(prospect_id: int) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(prospects).where(prospects.c.id == prospect_id)
        ).first()
    return _row_to_dict(row) if row else None

def update_prospect_audit(prospect_id: int, audit: dict):
    with engine.begin() as conn:
        conn.execute(
            update(prospects)
            .where(prospects.c.id == prospect_id)
            .values(
                score_audit=audit.get("score_audit", 0),
                audit_mobile=bool(audit.get("audit_mobile", False)),
                audit_performance=int(audit.get("audit_performance", 0) or 0),
                audit_seo=int(audit.get("audit_seo", 0) or 0),
                audit_gmb=bool(audit.get("audit_gmb", True)),
                seo_title=bool(audit.get("seo_title", False)),
                seo_meta_description=bool(audit.get("seo_meta_description", False)),
                seo_h1=bool(audit.get("seo_h1", False)),
                updated_at=datetime.utcnow(),
            )
        )

def update_prospect_statut(prospect_id: int, statut: str):
    """Met à jour le statut d'un prospect."""
    with engine.begin() as conn:
        conn.execute(
            prospects.update()
            .where(prospects.c.id == prospect_id)
            .values(statut=statut, updated_at=datetime.utcnow())
        )
