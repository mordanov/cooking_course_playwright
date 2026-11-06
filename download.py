#!/usr/bin/env python3
"""
Entry point: python download.py
Downloads all accessible trainings to ./offline/, renders the static site.
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from playwright.async_api import async_playwright

import config
from gcd import auth, crawler, lesson as lesson_mod, manifest as mf, media as media_mod, render

# ── failure tracking ──────────────────────────────────────────────────────────

_failures: list[dict] = []


def _fail(context: str, reason: str, url: str = ""):
    _failures.append({"context": context, "reason": reason, "url": url})
    print(f"  ✗ {context}: {reason}")


# ── media download worker ─────────────────────────────────────────────────────

_sem = asyncio.Semaphore(config.MEDIA_CONCURRENCY)


async def _download_one(item: dict, item_key: str, lesson_entry: dict, lesson_dir: Path):
    async with _sem:
        ctx = f"{lesson_entry['id']}/{item_key}"
        try:
            if item["type"] == "video":
                await media_mod.download_video(item, lesson_dir)
            else:
                await media_mod.download_http(item, lesson_dir)
            item["status"] = "done"
            print(f"  ✓ {ctx}")
        except ValueError as e:
            item["status"] = "failed"
            item["error"] = str(e)
            _fail(ctx, str(e), item.get("src_url") or item.get("embed_url", ""))
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            _fail(ctx, str(e), item.get("src_url") or item.get("embed_url", ""))


async def _download_lesson_media(lesson_entry: dict, lesson_dir: Path):
    tasks = []
    for mid, item in lesson_entry.get("media", {}).items():
        if item["status"] == "done" and (lesson_dir / item["local_path"]).exists():
            continue
        tasks.append(_download_one(item, mid, lesson_entry, lesson_dir))
    for img in lesson_entry.get("images", []):
        if img["status"] == "done" and (lesson_dir / img["local_path"]).exists():
            continue
        tasks.append(_download_one(img, img["id"], lesson_entry, lesson_dir))
    if tasks:
        await asyncio.gather(*tasks)


# ── main crawl loop ───────────────────────────────────────────────────────────

async def run():
    media_mod.check_tools()
    config.OUTPUT_DIR.mkdir(exist_ok=True)

    manifest = mf.load()

    async with async_playwright() as pw:
        browser, context = await auth.make_browser_context(pw)
        page = await context.new_page()

        # login if no stored auth
        if not config.AUTH_STATE.exists():
            await auth._do_login(page)
            await page.goto(f"{config.BASE_URL}/teach/control/stream", wait_until="load")

        print("\n=== Crawling trainings list ===")
        trainings_raw = await crawler.get_trainings(page)
        print(f"  found {len(trainings_raw)} trainings")

        # merge with manifest (preserve existing metadata)
        existing_tids = {t["id"] for t in manifest["trainings"]}
        for t in trainings_raw:
            if t["id"] not in existing_tids:
                manifest["trainings"].append({
                    "id": t["id"], "url": t["url"], "title": "",
                    "lesson_ids": [], "locked_lessons": [],
                })

        lesson_count = 0

        for training in manifest["trainings"]:
            if config.TRAINING_ID_FILTER and training["id"] != config.TRAINING_ID_FILTER:
                continue
            tid = training["id"]
            print(f"\n=== Training {tid} ({training.get('title') or '?'}) ===")

            try:
                title, lessons_raw, sub_trainings = await crawler.get_training_info(page, training)
            except Exception as e:
                _fail(f"training {tid}", str(e), training.get("url", ""))
                continue
            if title:
                training["title"] = title

            # add newly discovered sub-trainings to the manifest (deduped)
            existing_tids = {t["id"] for t in manifest["trainings"]}
            for st in sub_trainings:
                if st["id"] not in existing_tids and st["id"] != tid:
                    manifest["trainings"].append({
                        "id": st["id"], "url": st["url"], "title": "",
                        "lesson_ids": [], "locked_lessons": [],
                    })
                    existing_tids.add(st["id"])
                    print(f"  + sub-training {st['id']}")

            # partition accessible / locked
            accessible = [l for l in lessons_raw if not l.get("locked")]
            locked = [l for l in lessons_raw if l.get("locked")]
            training["locked_lessons"] = [{"id": l["id"], "title": ""} for l in locked]

            # update lesson_ids preserving order
            new_ids = [l["id"] for l in accessible]
            # keep existing ids that are still present, add new ones at end
            existing = [lid for lid in training["lesson_ids"] if lid in set(new_ids)]
            added = [lid for lid in new_ids if lid not in set(existing)]
            training["lesson_ids"] = existing + added

            for lesson_stub in accessible:
                if config.LIMIT_LESSONS and lesson_count >= config.LIMIT_LESSONS:
                    print(f"  LIMIT_LESSONS={config.LIMIT_LESSONS} reached, stopping")
                    mf.save(manifest)
                    await browser.close()
                    _finish(manifest)
                    return

                lid = lesson_stub["id"]
                lesson_dir = config.OUTPUT_DIR / tid / lid
                lesson_dir.mkdir(parents=True, exist_ok=True)

                existing_entry = manifest["lessons"].get(lid)

                # Skip only when parser version matches AND all media is done AND files exist.
                # parser_version bump forces a re-parse (added Google Drive button detection).
                _PARSER_VERSION = 3
                all_done = (
                    existing_entry
                    and existing_entry.get("parser_version") == _PARSER_VERSION
                    and all(m["status"] == "done" for m in existing_entry.get("media", {}).values())
                    and all(i["status"] == "done" for i in existing_entry.get("images", []))
                )
                if all_done:
                    files_ok = all(
                        (lesson_dir / m["local_path"]).exists()
                        for m in existing_entry.get("media", {}).values()
                        if m.get("local_path")
                    )
                    if files_ok:
                        if not existing_entry.get("s3_uuid"):
                            existing_entry["s3_uuid"] = str(uuid.uuid4())
                        print(f"  skip {lid} (already done)")
                        lesson_count += 1
                        continue

                print(f"  → parsing lesson {lid}…")
                try:
                    parsed = await lesson_mod.parse(page, lesson_stub["url"])
                except Exception as e:
                    _fail(f"lesson {lid}", str(e), lesson_stub["url"])
                    lesson_count += 1
                    continue

                # Carry forward done-status when the local file already exists.
                # File existence (not content_hash) is the source of truth — avoids
                # re-downloading large videos when we re-parse to pick up new media types.
                if existing_entry:
                    for mid, item in parsed["media"].items():
                        prev = existing_entry.get("media", {}).get(mid, {})
                        if prev.get("status") == "done":
                            local = lesson_dir / prev.get("local_path", item["local_path"])
                            if local.exists() and local.stat().st_size > 0:
                                item["status"] = "done"
                                item["local_path"] = prev["local_path"]
                    for img in parsed["images"]:
                        prev_img = next(
                            (i for i in existing_entry.get("images", []) if i["id"] == img["id"]),
                            None,
                        )
                        if prev_img and prev_img.get("status") == "done":
                            local = lesson_dir / prev_img.get("local_path", img["local_path"])
                            if local.exists() and local.stat().st_size > 0:
                                img["status"] = "done"
                                img["local_path"] = prev_img["local_path"]

                # preserve existing S3 UUID so media URLs don't change on re-parse
                parsed["s3_uuid"] = (existing_entry or {}).get("s3_uuid") or str(uuid.uuid4())
                parsed["id"] = lid
                parsed["training_id"] = tid
                manifest["lessons"][lid] = parsed

                await _download_lesson_media(parsed, lesson_dir)

                lesson_count += 1
                mf.save(manifest)

        await browser.close()

    _finish(manifest)


def _finish(manifest: dict):
    mf.save(manifest)

    # write failures.json
    out = config.OUTPUT_DIR / "failures.json"
    tmp = out.with_suffix(".json.part")
    tmp.write_text(json.dumps(_failures, indent=2, ensure_ascii=False))
    tmp.replace(out)

    # render static site
    print("\n=== Rendering static site ===")
    try:
        render.render_site(manifest)
        print(f"  done → {config.OUTPUT_DIR}/index.html")
    except Exception as e:
        print(f"  render error: {e}")

    # summary
    total = sum(len(t.get("lesson_ids", [])) for t in manifest["trainings"])
    print(f"\n=== Done. {total} lessons, {len(_failures)} failures ===")
    if _failures:
        print("  Failures:")
        for f in _failures:
            print(f"    {f['context']}: {f['reason']}")
    print(f"\nView offline: cd offline && python -m http.server 8000")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
