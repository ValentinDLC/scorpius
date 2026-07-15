#!/usr/bin/env python3
"""
run.py - Scorpius launcher
"""
import sys
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
import os as os_sys
sys.path.insert(0, os_sys.path.join(os_sys.path.dirname(__file__), '..', 'data'))

import sys
import os as os_sys
sys.path.insert(0, os_sys.path.join(os_sys.path.dirname(__file__), '..', 'data'))

import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Ajouter le dossier racine au PYTHONPATH
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from dashboard.app import app
    from dashboard.app import login_required, ok, err
    from dashboard.crm_routes import register_crm_routes
    register_crm_routes(app, login_required, ok, err)

    from storage.db import init_db
    from storage.prospects import init_prospects_db
    from config.loader import get_config
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    # Init DB
    init_db()
    init_prospects_db()

    # Config
    try:
        cfg = get_config()
        port = int(os.getenv("PORT", cfg.dashboard.get("port", 5000)))
        print(f"\n🦂 Scorpius Dashboard")
        print(f"   Métier: {cfg.profil.get('metier')}")
        print(f"   URL: http://localhost:{port}\n")
    except Exception as e:
        print(f"⚠️  Config error: {e}")
        port = 5000

    # Run
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
