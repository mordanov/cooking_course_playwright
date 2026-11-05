"""Walk all trainings → lessons using a single Playwright page."""

import asyncio
import random
from playwright.async_api import Page
import config
from gc.auth import ensure_logged_in


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


async def get_training_info(page: Page, training: dict) -> tuple[str, list[dict]]:
    """Navigate to training page; return (title, [{id, url, locked}])."""
    await _nav(page, training["url"])
    title = ""
    try:
        title = await page.eval_on_selector("h1", "e => e.textContent.trim()")
    except Exception:
        pass

    # accessible lessons
    links = await page.eval_on_selector_all(
        "a[href*='/teach/control/lesson/view/id/']",
        """els => [...new Map(
            els.map(e => {
                const id = e.href.replace(/.*\\/id\\//, '').split('?')[0];
                return [id, {id, url: e.href.split('?')[0], locked: false}];
            })
        ).values()]""",
    )

    # locked indicators — mark as locked but include in list
    locked_texts = await page.eval_on_selector_all(
        ".gc-lock, [class*='lock-lesson'], [class*='lesson-locked']",
        "els => els.map(e => e.closest('[data-lesson-id]')?.dataset?.lessonId || '')",
    )
    locked_ids = {lid for lid in locked_texts if lid}
    for l in links:
        if l["id"] in locked_ids:
            l["locked"] = True

    return title, links
