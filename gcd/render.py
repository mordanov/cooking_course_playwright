"""Render the complete static site from manifest data."""

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import config

_TMPL_DIR = Path(__file__).parent.parent / "templates"


def render_site(manifest: dict):
    env = Environment(loader=FileSystemLoader(str(_TMPL_DIR)), autoescape=True)

    # assets
    assets = config.OUTPUT_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(_TMPL_DIR / "style.css", assets / "style.css")

    trainings = manifest["trainings"]
    lessons_map = manifest["lessons"]

    # index.html
    _render(env, "index.html", config.OUTPUT_DIR / "index.html", trainings=trainings)

    for training in trainings:
        tid = training["id"]
        t_dir = config.OUTPUT_DIR / tid
        t_dir.mkdir(exist_ok=True)

        lesson_list = [
            lessons_map[lid]
            for lid in training.get("lesson_ids", [])
            if lid in lessons_map
        ]
        locked_list = training.get("locked_lessons", [])

        _render(
            env, "training.html", t_dir / "index.html",
            training=training,
            lessons=lesson_list,
            locked=locked_list,
        )

        for i, lesson in enumerate(lesson_list):
            lid = lesson["id"]
            l_dir = t_dir / lid
            l_dir.mkdir(exist_ok=True)

            prev_lesson = lesson_list[i - 1] if i > 0 else None
            next_lesson = lesson_list[i + 1] if i < len(lesson_list) - 1 else None

            _render(
                env, "lesson.html", l_dir / "index.html",
                training=training,
                lesson=lesson,
                blocks=_render_blocks(lesson, l_dir),
                prev=prev_lesson,
                next=next_lesson,
            )


def _render(env: Environment, template_name: str, out_path: Path, **ctx):
    tmpl = env.get_template(template_name)
    out_path.write_text(tmpl.render(**ctx), encoding="utf-8")


def _render_blocks(lesson: dict, lesson_dir: Path) -> list[dict]:
    """Convert manifest blocks to template-ready dicts with resolved local paths."""
    media = lesson.get("media", {})
    result = []
    for block in lesson.get("blocks", []):
        btype = block["type"]
        if btype == "html":
            result.append({"type": "html", "content": block["content"]})
        elif btype == "video":
            mid = block["media_id"]
            item = media.get(mid, {})
            lp = item.get("local_path", "")
            done = item.get("status") == "done" and lp and (lesson_dir / lp).exists()
            result.append({
                "type": "video",
                "src": lp if done else "",
                "original_url": item.get("embed_url", ""),
                "failed": not done,
            })
        elif btype == "audio":
            mid = block["media_id"]
            item = media.get(mid, {})
            lp = item.get("local_path", "")
            done = item.get("status") == "done" and lp and (lesson_dir / lp).exists()
            result.append({
                "type": "audio",
                "src": lp if done else "",
                "original_url": item.get("src_url", ""),
                "failed": not done,
            })
        elif btype == "file":
            mid = block["media_id"]
            item = media.get(mid, {})
            lp = item.get("local_path", "")
            done = item.get("status") == "done" and lp and (lesson_dir / lp).exists()
            result.append({
                "type": "file",
                "src": lp if done else "",
                "text": block.get("text", item.get("filename", "File")),
                "original_url": item.get("src_url", ""),
                "failed": not done,
            })
    return result
