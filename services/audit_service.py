import asyncio

from services.pagespeed import run_pagespeed
from services.seo_audit import audit_seo_tags

def compute_audit_score(*, has_site: bool, audit_mobile: bool, audit_performance: int, audit_seo: int, audit_gmb: bool) -> int:
    score = 0
    score += 25 if has_site else 0
    score += 20 if audit_mobile else 0
    score += min(max(audit_performance, 0), 100) * 0.35
    score += min(max(audit_seo, 0), 100) * 0.20
    score += 20 if audit_gmb else 0
    return int(round(min(score, 100)))

async def audit_one_prospect(prospect: dict) -> dict:
    url = prospect.get("url_site")
    has_site = bool(url)

    if has_site:
        try:
            pagespeed = await asyncio.to_thread(run_pagespeed, url)
        except Exception:
            pagespeed = {
                "audit_mobile": False,
                "audit_performance": 0,
            }

        try:
            seo = await audit_seo_tags(url)
        except Exception:
            seo = {
                "seo_title": False,
                "seo_meta_description": False,
                "seo_h1": False,
            }
    else:
        pagespeed = {
            "audit_mobile": False,
            "audit_performance": 0,
        }
        seo = {
            "seo_title": False,
            "seo_meta_description": False,
            "seo_h1": False,
        }

    seo_score = int(
        (
            int(seo["seo_title"])
            + int(seo["seo_meta_description"])
            + int(seo["seo_h1"])
        ) / 3 * 100
    )

    audit = {
        "audit_mobile": pagespeed["audit_mobile"],
        "audit_performance": pagespeed["audit_performance"],
        "audit_seo": seo_score,
        "audit_gmb": bool(prospect.get("audit_gmb", True)),
        "seo_title": seo["seo_title"],
        "seo_meta_description": seo["seo_meta_description"],
        "seo_h1": seo["seo_h1"],
    }

    audit["score_audit"] = compute_audit_score(
        has_site=has_site,
        audit_mobile=audit["audit_mobile"],
        audit_performance=audit["audit_performance"],
        audit_seo=audit["audit_seo"],
        audit_gmb=audit["audit_gmb"],
    )
    return audit

async def audit_many_prospects(prospects: list[dict], concurrency: int = 3) -> list[tuple[int, dict]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _wrapped(prospect: dict):
        async with semaphore:
            audit = await audit_one_prospect(prospect)
            return prospect["id"], audit

    return await asyncio.gather(*[_wrapped(p) for p in prospects])
