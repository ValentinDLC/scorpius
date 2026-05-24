from playwright.async_api import async_playwright

async def audit_seo_tags(url: str) -> dict:
    if not url:
        return {
            "seo_title": False,
            "seo_meta_description": False,
            "seo_h1": False,
        }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            title = await page.title()
            meta_desc = await page.locator('meta[name="description"]').get_attribute("content")
            h1_count = await page.locator("h1").count()

            return {
                "seo_title": bool(title and title.strip()),
                "seo_meta_description": bool(meta_desc and meta_desc.strip()),
                "seo_h1": h1_count > 0,
            }
        finally:
            await browser.close()
