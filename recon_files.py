#!/usr/bin/env python3
"""
One-shot recon: visit the trainings list + each training page,
collect any file download links (PDF, fileservice, etc.) found
OUTSIDE lesson pages, and print them.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from playwright.async_api import async_playwright
import config
from gcd import auth, manifest as mf
from gcd.crawler import _nav

_FILE_EXTS = {".pdf", ".zip", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".rar", ".7z"}

def _is_file_link(href: str) -> bool:
    if not href or href.startswith(("data:", "mailto:", "#", "javascript:")):
        return False
    if "/fileservice/file/download" in href:
        return True
    path = href.split("?")[0].lower()
    return any(path.endswith(ext) for ext in _FILE_EXTS)


async def collect_links(page, url: str, label: str) -> list[dict]:
    try:
        await _nav(page, url)
    except Exception as e:
        print(f"  ERROR {label}: {e}")
        return []
    links = await page.evaluate("""() =>
        [...document.querySelectorAll('a[href]')]
            .map(a => ({text: a.textContent.trim().slice(0, 80), href: a.href}))
    """)
    found = [l for l in links if _is_file_link(l["href"])]
    return found


async def run():
    manifest = mf.load()

    async with async_playwright() as pw:
        browser, context = await auth.make_browser_context(pw)
        page = await context.new_page()

        results = {}

        # Main stream page
        print("Checking /teach/control/stream …")
        links = await collect_links(page, f"{config.BASE_URL}/teach/control/stream", "stream-list")
        if links:
            results["stream_list"] = links
            for l in links:
                print(f"  FOUND: {l['text']!r} → {l['href']}")
        else:
            print("  none")

        # Each training page
        for t in manifest["trainings"]:
            label = f"training {t['id']} ({t.get('title','?')})"
            print(f"Checking {label} …")
            links = await collect_links(page, t["url"], label)
            if links:
                results[t["id"]] = links
                for l in links:
                    print(f"  FOUND: {l['text']!r} → {l['href']}")
            else:
                print("  none")

        await browser.close()

    out = Path("recon/training_files.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out}")
    total = sum(len(v) for v in results.values())
    print(f"Total file links found outside lessons: {total}")


if __name__ == "__main__":
    asyncio.run(run())
