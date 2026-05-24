import httpx

def run_pagespeed(url: str) -> dict:
    if not url:
        return {
            "audit_mobile": False,
            "audit_performance": 0,
        }

    resp = httpx.get(
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
        params={
            "url": url,
            "strategy": "mobile",
            "category": "performance",
        },
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        score = int(
            (data["lighthouseResult"]["categories"]["performance"]["score"] or 0) * 100
        )
    except Exception:
        score = 0

    return {
        "audit_mobile": score >= 50,
        "audit_performance": score,
        "raw_pagespeed": data,
    }
