import re
from pathlib import Path

file_path = Path("services/audit_service.py")
content = file_path.read_text(encoding="utf-8")

# Expression régulière pour remplacer l'ancienne fonction de scoring
pattern = re.compile(r"def compute_audit_score\(.*?\).*?return [^\n]+", re.DOTALL)

new_func = """def compute_audit_score(*, has_site: bool, audit_mobile: bool, audit_performance: int, audit_seo: int, audit_gmb: bool) -> int:
    score = 0
    score += 20 if has_site else 0
    score += 20 if audit_mobile else 0
    score += min(max(audit_performance, 0), 100) * 0.35
    score += min(max(audit_seo, 0), 100) * 0.25
    
    # On garantit que le score restera toujours entre 0 et 100
    return int(round(min(max(score, 0), 100)))"""

if pattern.search(content):
    content = pattern.sub(new_func, content)
    file_path.write_text(content, encoding="utf-8")
    print("✅ Formule de score mise à jour dans services/audit_service.py !")
else:
    print("⚠️ Impossible de trouver la fonction, vérifie manuellement.")
