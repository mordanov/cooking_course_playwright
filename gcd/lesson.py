"""Parse a lesson page into a structured dict. Captures Kinescope manifest URLs."""

import hashlib
import re
from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page
import config
from gcd.auth import ensure_logged_in


async def parse(page: Page, url: str) -> dict:
    """
    Navigate to url, intercept network, parse content blocks.
    Returns a lesson dict ready to merge into the manifest.
    """
    manifests: dict[str, dict] = {}  # embed_url → {manifest_url, referer}

    def on_request(req):
        if "master.m3u8" in req.url and "kinescope" in req.url:
            ref = req.headers.get("referer", "")
            manifests[ref] = {"manifest_url": req.url, "referer": ref}

    page.on("request", on_request)
    await page.goto(url, wait_until="load")
    await ensure_logged_in(page)
    await page.wait_for_timeout(2000)

    raw_html = await page.content()

    # scroll to each kinescope iframe and click play to trigger manifest load
    for iframe_el in await page.locator("iframe[src*='kinescope']").all():
        try:
            await iframe_el.scroll_into_view_if_needed(timeout=2000)
            await page.wait_for_timeout(500)
        except Exception:
            pass
    for frame in page.frames[1:]:
        if "kinescope" not in frame.url:
            continue
        for sel in ["button[aria-label*='lay']", ".play-button", "video"]:
            try:
                el = frame.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=2000)
                    break
            except Exception:
                pass

    await page.wait_for_timeout(4000)
    page.remove_listener("request", on_request)

    soup = BeautifulSoup(raw_html, "html.parser")

    title = ""
    el = soup.select_one("h2.lesson-title-value")
    if el:
        title = el.get_text(strip=True)

    description = ""
    el = soup.select_one(".lesson-description-value")
    if el:
        description = el.get_text(strip=True)

    blocks: list[dict] = []
    images: list[dict] = []
    media: dict[str, dict] = {}

    video_idx = audio_idx = file_idx = img_idx = 0

    for block in soup.select(".modal-block-content"):
        # ── video (Kinescope iframe) ──────────────────────────────────────────
        iframe = block.select_one("iframe[src*='kinescope.io']")
        if iframe:
            embed_url = (iframe.get("src") or "").split("?")[0]
            # manifest may have been captured with query-params embed URL as key
            minfo = manifests.get(embed_url) or next(
                (v for k, v in manifests.items() if embed_url in k), {}
            )
            mid = f"video_{video_idx}"
            video_idx += 1
            media[mid] = {
                "type": "video",
                "embed_url": embed_url,
                "manifest_url": minfo.get("manifest_url", ""),
                "referer": minfo.get("referer", embed_url),
                "local_path": f"media/{mid}.mp4",
                "status": "pending",
            }
            blocks.append({"type": "video", "media_id": mid})
            continue

        # ── audio ─────────────────────────────────────────────────────────────
        audio_src_tag = block.select_one("audio source")
        if audio_src_tag:
            src = audio_src_tag.get("src") or ""
            mid = f"audio_{audio_idx}"
            audio_idx += 1
            media[mid] = {
                "type": "audio",
                "src_url": src,
                "local_path": f"media/{mid}.mp3",
                "status": "pending",
            }
            blocks.append({"type": "audio", "media_id": mid})
            continue

        # ── file download link ────────────────────────────────────────────────
        file_link = block.select_one("a[href*='fileservice/file/download']")
        if not file_link:
            file_link = block.select_one("a[download]")
        if file_link:
            src = file_link.get("href") or ""
            fname = _guess_filename(file_link, file_idx)
            mid = f"file_{file_idx}"
            file_idx += 1
            media[mid] = {
                "type": "file",
                "src_url": src,
                "filename": fname,
                "local_path": f"files/{fname}",
                "status": "pending",
            }
            blocks.append({"type": "file", "media_id": mid, "text": file_link.get_text(strip=True)})
            continue

        # ── HTML block ────────────────────────────────────────────────────────
        _clean_block(block)
        for img in block.select("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src.startswith("//"):
                src = "https:" + src
            if not src or src.startswith("data:") or "/public/img/" in src:
                continue
            iid = f"img_{img_idx}"
            img_idx += 1
            ext = _img_ext(src)
            local = f"images/{iid}{ext}"
            images.append({"id": iid, "type": "image", "url": src, "local_path": local, "status": "pending"})
            img["src"] = local  # rewrite in stored HTML

        html_content = str(block)
        if html_content.strip():
            blocks.append({"type": "html", "content": html_content})

    content_hash = hashlib.md5(raw_html.encode()).hexdigest()

    return {
        "url": url,
        "title": title,
        "description": description,
        "content_hash": content_hash,
        "blocks": blocks,
        "media": media,
        "images": images,
    }


def _clean_block(tag: Tag):
    for el in tag.select("script, style, noscript, [class*='tracking'], [data-gtm]"):
        el.decompose()


def _guess_filename(link: Tag, idx: int) -> str:
    href = link.get("href") or ""
    name = link.get("download") or href.rstrip("/").split("/")[-1].split("?")[0]
    name = re.sub(r"[^\w.\-]", "_", name)
    if not name or name == "_":
        name = f"file_{idx}"
    if "." not in name[-6:]:
        name += ".bin"
    return name


def _img_ext(url: str) -> str:
    path = url.split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
        if path.lower().endswith(ext):
            return ext
    return ".jpg"
