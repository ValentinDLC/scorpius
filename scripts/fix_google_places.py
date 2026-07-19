from pathlib import Path
import re

print("1. Mise à jour de google_places.py...")
file_path = Path("services/google_places.py")
content = file_path.read_text(encoding="utf-8")

# On renomme proprement filtre_sans_site en priorite_sans_site et on documente rayon_km
content = content.replace("filtre_sans_site", "priorite_sans_site")
content = content.replace("def search_prospects(secteur: str, ville: str, rayon_km: int = 10", "def search_prospects(secteur: str, ville: str, rayon_km: int = 0, # Non implémenté par API\n")
file_path.write_text(content, encoding="utf-8")
print("✅ services/google_places.py corrigé.")


print("2. Mise à jour de l'interface HTML (retrait du faux rayon et correction mobile)...")
html_path = Path("web/templates/prospects.html")
if html_path.exists():
    html_content = html_path.read_text(encoding="utf-8")
    
    # Remplacement du label du rayon
    html_content = re.sub(
        r'<label class="label">Rayon \(km\)</label>.*?<input[^>]+id="search-rayon"[^>]*>',
        '<label class="label">Périmètre</label>\n<input type="text" id="search-rayon" class="input" style="width:100%" value="Agglomération" disabled>',
        html_content, flags=re.DOTALL
    )
    
    # Remplacement du label trompeur "Mobile Friendly" ou "Responsive" par un indicateur technique
    html_content = html_content.replace("Mobile-friendly", "Signal Mobile")
    html_content = html_content.replace("Mobile Friendly", "Signal Mobile")
    html_content = html_content.replace("Responsive", "Signal Mobile")
    
    html_path.write_text(html_content, encoding="utf-8")
    print("✅ web/templates/prospects.html corrigé.")
else:
    print("⚠️ web/templates/prospects.html introuvable.")


print("3. Mise à jour des routes...")
routes_path = Path("dashboard/prospects_routes.py")
if routes_path.exists():
    routes_content = routes_path.read_text(encoding="utf-8")
    routes_content = routes_content.replace("filtre_sans_site", "priorite_sans_site")
    routes_path.write_text(routes_content, encoding="utf-8")
    print("✅ dashboard/prospects_routes.py corrigé.")
else:
    print("⚠️ dashboard/prospects_routes.py introuvable.")

