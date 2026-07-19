import os
import sys
from pathlib import Path

# On indique le chemin pour SQLAlchemy
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data')))
from storage.db import get_conn
from sqlalchemy import text

print("1. Migration des données en base...")
migration_queries = [
    "UPDATE prospects SET statut = 'nouveau' WHERE statut IN ('Nouveau', 'nouveau', 'a_appeler', 'NOUVEAU');",
    "UPDATE prospects SET statut = 'a_demarcher' WHERE statut IN ('À démarcher', 'A démarcher', 'a_demarcher', 'A_APPELER');",
    "UPDATE prospects SET statut = 'en_cours' WHERE statut IN ('En cours', 'en_cours', 'mission');",
    "UPDATE prospects SET statut = 'gagne' WHERE statut IN ('Gagné', 'gagne', 'gagné');",
    "UPDATE prospects SET statut = 'perdu' WHERE statut IN ('Perdu', 'perdu');"
]

try:
    with get_conn() as conn:
        for q in migration_queries:
            conn.execute(text(q))
    print("✅ Base de données migrée avec succès.")
except Exception as e:
    print(f"⚠️ Erreur lors de la migration SQL : {e}")

print("2. Mise à jour de la valeur par défaut dans prospects.py...")
prospects_file = Path("data/storage/prospects.py")
content = prospects_file.read_text(encoding="utf-8")
content = content.replace("DEFAULT 'a_appeler'", "DEFAULT 'nouveau'")
prospects_file.write_text(content, encoding="utf-8")
print("✅ prospects.py mis à jour.")

print("3. Mise à jour du template HTML du CRM...")
html_file = Path("web/templates/crm/crm_dashboard.html")
if html_file.exists():
    html = html_file.read_text(encoding="utf-8")
    # On remplace les appels à "status" brut par la clé technique "key"
    html = html.replace("{% if prospect.statut == status %}", "{% if prospect.statut == key %}")
    html = html.replace('<option value="{{ status }}"', '<option value="{{ key }}"')
    html = html.replace("{{ status }}</option>", "{{ label }}</option>")
    html = html.replace("for status in statuses", "for key, label in statuses.items()")
    html = html.replace("status-{{ prospect.statut|lower|replace(' ', '_') }}", "status-{{ prospect.statut }}")
    html_file.write_text(html, encoding="utf-8")
    print("✅ crm_dashboard.html mis à jour.")
else:
    print("⚠️ Fichier HTML non trouvé.")

