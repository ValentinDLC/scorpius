"""
scrapers/scraper.py
Scraper Playwright générique — Scorpius v2
"""

import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from config.loader import get_config
from brain.extractor import process_page
from storage.db import upsert_mission, init_db

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOTS_DIR = Path(__file__).parent.parent / "data" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin' },
            { name: 'Chrome PDF Viewer' },
            { name: 'Native Client' },
        ],
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['fr-FR', 'fr', 'en-US', 'en'],
    });
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
    };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
}
"""


# ══════════════════════════════════════════════════════════════════════════════

class ScorpiusScraper:

    def __init__(self):
        self.cfg = get_config()
        self._browser: Optional[Browser] = None
        self._nouvelles_missions: list[dict] = []

    async def run(self) -> list[dict]:
        plateformes = self.cfg.plateformes_actives

        if not plateformes:
            logger.warning("Aucune plateforme active dans profil.yaml")
            return []

        logger.info(f"━━━ Scraping démarré — {len(plateformes)} plateforme(s) ━━━")
        self._nouvelles_missions = []

        async with async_playwright() as pw:
            self._browser = await self._launch_browser(pw)

            for i, plateforme in enumerate(plateformes, 1):
                url = plateforme["url"]
                nom = _extract_nom(url)
                logger.info(f"[{i}/{len(plateformes)}] {nom} — {url}")

                try:
                    await self._scrape_plateforme(plateforme)
                except Exception as e:
                    logger.error(f"  ✗ Erreur {nom} : {e}")

                if i < len(plateformes):
                    delai = random.uniform(
                        self.cfg.scraping.get("delai_min_secondes", 3),
                        self.cfg.scraping.get("delai_max_secondes", 8),
                    )
                    logger.info(f"  ⏱ Pause {delai:.1f}s...")
                    await asyncio.sleep(delai)

            await self._browser.close()

        total = len(self._nouvelles_missions)
        logger.info(f"━━━ Scraping terminé — {total} nouvelle(s) mission(s) ━━━")
        return self._nouvelles_missions

    async def _scrape_plateforme(self, plateforme: dict):
        url  = plateforme["url"]
        tier = plateforme.get("tier", 1)
        nom  = _extract_nom(url)

        context = await self._create_context(nom, tier)
        page    = await context.new_page()

        try:
            await page.add_init_script(script=STEALTH_JS)
            html = await self._load_page(page, url, nom)
            if not html:
                return

            missions = process_page(html=html, plateforme_url=url, plateforme_nom=nom)

            nouvelles = 0
            for m in missions:
                # Formate le budget en string pour save_mission
                budget_str = _format_budget(m)
                competences_str = ", ".join(m.get("competences") or [])

                mission_dict = {
                    "plateforme": nom,
                    "titre": m.get("titre", "Sans titre"),
                    "url": m.get("url", url),
                    "budget_min": m.get("budget_min"),
                    "budget_max": m.get("budget_max"),
                    "devise": m.get("devise", "EUR"),
                    "description": m.get("description") or "",
                    "competences": competences_str,
                    "score": m.get("score", 0),
                }
                mission_id = upsert_mission(mission_dict)
                if mission_id:
                    nouvelles += 1
                    self._nouvelles_missions.append(m)

            logger.info(
                f"  ✓ {len(missions)} mission(s) scorées "
                f"— {nouvelles} nouvelle(s) en DB"
            )

        finally:
            await page.close()
            await context.close()

    async def _load_page(self, page: Page, url: str, nom: str, timeout_ms: int = 30000) -> Optional[str]:
        try:
            logger.info(f"  → Chargement {url}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await asyncio.sleep(random.uniform(2.0, 4.0))
            await self._scroll_naturel(page)
            html = await page.content()
            logger.info(f"  → HTML récupéré : {len(html):,} chars")

            screenshot_path = SCREENSHOTS_DIR / f"{nom}_last.png"
            await page.screenshot(path=str(screenshot_path))

            return html

        except PlaywrightTimeoutError:
            logger.error(f"  ✗ Timeout sur {url}")
            await self._screenshot_erreur(page, nom, "timeout")
            return None
        except Exception as e:
            logger.error(f"  ✗ Erreur chargement {url} : {e}")
            await self._screenshot_erreur(page, nom, "error")
            return None

    async def _scroll_naturel(self, page: Page):
        try:
            hauteur = await page.evaluate("document.body.scrollHeight")
            position = 0
            while position < hauteur:
                position = min(position + random.randint(300, 600), hauteur)
                await page.evaluate(f"window.scrollTo(0, {position})")
                await asyncio.sleep(random.uniform(0.3, 0.8))
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception as e:
            logger.debug(f"Erreur scroll (ignorée) : {e}")

    async def _create_context(self, nom_plateforme: str, tier: int) -> BrowserContext:
        ua = random.choice(USER_AGENTS)
        params = {
            "user_agent": ua,
            "viewport": {
                "width":  random.choice([1280, 1366, 1440, 1920]),
                "height": random.choice([720, 768, 800, 900]),
            },
            "locale": "fr-FR",
            "timezone_id": "Europe/Paris",
            "extra_http_headers": {
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "DNT": "1",
            },
        }

        if tier == 2:
            session_file = SESSIONS_DIR / f"{nom_plateforme}_session.json"
            if session_file.exists():
                logger.info(f"  → Session cookie chargée : {session_file.name}")
                params["storage_state"] = str(session_file)
            else:
                logger.warning(f"  ⚠ Tier 2 sans session pour '{nom_plateforme}'.")

        return await self._browser.new_context(**params)

    async def _launch_browser(self, pw) -> Browser:
        return await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1366,768",
            ],
        )

    async def _screenshot_erreur(self, page: Page, nom: str, raison: str):
        try:
            path = SCREENSHOTS_DIR / f"{nom}_{raison}.png"
            await page.screenshot(path=str(path))
        except Exception:
            pass

    async def save_session(self, plateforme_url: str):
        nom = _extract_nom(plateforme_url)
        session_file = SESSIONS_DIR / f"{nom}_session.json"

        print(f"\n{'━'*50}")
        print(f"  Scorpius — Connexion {nom}")
        print(f"  Connectez-vous sur {plateforme_url} puis appuyez ENTRÉE")
        print(f"{'━'*50}\n")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            context = await browser.new_context()
            page    = await context.new_page()
            await page.goto(plateforme_url)
            input("  → Appuyez sur ENTRÉE après connexion...")
            await context.storage_state(path=str(session_file))
            print(f"\n  ✅ Session sauvegardée : {session_file}\n")
            await browser.close()


# ══════════════════════════════════════════════════════════════════════════════
# Scheduler
# ══════════════════════════════════════════════════════════════════════════════

async def run_scheduler():
    cfg = get_config()
    frequence_min = cfg.scraping.get("frequence_minutes", 60)
    logger.info(f"Scheduler démarré — cycle toutes les {frequence_min} min")

    cycle = 0
    while True:
        cycle += 1
        logger.info(f"━━━ Cycle #{cycle} — {datetime.now().strftime('%H:%M:%S')} ━━━")
        try:
            scraper = ScorpiusScraper()
            nouvelles = await scraper.run()
            if nouvelles:
                from notifications.telegram import notify_nouvelles_missions
                await notify_nouvelles_missions(nouvelles)
        except Exception as e:
            logger.error(f"Erreur cycle #{cycle} : {e}")

        logger.info(f"Prochain cycle dans {frequence_min} min...")
        await asyncio.sleep(frequence_min * 60)


# ══════════════════════════════════════════════════════════════════════════════
# Utilitaires
# ══════════════════════════════════════════════════════════════════════════════

def _extract_nom(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or url
    parts = host.replace("www.", "").split(".")
    return parts[0] if parts else host


def _format_budget(mission: dict) -> str:
    bmin = mission.get("budget_min")
    bmax = mission.get("budget_max")
    devise = mission.get("devise", "EUR")
    if bmin and bmax:
        return f"{bmin}–{bmax} {devise}"
    elif bmin:
        return f"À partir de {bmin} {devise}"
    elif bmax:
        return f"Jusqu'à {bmax} {devise}"
    return ""


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    init_db()

    async def main():
        from notifications.telegram import notify_nouvelles_missions
        
        scraper = ScorpiusScraper()
        missions = await scraper.run()
        
        print(f"\n{'━'*50}")
        print(f"  {len(missions)} nouvelle(s) mission(s) traitée(s)")
        for m in missions:
            # Sécurité float -> int
            score = int(m.get('score', 0))
            print(f"  [{score:3d}/100] {m.get('titre', '')[:55]}")
        print(f"{'━'*50}")

        # ─── NOTIFICATION TELEGRAM AUTOMATIQUE ───
        bonnes_missions = [m for m in missions if int(m.get("score", 0)) >= 50]
        if bonnes_missions:
            print(f"  [Telegram] Envoi auto de {len(bonnes_missions)} mission(s) pertinente(s)...")
            await notify_nouvelles_missions(bonnes_missions)
        else:
            print("  [Telegram] Aucune mission > 50/100 à notifier pour ce cycle.")

    asyncio.run(main())
