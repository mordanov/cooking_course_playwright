# Cooking Course Downloader

Offline copy tool for courses purchased on [course.welldone.study](https://course.welldone.study/) (GetCourse platform). Downloads all accessible trainings and renders a clean static HTML site in `./offline/`.

## What it does

- Logs in with stored credentials, crawls all trainings and sub-trainings
- Saves lesson text, images, videos (best quality via Kinescope HLS), audio, and attached files (PDF, etc.)
- Renders a static site: table of contents + individual lesson pages, no GetCourse JS/CSS
- Incremental: re-running skips already-downloaded content; only re-fetches changed or failed lessons

## Requirements

- Python 3 (`.venv` already set up)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ffmpeg](https://ffmpeg.org/) via Homebrew:
  ```
  brew install yt-dlp ffmpeg
  ```
- Playwright Chromium browser (installed with `playwright install chromium`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create `.env` with your account credentials:
```
GC_EMAIL=your@email.com
GC_PASSWORD=yourpassword
```

## Usage

```bash
source .venv/bin/activate
python download.py
```

When it finishes:
```bash
cd offline && python -m http.server 8000
# open http://localhost:8000
```

## Configuration (`config.py`)

| Variable | Default | Description |
|---|---|---|
| `MEDIA_CONCURRENCY` | `2` | Concurrent media downloads |
| `NAV_DELAY` | `(1.0, 3.0)` | Random pause between page navigations (seconds) |
| `LIMIT_LESSONS` | `0` | Max lessons to process (0 = unlimited) |
| `TRAINING_ID_FILTER` | `""` | Process only one training ID (empty = all) |

## Output structure

```
offline/
  index.html              — table of contents
  <training_id>/
    <lesson_id>/
      index.html          — lesson page
      media/              — videos (.mp4) and audio (.mp3)
      images/             — lesson images
      files/              — PDFs and other attachments
  manifest.json           — incremental state
  failures.json           — failed items from last run
```

## Incremental runs

The downloader resumes safely:
- Lessons are skipped if `parser_version`, all media, and all images are marked `done` and files exist on disk
- Media files are never re-downloaded if the local file is present and non-empty
- Failed lessons are retried on the next run
- Atomic writes (`*.part` → rename) prevent corrupt files on interruption

## Constraints

- **No DRM bypass**: Widevine/FairPlay-protected streams are marked as failed and skipped
- **Read-only**: never submits forms (except login), never clicks "complete lesson" buttons
- **Polite**: one navigation worker, 2–3 concurrent downloads, random delays, exponential backoff on 429/5xx
