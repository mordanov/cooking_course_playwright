"""Download video (yt-dlp), audio/images/files (httpx). Atomic writes."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import httpx

import config

_RETRY = 3


def _cookies() -> dict[str, str]:
    if not config.AUTH_STATE.exists():
        return {}
    state = json.loads(config.AUTH_STATE.read_text())
    return {c["name"]: c["value"] for c in state.get("cookies", [])}


async def download_video(media: dict, lesson_dir: Path) -> None:
    """Run yt-dlp in a thread pool so the event loop stays free."""
    manifest_url = media.get("manifest_url", "")
    if not manifest_url:
        raise ValueError("no manifest_url — lesson page must be re-visited")
    referer = media.get("referer", manifest_url)
    out = lesson_dir / media["local_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.get_event_loop().run_in_executor(
        None, _yt_dlp_sync, manifest_url, referer, out
    )


def _yt_dlp_sync(manifest_url: str, referer: str, out: Path):
    part = out.with_suffix(".mp4.part")
    cmd = [
        "yt-dlp",
        "--add-header", f"Referer:{referer}",
        "--no-playlist",
        "-f", config.YTDLP_FORMAT,
        "--merge-output-format", "mp4",
        "-o", str(out),
        manifest_url,
    ]
    for attempt in range(1, _RETRY + 1):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            if part.exists():
                part.unlink(missing_ok=True)
            return
        # DRM → mark and stop retrying
        if any(k in (r.stdout + r.stderr).lower() for k in ["widevine", "sample-aes", "drm"]):
            raise ValueError("drm")
        if attempt < _RETRY:
            import time; time.sleep(2 ** attempt)
    raise RuntimeError(f"yt-dlp failed after {_RETRY} attempts:\n{r.stderr[-400:]}")


async def download_http(media_or_img: dict, lesson_dir: Path) -> None:
    """Download audio/image/file via httpx with auth cookies."""
    src = media_or_img.get("src_url") or media_or_img.get("url", "")
    if src.startswith("//"):
        src = "https:" + src
    out = lesson_dir / media_or_img["local_path"]
    out.parent.mkdir(parents=True, exist_ok=True)

    cookies = _cookies()
    for attempt in range(1, _RETRY + 1):
        try:
            await _fetch(src, out, cookies)
            return
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                await asyncio.sleep(2 ** attempt)
            else:
                raise
        except Exception:
            if attempt == _RETRY:
                raise
            await asyncio.sleep(2 ** attempt)


async def _fetch(url: str, out: Path, cookies: dict):
    part = Path(str(out) + ".part")
    async with httpx.AsyncClient(
        cookies=cookies, follow_redirects=True, timeout=60
    ) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                async for chunk in r.aiter_bytes(8192):
                    f.write(chunk)
    part.replace(out)


def check_tools():
    missing = [t for t in ("yt-dlp", "ffmpeg") if not shutil.which(t)]
    if missing:
        tools = " ".join(missing)
        raise SystemExit(
            f"Missing: {tools}\nInstall with: brew install {tools}"
        )
