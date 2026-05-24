"""
notifications/service.py
Service central de notifications Scorpius.

Canal principal :
- Inbox interne Scorpius

Canaux optionnels :
- Telegram si TELEGRAM_ENABLED=true
"""

import os
import asyncio
import logging
from datetime import datetime

from storage.db import create_notification

logger = logging.getLogger(__name__)


def telegram_enabled() -> bool:
    """
    Telegram devient optionnel.
    """
    return os.getenv("TELEGRAM_ENABLED", "false").lower() in {
        "1", "true", "yes", "on"
    }


def notify_new_missions_sync(missions: list[dict]) -> int | None:
    """
    Crée une notification Inbox pour les nouvelles missions.
    Optionnellement envoie aussi sur Telegram.
    """
    if not missions:
        return None

    n = len(missions)
    top = sorted(
        missions,
        key=lambda m: int(m.get("score", 0)),
        reverse=True
    )[:5]

    title = f"{n} nouvelle{'s' if n > 1 else ''} mission{'s' if n > 1 else ''}"

    lines = []
    for m in top:
        score = int(m.get("score", 0))
        titre = m.get("titre", "Sans titre")
        plateforme = m.get("plateforme", "plateforme")
        lines.append(f"[{score}/100] {titre} — {plateforme}")

    if n > 5:
        lines.append(f"+ {n - 5} autre(s) mission(s)")

    body = "\\n".join(lines)

    notif_id = create_notification(
        type="new_missions",
        title=title,
        body=body,
        source="scraper",
        link="/missions",
        data={
            "count": n,
            "missions": [
                {
                    "titre": m.get("titre"),
                    "score": m.get("score"),
                    "url": m.get("url"),
                    "plateforme": m.get("plateforme"),
                }
                for m in top
            ],
        },
    )

    logger.info(f"Inbox notification créée : {title}")

    if telegram_enabled():
        try:
            from notifications.telegram import notify_nouvelles_missions
            asyncio.run(notify_nouvelles_missions(missions))
        except Exception as e:
            logger.error(f"Telegram optionnel échoué : {e}")

    return notif_id


def notify_system_sync(
    title: str,
    body: str = "",
    type: str = "system",
    source: str = "scorpius",
    link: str = "",
    data: dict | None = None,
) -> int | None:
    """
    Crée une notification système.
    """
    return create_notification(
        type=type,
        title=title,
        body=body,
        source=source,
        link=link,
        data=data or {},
    )


def notify_worker_status_sync(
    title: str,
    body: str = "",
    data: dict | None = None,
):
    """
    Notification liée au worker PC.
    """
    return notify_system_sync(
        title=title,
        body=body,
        type="worker",
        source="worker",
        link="/settings",
        data=data or {},
    )


def notify_error_sync(
    module: str,
    message: str,
):
    """
    Notification erreur.
    """
    return notify_system_sync(
        title=f"Erreur {module}",
        body=message,
        type="error",
        source=module,
        link="/messages",
        data={
            "module": module,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
