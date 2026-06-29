#!/bin/bash
# start.sh - Lanceur Scorpius

cd "$(dirname "$0")"

# Active venv
source .venv/bin/activate

# Export PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Lance le dashboard
echo "🦂 Démarrage de Scorpius..."
python3 dashboard/app.py
