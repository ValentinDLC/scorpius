#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys

import browser_cookie3

LOADERS = {
    "chrome": getattr(browser_cookie3, "chrome", None),
    "chromium": getattr(browser_cookie3, "chromium", None),
    "edge": getattr(browser_cookie3, "edge", None),
    "brave": getattr(browser_cookie3, "brave", None),
    "firefox": getattr(browser_cookie3, "firefox", None),
    "safari": getattr(browser_cookie3, "safari", None),
}

def browser_order(name: str):
    if name and name != "auto":
        fn = LOADERS.get(name)
        if not callable(fn):
            raise SystemExit(f"Browser non supporté: {name}")
        return [(name, fn)]
    return [(k, v) for k, v in LOADERS.items() if callable(v)]

def load_jar(fn, domain: str):
    try:
        return fn(domain_name=domain)
    except TypeError:
        return fn()

def normalize_samesite(cookie):
    rest = getattr(cookie, "_rest", {}) or {}
    raw = str(rest.get("SameSite") or "Lax").capitalize()
    return raw if raw in {"Lax", "Strict", "None"} else "Lax"

def is_http_only(cookie):
    rest = getattr(cookie, "_rest", {}) or {}
    return "HttpOnly" in rest or bool(rest.get("HttpOnly"))

def matches_domain(cookie_domain: str, wanted: str) -> bool:
    cookie_domain = (cookie_domain or "").lower().lstrip(".")
    wanted = (wanted or "").lower().lstrip(".")
    return (
        cookie_domain == wanted
        or cookie_domain.endswith("." + wanted)
        or wanted in cookie_domain
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True, help="slug plateforme, ex: codeur")
    parser.add_argument("--domain", required=True, help="domaine, ex: codeur.com")
    parser.add_argument("--browser", default="auto", help="chrome|safari|firefox|edge|brave|chromium|auto")
    parser.add_argument("--output", default="", help="fichier de sortie facultatif")
    args = parser.parse_args()

    output = args.output or f"data/sessions/{args.slug}_session.json"
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    for browser_name, fn in browser_order(args.browser):
        try:
            jar = load_jar(fn, args.domain)
        except Exception as e:
            print(f"[-] {browser_name}: {e}")
            continue

        cookies = []
        for c in jar:
            if not matches_domain(getattr(c, "domain", ""), args.domain):
                continue

            expires = float(c.expires) if getattr(c, "expires", None) else -1

            cookies.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path or "/",
                "expires": expires,
                "httpOnly": is_http_only(c),
                "secure": bool(c.secure),
                "sameSite": normalize_samesite(c),
            })

        if cookies:
            out.write_text(
                json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[+] Session importée depuis {browser_name}")
            print(f"[+] Domaine : {args.domain}")
            print(f"[+] Slug    : {args.slug}")
            print(f"[+] Cookies : {len(cookies)}")
            print(f"[+] Fichier : {out}")
            return 0

    print("[-] Aucun cookie trouvé pour ce domaine.")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
