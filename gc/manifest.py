"""Load/save offline/manifest.json. Single source of truth for incremental runs."""

import json
from pathlib import Path
import config

_PATH = config.OUTPUT_DIR / "manifest.json"
_VERSION = 1


def load() -> dict:
    if _PATH.exists():
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if data.get("version") == _VERSION:
            return data
    return {"version": _VERSION, "trainings": [], "lessons": {}}


def save(manifest: dict):
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    tmp = _PATH.with_suffix(".json.part")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_PATH)


def lesson_needs_work(manifest: dict, lesson_id: str, content_hash: str) -> bool:
    """True if lesson has never been fully processed or content changed."""
    entry = manifest["lessons"].get(lesson_id)
    if not entry:
        return True
    if entry.get("content_hash") != content_hash:
        return True
    # needs work if any media item is not done
    for item in entry.get("media", {}).values():
        if item.get("status") != "done":
            return True
    for img in entry.get("images", []):
        if img.get("status") != "done":
            return True
    return False


def media_done(lesson_entry: dict, media_id: str, lesson_dir: Path) -> bool:
    item = lesson_entry.get("media", {}).get(media_id, {})
    if item.get("status") != "done":
        return False
    lp = item.get("local_path", "")
    return lp and (lesson_dir / lp).exists() and (lesson_dir / lp).stat().st_size > 0


def image_done(img_entry: dict, lesson_dir: Path) -> bool:
    if img_entry.get("status") != "done":
        return False
    lp = img_entry.get("local_path", "")
    return lp and (lesson_dir / lp).exists() and (lesson_dir / lp).stat().st_size > 0
