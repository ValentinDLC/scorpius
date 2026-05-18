from urllib.parse import urljoin
import re

from bs4 import BeautifulSoup

BASE_URL = "https://www.codeur.com"


def _clean_text(value):
    value = value or ""
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parse_budget(text):
    text = _clean_text(text)
    numbers = []

    for raw in re.findall(r'(\d[\d\s]*)\s*€', text):
        try:
            numbers.append(int(re.sub(r"\s+", "", raw)))
        except Exception:
            pass

    devise = "€" if "€" in text else None

    if not numbers:
        return None, None, devise

    low = text.lower()

    if "moins de" in low:
        return None, numbers[0], devise

    if "plus de" in low or "à partir de" in low or "a partir de" in low:
        return numbers[0], None, devise

    if len(numbers) >= 2:
        return numbers[0], numbers[1], devise

    return numbers[0], numbers[0], devise


def extract_codeur_projects_from_html(html: str):
    soup = BeautifulSoup(html or "", "html.parser")
    missions = []
    seen = set()

    cards = soup.select('div[id^="project-"][data-controller="project-preview"]')

    for card in cards:
        project_id = (card.get("id") or "").replace("project-", "").strip()

        title_a = None
        for a in card.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            text = _clean_text(a.get_text(" ", strip=True))

            if not href.startswith("/projects/"):
                continue
            if "/like" in href or "project_preview" in href:
                continue
            if not text:
                continue

            title_a = a
            break

        if not title_a:
            continue

        titre = _clean_text(title_a.get_text(" ", strip=True))
        url = urljoin(BASE_URL, title_a["href"])

        if not titre or not url or url in seen:
            continue
        seen.add(url)

        summary_node = card.find(attrs={"data-project-preview-target": "summary"})
        description = _clean_text(summary_node.get_text(" ", strip=True) if summary_node else "")

        budget_node = None
        for tag in card.find_all(["span", "div", "p", "strong"]):
            title_attr = str(tag.get("title", "") or "")
            bs_title = str(tag.get("data-bs-original-title", "") or "")
            if "Budget indicatif" in title_attr or "Budget indicatif" in bs_title:
                budget_node = tag
                break

        budget_text = _clean_text(budget_node.get_text(" ", strip=True) if budget_node else "")

        if not budget_text:
            euro_string = card.find(string=re.compile(r"€"))
            if euro_string:
                budget_text = _clean_text(str(euro_string))

        budget_min, budget_max, devise = _parse_budget(budget_text)

        competences = []
        for a in card.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            text = _clean_text(a.get_text(" ", strip=True))
            if "/projects/c/" in href and text and text not in competences:
                competences.append(text)

        mission = {
            "source_id": project_id or None,
            "titre": titre,
            "url": url,
            "description": description,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "devise": devise,
            "plateforme": "codeur",
        }

        if competences:
            mission["competences"] = competences

        missions.append(mission)

    return missions
