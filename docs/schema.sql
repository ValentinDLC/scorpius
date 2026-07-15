CREATE TABLE utilisateurs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom           TEXT NOT NULL,
                    email         TEXT UNIQUE,
                    password_hash TEXT,
                    voice_auth    INTEGER DEFAULT 0,
                    date_creation TEXT DEFAULT (datetime('now'))
                );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE missions (
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
                );
CREATE TABLE voice_profiles (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER,
                    embedding     TEXT NOT NULL,
                    date_creation TEXT DEFAULT (datetime('now')),
                    date_maj      TEXT
                );
CREATE TABLE prospects (
	id INTEGER NOT NULL, 
	place_id VARCHAR(255) NOT NULL, 
	nom VARCHAR(255) NOT NULL, 
	secteur VARCHAR(255), 
	telephone VARCHAR(80), 
	adresse TEXT, 
	ville VARCHAR(120), 
	url_site TEXT, 
	google_maps_url TEXT, 
	score_audit INTEGER, 
	audit_mobile BOOLEAN, 
	audit_performance INTEGER, 
	audit_seo INTEGER, 
	audit_gmb BOOLEAN, 
	seo_title BOOLEAN, 
	seo_meta_description BOOLEAN, 
	seo_h1 BOOLEAN, 
	statut VARCHAR(50), 
	raw_google_json TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (place_id)
);
CREATE TABLE calls (
	id INTEGER NOT NULL, 
	prospect_id INTEGER NOT NULL, 
	date DATETIME, 
	duree INTEGER, 
	audio_path TEXT, 
	transcript TEXT, 
	probleme_detecte TEXT, 
	solution_proposee TEXT, 
	interet_percu VARCHAR(80), 
	email_suivi_draft TEXT, 
	created_at DATETIME, status TEXT DEFAULT 'recording', duration_sec REAL, updated_at DATETIME, privacy_mode INTEGER DEFAULT 0, audio_saved INTEGER DEFAULT 1, 
	PRIMARY KEY (id)
);
CREATE INDEX idx_calls_prospect ON calls(prospect_id);
CREATE INDEX idx_calls_status ON calls(status);
CREATE INDEX idx_calls_created ON calls(created_at DESC);
