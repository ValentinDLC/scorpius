"""
notifications/telegram.py
Bot Telegram centralisé — Scorpius v2
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from dotenv import load_dotenv

from config.loader import get_config

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("SCORPIUS_BOT_TOKEN", "")
API_BASE  = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def _post(endpoint: str, payload: dict) -> Optional[dict]:
    if not BOT_TOKEN:
        logger.error("SCORPIUS_BOT_TOKEN manquant dans .env")
        return None
    url = f"{API_BASE}/{endpoint}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Telegram API erreur : {data.get('description')}")
                return None
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Telegram HTTP {e.response.status_code} : {e.response.text[:200]}")
        return None
    except httpx.TimeoutException:
        logger.error("Telegram : timeout dépassé")
        return None
    except httpx.ConnectError:
        logger.error("Telegram : impossible de joindre l'API")
        return None


async def send_message(chat_id: str, text: str, parse_mode: str = "HTML", disable_preview: bool = True) -> bool:
    if len(text) > 4096:
        text = text[:4090] + "\n<i>...</i>"
    payload = {
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    result = await _post("sendMessage", payload)
    if result:
        logger.debug(f"Message envoyé → chat_id {chat_id}")
        return True
    return False


def _emoji_score(score: int) -> str:
    if score >= 80: return "🟢"
    elif score >= 60: return "🟡"
    elif score >= 40: return "🟠"
    return "🔴"


def _format_budget(mission: dict) -> str:
    bmin   = mission.get("budget_min")
    bmax   = mission.get("budget_max")
    devise = mission.get("devise", "€")
    if bmin and bmax and bmin != bmax:
        return f"{int(bmin)}–{int(bmax)} {devise}"
    elif bmin:
        return f"{int(bmin)}+ {devise}"
    elif bmax:
        return f"≤{int(bmax)} {devise}"
    return "Budget non précisé"


def format_nouvelles_missions(missions: list[dict]) -> str:
    n = len(missions)
    s = "s" if n > 1 else ""
    lignes = [
        f"🦂 <b>Scorpius — {n} nouvelle{s} mission{s}</b>",
        f"<i>{datetime.now().strftime('%d/%m/%Y %H:%M')}</i>",
        "",
    ]
    top = sorted(missions, key=lambda m: m.get("score", 0), reverse=True)[:5]
    for m in top:
        score      = m.get("score", 0)
        titre      = m.get("titre", "Sans titre")[:55]
        budget     = _format_budget(m)
        plateforme = m.get("plateforme", "").capitalize()
        url        = m.get("url", "#")
        raisons    = m.get("score_raisons", "")[:80]
        lignes += [
            f"{_emoji_score(score)} <b>{titre}</b>",
            f"   Score : <b>{score}/100</b> · {budget}",
            f"   📌 {plateforme}",
        ]
        if raisons:
            lignes.append(f"   💬 <i>{raisons}</i>")
        lignes.append(f"   🔗 <a href='{url}'>Voir la mission</a>")
        lignes.append("")
    if n > 5:
        lignes.append(f"<i>+ {n - 5} autre{s} sur le dashboard.</i>")
    return "\n".join(lignes)


def format_relance(client_nom: str, mission_titre: str, jours: int, url: str = "") -> str:
    lignes = [
        "🦂 <b>Scorpius — Relance recommandée</b>",
        "",
        f"Le client <b>{client_nom}</b> n'a pas répondu depuis <b>{jours} jour{'s' if jours > 1 else ''}</b>.",
        f"Mission : <i>{mission_titre}</i>",
    ]
    if url:
        lignes.append(f"🔗 <a href='{url}'>Voir la mission</a>")
    lignes += ["", "💡 Envisagez une relance amiable."]
    return "\n".join(lignes)


def format_briefing(stats: dict) -> str:
    date = datetime.now().strftime("%A %d %B %Y")
    lignes = [
        f"🦂 <b>Scorpius — Briefing du {date}</b>",
        "",
        "📊 <b>Tableau de bord</b>",
        f"   📋 Nouvelles missions   : <b>{stats.get('nouvelles', 0)}</b>",
        f"   ⏳ En attente réponse   : <b>{stats.get('en_attente', 0)}</b>",
        f"   🔨 En cours             : <b>{stats.get('en_cours', 0)}</b>",
        f"   ✅ Terminées            : <b>{stats.get('terminees', 0)}</b>",
        "",
        "💰 <b>Finances</b>",
        f"   Ce mois    : <b>{stats.get('gains_mois', 0):,.0f} €</b>",
        f"   Total      : <b>{stats.get('gains_total', 0):,.0f} €</b>",
        "",
        "🚀 Bonne journée !",
    ]
    return "\n".join(lignes)


def format_mission_statut(mission_titre: str, ancien_statut: str, nouveau_statut: str) -> str:
    emojis = {
        "proposee": "📋", "en_attente": "⏳",
        "en_cours": "🔨", "terminee": "✅", "refusee": "❌",
    }
    e_ancien  = emojis.get(ancien_statut, "•")
    e_nouveau = emojis.get(nouveau_statut, "•")
    return (
        f"🦂 <b>Scorpius — Mise à jour mission</b>\n\n"
        f"<i>{mission_titre[:60]}</i>\n\n"
        f"{e_ancien} {ancien_statut.replace('_', ' ').capitalize()} "
        f"→ {e_nouveau} <b>{nouveau_statut.replace('_', ' ').capitalize()}</b>"
    )


def format_erreur(module: str, message: str) -> str:
    return (
        f"🦂⚠️ <b>Scorpius — Erreur {module}</b>\n\n"
        f"<code>{message[:300]}</code>\n\n"
        f"<i>{datetime.now().strftime('%H:%M:%S')}</i>"
    )


async def notify_nouvelles_missions(missions: list[dict]) -> bool:
    if not missions:
        return True
    cfg     = get_config()
    chat_id = cfg.notifications.get("telegram_chat_id", "")
    message = format_nouvelles_missions(missions)
    logger.info(f"Telegram → {len(missions)} mission(s) → chat_id {chat_id}")
    return await send_message(chat_id, message)


async def notify_relance(client_nom: str, mission_titre: str, jours: int, url: str = "") -> bool:
    cfg = get_config()
    return await send_message(cfg.notifications.get("telegram_chat_id", ""), format_relance(client_nom, mission_titre, jours, url))


async def notify_briefing(stats: dict) -> bool:
    cfg = get_config()
    return await send_message(cfg.notifications.get("telegram_chat_id", ""), format_briefing(stats))


async def notify_statut_change(mission_titre: str, ancien_statut: str, nouveau_statut: str) -> bool:
    cfg = get_config()
    return await send_message(cfg.notifications.get("telegram_chat_id", ""), format_mission_statut(mission_titre, ancien_statut, nouveau_statut))


async def notify_erreur(module: str, message: str) -> bool:
    cfg = get_config()
    return await send_message(cfg.notifications.get("telegram_chat_id", ""), format_erreur(module, message))


async def notify_custom(texte: str) -> bool:
    cfg = get_config()
    return await send_message(cfg.notifications.get("telegram_chat_id", ""), f"🦂 {texte}")


async def verify_bot() -> dict:
    if not BOT_TOKEN:
        return {"ok": False, "username": "", "erreur": "SCORPIUS_BOT_TOKEN manquant dans .env"}
    result = await _post("getMe", {})
    if result and result.get("ok"):
        bot = result["result"]
        return {"ok": True, "username": bot.get("username", ""), "first_name": bot.get("first_name", ""), "erreur": ""}
    return {"ok": False, "username": "", "erreur": "Token invalide ou API inaccessible"}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s", datefmt="%H:%M:%S")

    async def main():
        print("\n─── Test Telegram ───")

        print("\n[1/3] Vérification du bot...")
        info = await verify_bot()
        if not info["ok"]:
            print(f"❌ Bot invalide : {info['erreur']}")
            sys.exit(1)
        print(f"✅ Bot connecté : @{info['username']}")

        print("\n[2/3] Envoi message test...")
        cfg = get_config()
        ok = await send_message(
            cfg.notifications.get("telegram_chat_id", ""),
            f"🦂 <b>Scorpius v2</b> — Test de connexion réussi ✅\n"
            f"<i>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>",
        )
        print("✅ Message envoyé" if ok else "❌ Échec envoi")

        print("\n[3/3] Envoi notification missions simulées...")
        fausses_missions = [
            {"titre": "Développement API Python REST", "score": 88, "budget_min": 2000, "budget_max": 3000, "devise": "EUR", "plateforme": "codeur", "url": "https://www.codeur.com/projects/test1", "score_raisons": "Parfaite correspondance Python + budget excellent."},
            {"titre": "Refonte site React e-commerce", "score": 72, "budget_min": 1500, "budget_max": 1500, "devise": "EUR", "plateforme": "malt", "url": "https://www.malt.fr/missions/test2", "score_raisons": "Bonne correspondance React, durée courte."},
            {"titre": "Script scraping données B2B", "score": 65, "budget_min": 500, "budget_max": 800, "devise": "EUR", "plateforme": "codeur", "url": "https://www.codeur.com/projects/test3", "score_raisons": "Python pertinent, budget dans la fourchette."},
        ]
        ok = await notify_nouvelles_missions(fausses_missions)
        print("✅ Notification envoyée" if ok else "❌ Échec notification")

        print("\n─── Fin des tests ───")
        print("→ Vérifie ton Telegram, tu dois avoir 2 messages.")

    asyncio.run(main())
