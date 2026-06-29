#!/bin/bash
cd /Users/valentindardenne/scorpius
source .venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python3 scrapers/scraper.py
