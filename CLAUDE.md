# CLAUDE.md

## Project

Personal-use tool that creates an **offline copy** of the courses I bought on
`https://course.welldone.study/` (a **GetCourse** school). Output is a clean static
HTML site in `./offline/`, served locally with `python -m http.server`, that needs no
Internet access.

The user owns a paid account. This is for private, personal viewing only.

## Communication

- Reply to the user in **Russian**. Code, comments, commits, logs: English.
- Be concise. Ask before making decisions not covered by this file or `PROMPT.md`.

## Hard rules

- **Never** commit or print secrets. Credentials live only in `.env`
  (`GC_EMAIL`, `GC_PASSWORD`). Browser state/cookies live in `.auth/`.
- `.gitignore` must contain: `.env`, `.auth/`, `offline/`, `recon/`, `.venv/`,
  `__pycache__/`, `*.log`.
- **Do not bypass DRM** (Widevine/FairPlay-encrypted streams). If a stream is DRM-protected,
  mark it as failed with reason `drm` and move on.
- Be polite to the server: one page-navigation worker, 2–3 concurrent media downloads,
  random 1–3 s pause between page navigations, exponential backoff on 429/5xx.
  Never parallelise logins. Stop the run if the session gets logged out twice in a row.
- Read-only: never submit forms other than login, never post homework/comments,
  never click "complete lesson"-type buttons.

## Stack

- Python 3 in the existing `.venv`. Dependencies in `requirements.txt`
  (`playwright`, `python-dotenv`, `beautifulsoup4`, `jinja2`, `httpx` if needed).
- Playwright (Chromium) for login, page rendering and network interception.
- System `yt-dlp` and `ffmpeg` (Homebrew) for HLS/DASH → mp4. Check they exist at
  startup and print the `brew install` command if missing.
- Entry point: `python download.py` — **no CLI options**. Tunables are constants in
  `config.py`.

## Domain glossary

- **Training (тренинг)** — a GetCourse course/stream, URL `/teach/control/stream/view/id/<id>`.
  A training may contain nested sub-trainings and/or lessons.
- **Lesson (урок)** — a page with content blocks, URL like `/teach/control/lesson/view/id/<id>`
  or `/pl/teach/control/lesson/view?id=<id>`.
- **Media** — video, audio, or attached file belonging to a lesson.
- **Locked lesson** — visible in the list but not accessible (schedule/homework gate).
- **Manifest** — `offline/manifest.json`, the source of truth for incremental runs.

## Behaviour requirements

- Scope: **all trainings available to the account** (start at `/teach/control/stream`),
  recursing into sub-trainings. Known examples:
  `/teach/control/stream/view/id/934751868`, `/teach/control/stream/view/id/934566154`.
- Content to save: lesson text + images, video (max available quality), audio,
  attached files (PDF etc., typically `/fileservice/file/download/...`).
- Output = own clean templates (table of contents + lesson pages), no GetCourse chrome/JS.
  Videos use native `<video controls>`, audio `<audio controls>`. All URLs relative.
- Locked lessons: skip, but list them in the TOC greyed out as "недоступно".
- Failures: skip, log, continue. Lesson page shows a placeholder with a link to the
  original URL for each failed media item. Print a failure summary at the end and write
  `offline/failures.json`.
- Incremental: re-running resumes interrupted downloads and only re-fetches lessons that
  are new or whose content hash changed. Already-downloaded media is never re-downloaded
  unless its file is missing or zero-sized. Write files atomically (`*.part` → rename).

## Workflow

- Phase 0 (recon) and the plan need explicit user approval before writing the
  downloader — see `PROMPT.md`.
- No automated tests. Verify manually on one lesson, then one training, then everything.
- Commit after each working milestone with a clear message.
