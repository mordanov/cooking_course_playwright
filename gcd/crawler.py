"""Walk all trainings → lessons using a single Playwright page."""

import asyncio
import random
from playwright.async_api import Page
import config
from gcd.auth import ensure_logged_in


async def _nav(page: Page, url: str):
    await page.goto(url, wait_until="load")
    await ensure_logged_in(page)
    await asyncio.sleep(random.uniform(*config.NAV_DELAY))


async def get_trainings(page: Page) -> list[dict]:
    """Return [{id, url}] for every unique training."""
    await _nav(page, f"{config.BASE_URL}/teach/control/stream")
    rows = await page.eval_on_selector_all(
        "a[href*='/teach/control/stream/view/id/']",
        """els => [...new Map(
            els.map(e => {
                const id = e.href.replace(/.*\\/id\\//, '').split('?')[0];
                return [id, {id, url: e.href.split('?')[0]}];
            })
        ).values()]""",
    )
    return rows


async def get_training_info(page: Page, training: dict) -> tuple[str, list[dict], list[dict]]:
    """Navigate to training page; return (title, [{id, url, locked}], [{id, url}] sub-trainings)."""
    await _nav(page, training["url"])
    title = ""
    try:
        title = await page.eval_on_selector("h1", "e => e.textContent.trim()")
    except Exception:
        pass

    # accessible lessons — two URL patterns used by GetCourse
    links = await page.evaluate("""() => {
        const seen = new Map();
        for (const a of document.querySelectorAll('a[href]')) {
            const h = a.href;
            let id = null, url = null;
            const m1 = h.match(/\\/teach\\/control\\/lesson\\/view\\/id\\/(\\d+)/);
            if (m1) { id = m1[1]; url = h.split('?')[0]; }
            const m2 = h.match(/\\/pl\\/teach\\/control\\/lesson\\/view.*[?&]id=(\\d+)/);
            if (m2) { id = m2[1]; url = h.split('#')[0]; }
            if (id && !seen.has(id)) seen.set(id, {id, url, locked: false});
        }
        return [...seen.values()];
    }""")

    # locked indicators — mark as locked but include in list
    locked_texts = await page.eval_on_selector_all(
        ".gc-lock, [class*='lock-lesson'], [class*='lesson-locked']",
        "els => els.map(e => e.closest('[data-lesson-id]')?.dataset?.lessonId || '')",
    )
    locked_ids = {lid for lid in locked_texts if lid}
    for l in links:
        if l["id"] in locked_ids:
            l["locked"] = True

    # sub-trainings on this page (for trainings that contain nested streams)
    sub_trainings = await page.evaluate("""() => {
        const seen = new Map();
        for (const a of document.querySelectorAll('a[href*="/teach/control/stream/view/id/"]')) {
            const m = a.href.match(/\\/teach\\/control\\/stream\\/view\\/id\\/(\\d+)/);
            if (m) seen.set(m[1], {id: m[1], url: a.href.split('?')[0]});
        }
        return [...seen.values()];
    }""")

    return title, links, sub_trainings
