#!/usr/bin/env bash
set -e
echo "=== SCORPIUS v2 - Démonstration Sprint 1 ==="

echo "🔄 Démarrage du serveur..."
lsof -ti:8080 | xargs kill -9 2>/dev/null || true
python3 run.py > /tmp/scorpius.log 2>&1 &
sleep 3

if ! curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/login | grep -qE "200|302"; then
    echo "❌ Serveur non démarré. Voir /tmp/scorpius.log"; exit 1
fi
echo "✅ Serveur opérationnel"

curl -s -c /tmp/cookie.txt -X POST http://127.0.0.1:8080/login -d "password=scorpius" -L -o /dev/null
echo "✅ Authentifié"

echo -e "\n⏱️ Test 1: Recherche 10 prospects (lecture DB)"
time curl -s -b /tmp/cookie.txt "http://127.0.0.1:8080/api/prospects?limit=10" | python3 -c '
import sys, json
raw = sys.stdin.read()
if not raw.strip(): print("❌ Réponse vide"); sys.exit(1)
d = json.loads(raw).get("data", [])
print("✅", len(d), "prospects retournés")
'

echo -e "\n📊 Test 2: Distribution des scores"
curl -s -b /tmp/cookie.txt "http://127.0.0.1:8080/api/prospects?limit=10" | python3 -c '
import sys, json, statistics
raw = sys.stdin.read()
if not raw.strip(): print("❌ Réponse vide"); sys.exit(1)
d = json.loads(raw).get("data", [])
scores = [p["score_audit"] for p in d]
print("✅ Scores:", scores)
print("✅ Min:", min(scores), "Max:", max(scores), "Médiane:", statistics.median(scores))
'

echo -e "\n⚡ Test 3: Détail audit (cached)"
time curl -s -b /tmp/cookie.txt "http://127.0.0.1:8080/api/prospects?limit=1" | python3 -c '
import sys, json
raw = sys.stdin.read()
if not raw.strip(): print("❌ Réponse vide"); sys.exit(1)
d = json.loads(raw).get("data", [])
if d:
    p = d[0]
    print("✅", p.get("nom","?"), "→ score:", p.get("score_audit"), "| perf:", p.get("audit_performance"), "| seo:", p.get("audit_seo"))
else:
    print("⚠️ Aucun prospect")
'

echo -e "\n✅ Démo Sprint 1 terminée."
