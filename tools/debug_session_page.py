#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--session", default="")
    parser.add_argument("--html", required=True)
    parser.add_argument("--png", default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--sleep", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=60000)
    args = parser.parse_args()

    Path(args.html).parent.mkdir(parents=True, exist_ok=True)
    if args.png:
        Path(args.png).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)

        ctx_kwargs = {}
        if args.session and Path(args.session).exists():
            ctx_kwargs["storage_state"] = args.session

        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        await page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout)
        await page.wait_for_timeout(args.sleep * 1000)

        html = await page.content()
        Path(args.html).write_text(html, encoding="utf-8")

        if args.png:
            await page.screenshot(path=args.png, full_page=True)

        print(f"url={page.url}")
        print(f"title={await page.title()}")
        print(f"html_chars={len(html)}")
        print(f"html_file={args.html}")
        if args.png:
            print(f"png_file={args.png}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
