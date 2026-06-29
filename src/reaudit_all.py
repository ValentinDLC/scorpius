import asyncio
from services.audit_service import audit_one_prospect
from storage.prospects import list_prospects, update_prospect_audit

async def reaudit_prospect(p):
    if p.get('url_site'):
        try:
            audited = await audit_one_prospect(p)
            update_prospect_audit(p['id'], audited)
            print(f"Updated {p['nom']}: score={audited['score_audit']}")
        except Exception as e:
            print(f"Error auditing {p['nom']}: {e}")
    else:
        print(f"Skipping {p['nom']} (no website)")

async def main():
    prospects = list_prospects(limit=1000)
    tasks = [reaudit_prospect(p) for p in prospects]
    await asyncio.gather(*tasks)

asyncio.run(main())
print("Re-audit complete")
