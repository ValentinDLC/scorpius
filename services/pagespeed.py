import os
import time
import logging
import httpx

logger = logging.getLogger(__name__)

# Cache simple en mémoire — évite les appels répétés sur la même URL
_pagespeed_cache: dict = {}
_CACHE_TTL = 3600  # 1 heure

def _check_mobile_via_headers(url: str) -> bool:
    """Fallback léger : détecte responsive via meta viewport dans le HTML."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"},
            timeout=8,
            follow_redirects=True,
        )
        html = resp.text[:5000]  # Lire seulement le head
        has_viewport = 'name="viewport"' in html or "name=\'viewport\'" in html
        has_responsive = any(kw in html for kw in [
            "max-width", "min-width", "@media", "responsive", "bootstrap", "tailwind"
        ])
        # 200 + viewport meta = mobile-friendly probable
        return resp.status_code == 200 and has_viewport
    except Exception:
        return False


def run_pagespeed(url: str) -> dict:
    if not url:
        return {
            "audit_mobile": False,
            "audit_performance": 0,
        }

    # Cache hit
    cache_key = url.rstrip("/")
    cached = _pagespeed_cache.get(cache_key)
    if cached and (time.time() - cached["_ts"]) < _CACHE_TTL:
        logger.debug(f"PageSpeed cache hit pour {url}")
        return {k: v for k, v in cached.items() if k != "_ts"}

    api_key = os.getenv("PAGESPEED_API_KEY", "")
    params = {
        "url": url,
        "strategy": "mobile",
        "category": "performance",
    }
    if api_key:
        params["key"] = api_key

    try:
        resp = httpx.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params=params,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        logger.warning(f"PageSpeed timeout pour {url}")
        return {"audit_mobile": False, "audit_performance": 0}
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"PageSpeed HTTP {e.response.status_code} pour {url} — fallback mobile headers"
        )
        # 403 = API non activée, 429 = quota dépassé
        # Fallback : détection mobile via headers HTTP
        mobile = _check_mobile_via_headers(url)
        return {"audit_mobile": mobile, "audit_performance": 0}
    except Exception as e:
        logger.warning(f"PageSpeed erreur inattendue pour {url}: {e}")
        return {"audit_mobile": False, "audit_performance": 0}

    try:
        score = int(
            (data["lighthouseResult"]["categories"]["performance"]["score"] or 0) * 100
        )
    except Exception:
        score = 0

    result = {
        "audit_mobile": score >= 50,
        "audit_performance": score,
        "raw_pagespeed": data,
    }
    # Mise en cache
    _pagespeed_cache[cache_key] = {**result, "_ts": time.time()}
    return result
