import re
from pathlib import Path

# --- 1. Remplacement des Emojis courants ---
EMOJI_MAP = {
    r"📊": "<!-- icon:bar-chart -->",
    r"📞": "<!-- icon:phone -->",
    r"✅": "✔",
    r"❌": "✘",
    r"⚠️": "!",
    r"⚙️": "<!-- icon:settings -->",
    r"🔎": "<!-- icon:search -->",
    r"📝": "<!-- icon:file-text -->",
    r"🗑️": "<!-- icon:trash -->",
    r"💼": "<!-- icon:briefcase -->",
    r"🤖": "<!-- icon:bot -->",
    r"💡": "<!-- icon:lightbulb -->",
    r"🚀": "<!-- icon:rocket -->",
    r"🎯": "<!-- icon:target -->",
    r"🔥": "<!-- icon:flame -->",
    r"💰": "<!-- icon:dollar-sign -->",
    r"👑": "<!-- icon:crown -->"
}

def remove_emojis(text: str) -> str:
    # Remplacement des emojis connus
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    
    # Nettoyage brutal des autres emojis Unicode restants (plages typiques)
    # On laisse tranquille les caractères standards.
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)
    text = emoji_pattern.sub('', text)
    return text


# --- 2. Renommage de Scorpius en OBO ---
def rename_brand(text: str) -> str:
    # On évite de renommer les chemins de fichiers ou le code, on cible le texte visible.
    # On remplace les occurrences simples avec casse respectée.
    text = re.sub(r'\bScorpius\b', 'OBO', text)
    text = re.sub(r'\bSCORPIUS\b', 'OBO', text)
    text = re.sub(r'\bscorpius\b(?!(\.py|\.test|_api|/))', 'obo', text)
    return text


print("Démarrage de la transition de marque OBO...")

# Parcours des templates HTML
templates_dir = Path("web/templates")
html_files_modified = 0

if templates_dir.exists():
    for filepath in templates_dir.rglob("*.html"):
        content = filepath.read_text(encoding="utf-8")
        
        new_content = remove_emojis(content)
        new_content = rename_brand(new_content)
        
        if new_content != content:
            filepath.write_text(new_content, encoding="utf-8")
            html_files_modified += 1
            print(f"  - Modifié : {filepath}")

# Parcours du fichier README
readme_path = Path("README.md")
if readme_path.exists():
    content = readme_path.read_text(encoding="utf-8")
    new_content = rename_brand(content)
    if new_content != content:
        readme_path.write_text(new_content, encoding="utf-8")
        print("  - Modifié : README.md")

print(f"✅ Transition terminée : {html_files_modified} templates mis à jour et purgés de leurs emojis.")
