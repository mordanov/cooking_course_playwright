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
    """Convert manifest blocks to template-ready dicts with resolved paths.

    When config.S3_MEDIA_BASE_URL is set, video/audio/file src attributes use
    the public S3 URL ({base}/{s3_uuid}/{local_path}) instead of local relative paths.
    """
    media = lesson.get("media", {})
    s3_base = (
        f"{config.S3_MEDIA_BASE_URL}/{lesson['s3_uuid']}"
        if config.S3_MEDIA_BASE_URL and lesson.get("s3_uuid")
        else ""
    )
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
            src = (f"{s3_base}/{lp}" if s3_base else lp) if done else ""
            result.append({
                "type": "video",
                "src": src,
                "original_url": item.get("embed_url", ""),
                "failed": not done,
            })
        elif btype == "audio":
            mid = block["media_id"]
            item = media.get(mid, {})
            lp = item.get("local_path", "")
            done = item.get("status") == "done" and lp and (lesson_dir / lp).exists()
            src = (f"{s3_base}/{lp}" if s3_base else lp) if done else ""
            result.append({
                "type": "audio",
                "src": src,
                "original_url": item.get("src_url", ""),
                "failed": not done,
            })
        elif btype == "file":
            mid = block["media_id"]
            item = media.get(mid, {})
            lp = item.get("local_path", "")
            done = item.get("status") == "done" and lp and (lesson_dir / lp).exists()
            text = block.get("text", item.get("filename", "File"))
            src = ""
            if done:
                # PDF viewer page stays local; its iframe src points to S3 when configured
                pdf_s3_url = f"{s3_base}/{lp}" if s3_base else ""
                src = _write_pdf_viewer(lesson_dir, lp, text, pdf_s3_url)
            result.append({
                "type": "file",
                "src": src,
                "text": text,
                "original_url": item.get("original_url") or item.get("src_url", ""),
                "failed": not done,
            })
    return result


_PDF_VIEWER = """\
<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>html,body,iframe{{margin:0;padding:0;width:100%;height:100%;border:none;overflow:hidden}}</style>
</head><body><iframe src="{pdf}" style="width:100%;height:100%;border:none"></iframe></body></html>
"""


def _write_pdf_viewer(lesson_dir: Path, lp: str, title: str, pdf_url: str = "") -> str:
    """Write a thin iframe-wrapper page next to the PDF and return its relative path."""
    fname = Path(lp).name          # e.g. "document.pdf"
    viewer_path = lesson_dir / (lp + ".html")
    pdf_ref = pdf_url or fname     # absolute S3 URL or local filename
    viewer_path.write_text(
        _PDF_VIEWER.format(title=title.replace("<", "&lt;"), pdf=pdf_ref),
        encoding="utf-8",
    )
    return lp + ".html"            # relative href from lesson/index.html
