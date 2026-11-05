import os
from dotenv import load_dotenv
from playwright.async_api import Page
import config

load_dotenv()
_EMAIL = os.environ.get("GC_EMAIL", "")
_PASSWORD = os.environ.get("GC_PASSWORD", "")

_logout_streak = 0


async def make_browser_context(playwright):
    browser = await playwright.chromium.launch(headless=True)
    kwargs = {"storage_state": str(config.AUTH_STATE)} if config.AUTH_STATE.exists() else {}
    context = await browser.new_context(**kwargs)
    return browser, context


async def ensure_logged_in(page: Page):
    global _logout_streak
    if "login" not in page.url:
        _logout_streak = 0
        return
    _logout_streak += 1
    if _logout_streak >= 2:
        raise RuntimeError("Logged out twice in a row — stopping")
    await _do_login(page)


async def _do_login(page: Page):
    if not _EMAIL or not _PASSWORD:
        raise RuntimeError("GC_EMAIL / GC_PASSWORD not set in .env")
    print("  → logging in…")
    await page.goto(config.LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)
    await page.locator(".state-login input.form-field-email").first.fill(_EMAIL)
    pwd = page.locator(".state-login input.form-field-password").first
    await pwd.fill(_PASSWORD)
    await pwd.press("Enter")
    try:
        await page.wait_for_function(
            "() => !window.location.href.includes('login')", timeout=20_000
        )
    except Exception:
        raise RuntimeError("Login failed — check .env credentials")
    config.AUTH_STATE.parent.mkdir(exist_ok=True)
    await page.context.storage_state(path=str(config.AUTH_STATE))
    print("  auth saved")
