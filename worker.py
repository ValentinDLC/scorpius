"""
worker.py
Worker PC — Scorpius v2

Tourne sur le PC du client (en tâche de fond).
Scrape les plateformes → score via LLM → envoie à l'API serveur.

Usage :
    python worker.py              # Lance le worker en boucle
    python worker.py --once       # Un seul cycle puis quitte
    python worker.py --test       # Test connexion API + LLM
    python worker.py --login malt # Sauvegarde session cookie Tier 2
"""

import asyncio
import argparse
import logging
import os
import sys
import time
import socket
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "worker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("worker")


# ══════════════════════════════════════════════════════════════════════════════
# Config worker
# ══════════════════════════════════════════════════════════════════════════════

def load_worker_config() -> dict:
    """Charge worker_config.yaml."""
    path = Path("worker_config.yaml")
    if not path.exists():
        logger.error("worker_config.yaml introuvable")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ══════════════════════════════════════════════════════════════════════════════
# Client API — communication avec le serveur Fly.io
# ══════════════════════════════════════════════════════════════════════════════

class APIClient:
    """
    Envoie les données du worker vers l'API Scorpius.

    Toutes les requêtes sont authentifiées avec X-Worker-Key.
    """

    def __init__(self, api_url: str, api_key: str):
        self.base_url = api_url.rstrip("/")
        self.api_key  = api_key
        self.headers  = {
            "X-Worker-Key":  api_key,
            "Content-Type":  "application/json",
        }
        self.timeout = 30

    # ──────────────────────────────────────────────
    # Ping — vérifie que l'API est accessible
    # ──────────────────────────────────────────────

    async def ping(self) -> bool:
        """
        Signale au serveur que le worker est actif.
        Retourne True si l'API répond.
        """
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/worker/ping",
                    headers=self.headers,
                    json={"hostname": socket.gethostname()},
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    logger.debug("API ping OK")
                    return True
                else:
                    logger.warning(f"API ping {resp.status_code}")
                    return False
        except httpx.ConnectError:
            logger.error(
                f"API inaccessible : {self.base_url}\n"
                "  → Vérifiez que le serveur est démarré"
            )
            return False
        except Exception as e:
            logger.error(f"Ping erreur : {e}")
            return False

    # ──────────────────────────────────────────────
    # Envoi des missions
    # ──────────────────────────────────────────────

    async def send_missions(self, missions: list[dict]) -> dict:
        """
        Envoie une liste de missions à l'API.

        Returns:
            dict : {"inserted": int, "total": int}
        """
        if not missions:
            return {"inserted": 0, "total": 0}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/missions",
                    headers=self.headers,
                    json=missions,
                    timeout=self.timeout,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("data", {})
                    logger.info(
                        f"API ← {result.get('inserted', 0)} nouvelles / "
                        f"{result.get('total', 0)} envoyées"
                    )
                    return result

                elif resp.status_code == 401:
                    logger.error(
                        "Clé worker invalide (401)\n"
                        "  → Vérifiez WORKER_API_KEY dans .env et worker_config.yaml"
                    )
                    return {"inserted": 0, "total": 0}

                else:
                    logger.error(
                        f"API erreur {resp.status_code} : "
                        f"{resp.text[:200]}"
                    )
                    return {"inserted": 0, "total": 0}

        except httpx.TimeoutException:
            logger.error(f"Timeout API après {self.timeout}s")
            return {"inserted": 0, "total": 0}

        except httpx.ConnectError:
            logger.error(f"API inaccessible : {self.base_url}")
            return {"inserted": 0, "total": 0}

    # ──────────────────────────────────────────────
    # Récupère les commandes du serveur
    # ──────────────────────────────────────────────

    async def get_commands(self) -> list[dict]:
        """
        Poll les commandes envoyées depuis le dashboard.
        Ex: {"command": "scrape_now"}
        """
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/worker/commands",
                    headers=self.headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    return resp.json().get("data", [])
                return []
        except Exception:
            return []


# ══════════════════════════════════════════════════════════════════════════════
# Worker principal
# ══════════════════════════════════════════════════════════════════════════════

class ScorpiusWorker:
    """
    Worker qui tourne sur le PC du client.

    Boucle :
    1. Ping le serveur
    2. Vérifie les commandes
    3. Lance le scraping si c'est l'heure (ou commande reçue)
    4. Envoie les missions à l'API
    5. Attend la prochaine échéance
    """

    def __init__(self, config: dict):
        self.config   = config
        self.api      = APIClient(
            api_url = config["api"]["url"],
            api_key = config["api"]["key"],
        )
        self.frequence_min = config["scraping"].get("frequence_minutes", 60)
        self._force_scrape = False    # Flag commande manuelle
        self._running      = True

    # ──────────────────────────────────────────────
    # Lancement
    # ──────────────────────────────────────────────

    async def start(self, once: bool = False):
        """
        Lance le worker.

        Args:
            once : si True, exécute un seul cycle puis quitte
        """
        self._print_banner()

        # Vérifie la connexion API au démarrage
        logger.info("Connexion API...")
        api_ok = await self.api.ping()
        if not api_ok:
            logger.error(
                "⚠️  API inaccessible au démarrage.\n"
                "   Le worker va quand même démarrer et réessayer."
            )

        # Vérifie le LLM
        logger.info("Vérification LLM...")
        llm_ok = self._check_llm()
        if not llm_ok:
            logger.error("⚠️  LLM inaccessible. Vérifiez votre clé Groq.")

        logger.info(
            f"Worker démarré — cycle toutes les {self.frequence_min} min"
        )

        cycle = 0
        while self._running:
            cycle += 1
            logger.info(
                f"━━━ Cycle #{cycle} — "
                f"{datetime.now().strftime('%d/%m %H:%M:%S')} ━━━"
            )

            await self._run_cycle()

            if once:
                logger.info("Mode --once : worker terminé.")
                break

            # Attend en vérifiant les commandes toutes les 30s
            await self._wait_with_commands(self.frequence_min * 60)

    # ──────────────────────────────────────────────
    # Cycle de scraping
    # ──────────────────────────────────────────────

    async def _run_cycle(self):
        """Un cycle complet : scraping → scoring → envoi API."""

        # 1. Ping serveur
        await self.api.ping()

        # 2. Scraping
        logger.info("Lancement scraping...")
        missions = await self._scrape()

        if not missions:
            logger.info("Aucune nouvelle mission à envoyer.")
            return

        # 3. Envoi à l'API
        logger.info(f"Envoi de {len(missions)} missions à l'API...")
        result = await self.api.send_missions(missions)

        inserted = result.get("inserted", 0)
        logger.info(
            f"✓ Cycle terminé — "
            f"{inserted} nouvelle(s) mission(s) ajoutée(s) en base"
        )

    # ──────────────────────────────────────────────
    # Scraping
    # ──────────────────────────────────────────────

    async def _scrape(self) -> list[dict]:
        """
        Lance le scraper Playwright.
        Retourne les missions extraites et scorées.
        """
        try:
            from scrapers.scraper import ScorpiusScraper
            scraper  = ScorpiusScraper()
            missions = await scraper.run()
            return missions
        except Exception as e:
            logger.error(f"Erreur scraping : {e}")
            return []

    # ──────────────────────────────────────────────
    # Attente intelligente avec polling commandes
    # ──────────────────────────────────────────────

    async def _wait_with_commands(self, total_secondes: int):
        """
        Attend la prochaine échéance en vérifiant les commandes
        toutes les 30 secondes.

        Si commande "scrape_now" reçue → lance immédiatement.
        """
        elapsed   = 0
        poll_interval = 30   # Vérifie commandes toutes les 30s

        logger.info(
            f"Prochain scraping dans {total_secondes // 60} min "
            f"(ou sur commande dashboard)"
        )

        while elapsed < total_secondes and self._running:
            await asyncio.sleep(min(poll_interval, total_secondes - elapsed))
            elapsed += poll_interval

            # Vérifie les commandes
            commands = await self.api.get_commands()
            for cmd in commands:
                if cmd.get("command") == "scrape_now":
                    logger.info(
                        "⚡ Commande 'scrape_now' reçue depuis le dashboard"
                    )
                    return   # Sort de l'attente → lance un cycle immédiat

            # Affiche le temps restant toutes les 5 minutes
            restant = total_secondes - elapsed
            if restant > 0 and elapsed % 300 == 0:
                logger.info(f"Prochain scraping dans {restant // 60} min...")

    # ──────────────────────────────────────────────
    # Login Tier 2
    # ──────────────────────────────────────────────

    async def login_plateforme(self, url: str):
        """
        Lance le login interactif pour une plateforme Tier 2.
        Sauvegarde les cookies pour les prochains scrapes.
        """
        from scrapers.scraper import ScorpiusScraper
        scraper = ScorpiusScraper()
        await scraper.save_session(url)

    # ──────────────────────────────────────────────
    # Vérification LLM
    # ──────────────────────────────────────────────

    def _check_llm(self) -> bool:
        """Vérifie que le LLM est accessible."""
        try:
            from brain.extractor import LLMClient
            client = LLMClient()
            return client.ping()
        except Exception as e:
            logger.error(f"LLM check : {e}")
            return False

    # ──────────────────────────────────────────────
    # Banner démarrage
    # ──────────────────────────────────────────────

    def _print_banner(self):
        api_url = self.config["api"]["url"]
        print(f"""
╔══════════════════════════════════════════════╗
║         Scorpius v2 — Worker PC              ║
╠══════════════════════════════════════════════╣
║  API     : {api_url:<34} ║
║  Cycle   : {self.frequence_min} min{'':<29} ║
║  Machine : {socket.gethostname():<34} ║
╚══════════════════════════════════════════════╝
        """)


# ══════════════════════════════════════════════════════════════════════════════
# Tests de connexion
# ══════════════════════════════════════════════════════════════════════════════

async def run_tests(config: dict):
    """
    Mode --test : vérifie toutes les connexions.
    Affiche un rapport détaillé.
    """
    print("\n" + "━" * 50)
    print("  Scorpius Worker — Tests de connexion")
    print("━" * 50)

    results = {}

    # ── Test 1 : API ──
    print("\n[1/4] API Scorpius...")
    api = APIClient(config["api"]["url"], config["api"]["key"])
    ok  = await api.ping()
    results["api"] = ok
    print(f"  {'✅' if ok else '❌'} API : {config['api']['url']}")
    if not ok:
        print("  → Vérifiez que le serveur est démarré")
        print(f"  → En dev : python dashboard/app.py")

    # ── Test 2 : LLM ──
    print("\n[2/4] LLM (Groq/Ollama)...")
    try:
        from brain.extractor import LLMClient
        client = LLMClient()
        ok     = client.ping()
        results["llm"] = ok
        print(f"  {'✅' if ok else '❌'} {client.provider} / {client.model}")
        if not ok:
            print("  → Vérifiez llm.api_key dans config/profil.yaml")
    except Exception as e:
        results["llm"] = False
        print(f"  ❌ Erreur LLM : {e}")

    # ── Test 3 : Playwright ──
    print("\n[3/4] Playwright (Chromium)...")
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page    = await browser.new_page()
            await page.goto("https://example.com", timeout=10000)
            title   = await page.title()
            await browser.close()
        results["playwright"] = True
        print(f"  ✅ Chromium OK — page chargée : '{title}'")
    except Exception as e:
        results["playwright"] = False
        print(f"  ❌ Playwright : {e}")
        print("  → Lancez : playwright install chromium")

    # ── Test 4 : Config profil ──
    print("\n[4/4] Config profil.yaml...")
    try:
        from config.loader import get_config
        cfg = get_config()
        plateformes = cfg.plateformes_actives
        results["config"] = True
        print(f"  ✅ Profil : {cfg.profil.get('metier')}")
        print(f"  ✅ {len(plateformes)} plateforme(s) active(s) :")
        for p in plateformes:
            print(f"     • {p['url']}")
    except Exception as e:
        results["config"] = False
        print(f"  ❌ Config : {e}")

    # ── Résumé ──
    print("\n" + "━" * 50)
    all_ok = all(results.values())
    if all_ok:
        print("  ✅ Tout est OK — Worker prêt à démarrer")
        print("  → Lance : python worker.py")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"  ⚠️  Problèmes détectés : {', '.join(failed)}")
        print("  → Corrigez les erreurs ci-dessus avant de démarrer")
    print("━" * 50 + "\n")

    return all_ok


# ══════════════════════════════════════════════════════════════════════════════
# Scraping unique avec rapport détaillé
# ══════════════════════════════════════════════════════════════════════════════

async def run_once_with_report(config: dict):
    """Mode --once : un cycle complet avec rapport terminal."""
    print("\n" + "━" * 50)
    print("  Scorpius Worker — Cycle unique")
    print("━" * 50)

    worker = ScorpiusWorker(config)
    await worker.start(once=True)

    print("━" * 50 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Scorpius Worker — Agent de scraping PC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python worker.py              Lance le worker en boucle
  python worker.py --once       Un seul cycle puis quitte
  python worker.py --test       Teste toutes les connexions
  python worker.py --login https://www.malt.fr
                                Login interactif Malt (Tier 2)
        """,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Exécute un seul cycle de scraping puis quitte",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Teste les connexions API, LLM, Playwright",
    )
    parser.add_argument(
        "--login",
        metavar="URL",
        help="Login interactif pour une plateforme Tier 2",
    )
    parser.add_argument(
        "--config",
        default="worker_config.yaml",
        help="Chemin vers worker_config.yaml (défaut: worker_config.yaml)",
    )

    return parser.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    args   = parse_args()
    config = load_worker_config()

    # ── Mode test ──
    if args.test:
        ok = await run_tests(config)
        sys.exit(0 if ok else 1)

    # ── Mode login Tier 2 ──
    if args.login:
        worker = ScorpiusWorker(config)
        await worker.login_plateforme(args.login)
        sys.exit(0)

    # ── Mode once ──
    if args.once:
        await run_once_with_report(config)
        sys.exit(0)

    # ── Mode normal — boucle infinie ──
    worker = ScorpiusWorker(config)
    try:
        await worker.start()
    except KeyboardInterrupt:
        print("\n\n[Worker] Arrêté par l'utilisateur. À bientôt ! 🦂")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())