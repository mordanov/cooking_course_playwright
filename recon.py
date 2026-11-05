#!/usr/bin/env python3
"""
Phase 1 reconnaissance — saves everything to recon/ (git-ignored).
Headed browser so you can solve captcha/2FA if needed.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, BrowserContext

load_dotenv()

EMAIL = os.environ.get("GC_EMAIL", "")
PASSWORD = os.environ.get("GC_PASSWORD", "")
BASE_URL = "https://course.welldone.study"
LOGIN_URL = f"{BASE_URL}/cms/system/login"
AUTH_STATE = Path(".auth/state.json")
RECON_DIR = Path("recon")

TRAINING_IDS = ["934751868", "934566154"]
LESSONS_PER_TRAINING = 3


# ── helpers ──────────────────────────────────────────────────────────────────

def setup_dirs():
    RECON_DIR.mkdir(exist_ok=True)
    AUTH_STATE.parent.mkdir(exist_ok=True)


async def login(context: BrowserContext, page: Page):
    print("→ Logging in …")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(1_000)

    # fill email in the login tab — two identical forms on the page (mobile+desktop)
    await page.locator(".state-login input.form-field-email").first.fill(EMAIL)
    pwd = page.locator(".state-login input.form-field-password").first
    await pwd.fill(PASSWORD)
    await pwd.press("Enter")  # btn-login is CSS-hidden; Enter submits reliably

    try:
        await page.wait_for_function(
            "() => !window.location.href.includes('login')", timeout=20_000
        )
    except Exception:
        print("\n⚠️  Captcha / 2FA detected — solve it in the browser, then press Enter.")
        input("  >>> ")
        await page.wait_for_load_state("networkidle")
    await context.storage_state(path=str(AUTH_STATE))
    print(f"  auth saved → {AUTH_STATE}")


async def ensure_auth(context: BrowserContext, page: Page):
    if "login" in page.url:
        await login(context, page)


async def save_snapshot(page: Page, name: str):
    base = RECON_DIR / name
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".html").write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
    print(f"  saved {name}.html + .png")


# ── lesson capture ────────────────────────────────────────────────────────────

async def capture_lesson(page: Page, url: str, label: str) -> dict:
    """Navigate, intercept all network, try to click play, save snapshot."""
    requests_log: list[dict] = []
    responses_log: list[dict] = []

    # sync handlers are fine — Playwright calls them from its event loop
    def on_req(req):
        requests_log.append({
            "url": req.url,
            "type": req.resource_type,
            "method": req.method,
            "headers": dict(req.headers),
        })

    def on_resp(resp):
        responses_log.append({"url": resp.url, "status": resp.status})

    page.on("request", on_req)
    page.on("response", on_resp)

    await page.goto(url, wait_until="load")
    await page.wait_for_timeout(2_000)

    await save_snapshot(page, label)

    # collect iframes before clicking anything
    iframes = await page.eval_on_selector_all(
        "iframe",
        "els => els.map(e => ({src: e.src, id: e.id, name: e.name}))",
    )

    # try clicking play inside every same-origin frame
    for frame in page.frames[1:]:  # skip main frame
        for sel in ["button[aria-label*='lay']", ".play-button", "[class*='play']", "video"]:
            try:
                el = frame.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=2_000)
                    print(f"    clicked play in frame: {frame.url[:70]}")
                    break
            except Exception:
                pass

    # also try on the main page
    for sel in ["button[aria-label*='lay']", ".play-button"]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=2_000)
                break
        except Exception:
            pass

    await page.wait_for_timeout(4_000)  # wait for manifests to arrive

    page.remove_listener("request", on_req)
    page.remove_listener("response", on_resp)

    manifests = [r["url"] for r in requests_log if ".m3u8" in r["url"] or ".mpd" in r["url"]]

    result = {
        "url": url,
        "iframes": iframes,
        "manifests": manifests,
        "requests": requests_log,
    }
    (RECON_DIR / f"{label}_network.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    print(f"  {len(requests_log)} reqs | {len(manifests)} manifests | {len(iframes)} iframes")
    return result


# ── lesson list ───────────────────────────────────────────────────────────────

async def get_lessons(page: Page, training_url: str) -> tuple[list, list]:
    await page.goto(training_url, wait_until="load")
    await page.wait_for_timeout(1_000)

    lessons = await page.eval_on_selector_all(
        "a[href*='/teach/control/lesson'], a[href*='/pl/teach/control/lesson']",
        "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))",
    )
    if not lessons:
        lessons = await page.eval_on_selector_all(
            "a[href*='lesson/view']",
            "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))",
        )

    locked = await page.eval_on_selector_all(
        ".gc-lock, [class*='lock'], [class*='closed'], [class*='blocked']",
        "els => els.map(e => ({text: e.textContent.trim(), "
        "href: e.closest('a')?.href || ''}))",
    )
    return lessons, locked


# ── yt-dlp test ───────────────────────────────────────────────────────────────

def yt_dlp_test(url: str, referer: str, label: str) -> dict:
    out = str(RECON_DIR / f"{label}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--add-header", f"Referer:{referer}",
        "--no-playlist",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--max-filesize", "50m",
        "-o", out,
        url,
    ]
    print(f"  yt-dlp → {url[:80]} …")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        combined = r.stdout + r.stderr
        drm = any(k in combined.lower() for k in ["widevine", "sample-aes", "drm", "encrypted"])
        return {
            "url": url, "referer": referer,
            "returncode": r.returncode, "success": r.returncode == 0,
            "drm": drm, "stderr_tail": r.stderr[-600:],
        }
    except subprocess.TimeoutExpired:
        return {"url": url, "success": False, "error": "timeout"}


async def check_manifest_drm(url: str) -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as c:
            r = await c.get(url)
            return any(k in r.text for k in ["EXT-X-KEY", "SAMPLE-AES", "ContentProtection"])
    except Exception:
        return False


# ── main ──────────────────────────────────────────────────────────────────────

async def main():
    if not EMAIL or not PASSWORD:
        sys.exit("ERROR: GC_EMAIL / GC_PASSWORD not set in .env")

    setup_dirs()
    findings: dict = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx_kwargs = {"storage_state": str(AUTH_STATE)} if AUTH_STATE.exists() else {}
        if ctx_kwargs:
            print(f"Reusing auth from {AUTH_STATE}")
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        # ── trainings list ────────────────────────────────────────────────────
        print("\n=== Trainings list ===")
        await page.goto(f"{BASE_URL}/teach/control/stream", wait_until="load")
        await ensure_auth(context, page)
        await page.goto(f"{BASE_URL}/teach/control/stream", wait_until="load")
        await save_snapshot(page, "trainings_list")

        training_links = await page.eval_on_selector_all(
            "a[href*='/teach/control/stream/view']",
            "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))",
        )
        print(f"  training links visible: {len(training_links)}")
        findings["trainings_list"] = training_links

        # ── each training ─────────────────────────────────────────────────────
        sampled_lessons: list[tuple[str, dict]] = []

        for tid in TRAINING_IDS:
            t_url = f"{BASE_URL}/teach/control/stream/view/id/{tid}"
            print(f"\n=== Training {tid} ===")

            await page.goto(t_url, wait_until="load")
            await ensure_auth(context, page)
            await save_snapshot(page, f"training_{tid}")

            lessons, locked = await get_lessons(page, t_url)
            print(f"  lessons: {len(lessons)}, locked: {len(locked)}")
            findings[f"training_{tid}"] = {"url": t_url, "lessons": lessons, "locked": locked}

            for l in lessons[:LESSONS_PER_TRAINING]:
                sampled_lessons.append((tid, l))

        # ── sample lessons ────────────────────────────────────────────────────
        yt_candidates: list[dict] = []

        for tid, lesson in sampled_lessons:
            url = lesson["href"]
            lid = (url.split("/id/")[-1] if "/id/" in url else url.split("=")[-1]).split("?")[0]
            label = f"lesson_{tid}_{lid}"
            print(f"\n=== Lesson: {lesson['text'][:60]} ===")
            print(f"  {url}")

            await page.goto(url, wait_until="load")
            await ensure_auth(context, page)

            data = await capture_lesson(page, url, label)
            findings[label] = {
                "url": url, "iframes": data["iframes"], "manifests": data["manifests"],
            }

            for m in data["manifests"]:
                referer = next(
                    (r["headers"].get("referer", url) for r in data["requests"] if m in r["url"]),
                    url,
                )
                yt_candidates.append({"manifest": m, "referer": referer, "label": label})

            # also add iframe URLs as direct yt-dlp candidates (e.g. Kinescope)
            for f in data["iframes"]:
                src = f.get("src", "")
                if src and any(h in src for h in ["kinescope", "vimeo", "getcourse"]):
                    yt_candidates.append({"manifest": src, "referer": url, "label": label + "_iframe"})

        # ── yt-dlp tests ──────────────────────────────────────────────────────
        print("\n=== yt-dlp tests ===")
        yt_results = []
        seen: set[str] = set()
        for c in yt_candidates:
            if c["manifest"] in seen or len(yt_results) >= 3:
                continue
            seen.add(c["manifest"])
            drm_in_manifest = await check_manifest_drm(c["manifest"])
            res = yt_dlp_test(c["manifest"], c["referer"], f"yt_test_{len(yt_results)}")
            res["drm_in_manifest"] = drm_in_manifest
            yt_results.append(res)

        findings["yt_dlp_tests"] = yt_results

        # ── detect hostings from all iframes ──────────────────────────────────
        all_srcs = [
            f.get("src", "") if isinstance(f, dict) else str(f)
            for v in findings.values()
            if isinstance(v, dict) and "iframes" in v
            for f in v["iframes"]
        ]
        hostings: dict[str, list] = {}
        for src in all_srcs:
            if not src:
                continue
            for h in ["kinescope.io", "vimeo.com", "getcourse.ru", "player.getcourse"]:
                if h in src:
                    hostings.setdefault(h, []).append(src)
        findings["detected_hostings"] = hostings

        # ── save master findings ──────────────────────────────────────────────
        fp = RECON_DIR / "findings.json"
        fp.write_text(json.dumps(findings, indent=2, ensure_ascii=False))
        print(f"\n=== Done. Findings → {fp} ===")

        input("\nPress Enter to close the browser.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
