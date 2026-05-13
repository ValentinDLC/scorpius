#!/usr/bin/env python3
"""
run.py - Scorpius launcher
"""
import sys
from pathlib import Path

# Ajouter le dossier racine au PYTHONPATH
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from dashboard.app import app
    from storage.db import init_db
    from config.loader import get_config
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    # Init DB
    init_db()

    # Config
    try:
        cfg = get_config()
        port = cfg.dashboard.get("port", 5000)
        print(f"\n🦂 Scorpius Dashboard")
        print(f"   Métier: {cfg.profil.get('metier')}")
        print(f"   URL: http://localhost:{port}\n")
    except Exception as e:
        print(f"⚠️  Config error: {e}")
        port = 5000

    # Run
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)