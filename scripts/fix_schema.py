import re
from pathlib import Path

# 1. Nettoyage de db.py (Suppression du DROP TABLE destructeur)
db_file = Path("data/storage/db.py")
if db_file.exists():
    content = db_file.read_text(encoding="utf-8")
    
    # Remplacement du DROP TABLE + CREATE par un simple CREATE IF NOT EXISTS
    bad_pattern = r"DROP TABLE IF EXISTS calls CASCADE;\s*CREATE TABLE calls"
    safe_pattern = r"CREATE TABLE IF NOT EXISTS calls"
    
    if re.search(bad_pattern, content):
        content = re.sub(bad_pattern, safe_pattern, content)
        db_file.write_text(content, encoding="utf-8")
        print("✅ Le DROP TABLE destructeur a été retiré de db.py !")
    else:
        print("ℹ️ Le DROP TABLE n'a pas été trouvé (peut-être déjà corrigé).")
else:
    print("⚠️ Fichier data/storage/db.py introuvable.")

# 2. Mise à jour de la documentation schema.sql
schema_file = Path("docs/schema.sql")
schema_content = """-- Schéma de base de données officiel OBO
-- Compatible SQLite / PostgreSQL
-- Ne contient que les tables actives du périmètre.

CREATE TABLE utilisateurs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT, -- SERIAL sous PostgreSQL
    nom           TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    verification_code TEXT,
    verification_expires_at TIMESTAMP,
    reset_token TEXT,
    reset_token_expires_at TIMESTAMP,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- SERIAL sous PostgreSQL
    user_id INTEGER NOT NULL,
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
    statut VARCHAR(50) DEFAULT 'nouveau',
    raw_google_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE (place_id, user_id),
    FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
);

CREATE TABLE calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- SERIAL sous PostgreSQL
    prospect_id INTEGER NOT NULL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duree INTEGER,
    audio_path TEXT,
    transcript TEXT,
    probleme_detecte TEXT,
    solution_proposee TEXT,
    interet_percu VARCHAR(80),
    status TEXT DEFAULT 'recording',
    privacy_mode INTEGER DEFAULT 0,
    audio_saved INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id) ON DELETE CASCADE
);

CREATE INDEX idx_prospects_user_status ON prospects(user_id, statut);
CREATE INDEX idx_calls_prospect ON calls(prospect_id);
"""

# Création du dossier docs si non existant
schema_file.parent.mkdir(parents=True, exist_ok=True)
schema_file.write_text(schema_content, encoding="utf-8")
print("✅ Documentation du schéma (docs/schema.sql) mise à jour !")

