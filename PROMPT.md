# Task: offline copy of my GetCourse courses

Read `CLAUDE.md` first — it contains the hard rules, stack and requirements. This file
describes **how** to do the work. Work in phases and **stop for my approval** where marked.
Answer me in Russian.

## Phase 0 — Setup (no approval needed)

1. Create `.gitignore`, `requirements.txt`, `.env.example` (`GC_EMAIL=`, `GC_PASSWORD=`).
2. Install deps into `.venv`, run `playwright install chromium`.
3. Check `yt-dlp` and `ffmpeg` are on PATH; if not, tell me the brew command and wait.
4. Ask me to fill `.env` if it is missing. Commit.

## Phase 1 — Reconnaissance (STOP for approval at the end)

Goal: learn the real site structure instead of guessing. Write a throwaway
`recon.py` that uses Playwright (headed, so I can see it) and saves everything into
`recon/` (git-ignored):

1. Log in at `https://course.welldone.study/cms/system/login` with `.env` credentials.
   Persist storage state to `.auth/state.json` and reuse it on later runs; re-login only
   when redirected to the login page. If a captcha/2FA appears, pause and let me solve it
   in the open browser.
2. Save rendered HTML + screenshot of:
   - the trainings list `/teach/control/stream`;
   - `/teach/control/stream/view/id/934751868` and `/teach/control/stream/view/id/934566154`;
   - 2–3 lessons from them, picking lessons with video, audio and attached files
     if possible, and one locked lesson if one exists.
3. For each lesson, record all network requests (URL, type, status, request headers
   incl. Referer) to a JSON/HAR file, and dump every `<iframe>` src. Click play on each
   player for a few seconds so the HLS/DASH manifests (`.m3u8`/`.mpd`) are requested.
4. Identify the video hosting(s) actually used. The login page already loads
   **Kinescope** and **Vimeo** scripts; GetCourse also has its own HLS player
   (iframe on a `*.getcourse.ru` / `player*.getcourse.ru` domain). For each one found:
   find the manifest URL, the required headers (Referer/Origin/cookies), and try a
   one-off `yt-dlp` download of **one** video to confirm it works. Detect DRM
   (e.g. `EXT-X-KEY` with `SAMPLE-AES`/Widevine, `ContentProtection` in MPD) and report it.
5. Report to me, in Russian, a short findings summary:
   - URL patterns and CSS selectors for: trainings list, nested trainings, lesson list,
     locked lessons, lesson title, lesson content blocks, images, audio, files, video iframes;
   - per video hosting: how to get the manifest, required headers, yt-dlp command that
     worked, DRM yes/no;
   - surprises/risks (pagination, lazy loading, signed URLs that expire, etc.);
   - approximate count of trainings/lessons.
6. Propose the plan for Phase 2 (modules, manifest schema, output layout) adjusted to
   the findings. **Stop and wait for my approval.**

## Phase 2 — Implementation (after approval)

Suggested layout (adjust to recon findings, keep files small and single-purpose):

```
download.py          # entry point: python download.py
config.py            # constants: BASE_URL, OUTPUT_DIR="offline", concurrency, delays
gc/auth.py           # login + storage-state reuse + "am I logged out?" check
gc/crawler.py        # walk trainings → sub-trainings → lessons (one page worker)
gc/lesson.py         # parse one lesson page into a Lesson model (blocks, images, media refs)
gc/media.py          # video/audio/file download (yt-dlp/ffmpeg/httpx), max quality, retries
gc/manifest.py       # offline/manifest.json load/save, content hashes, status per item
gc/render.py         # Jinja2 rendering of the static site
templates/           # base.html, index.html, training.html, lesson.html, style.css
```

Output layout:

```
offline/
  index.html                         # all trainings
  assets/style.css                   # minimal, readable, no external fonts/CDNs
  <training-id>-<slug>/
    index.html                       # lesson list (+ nested trainings); locked = greyed "недоступно"
    <lesson-id>-<slug>/
      index.html                     # title, text, images, <video>, <audio>, file links, prev/next
      media/  images/  files/
  manifest.json
  failures.json
  download.log
```

Requirements recap (details in `CLAUDE.md`):
- Lesson HTML: keep the meaningful content blocks, strip GetCourse scripts/styles/
  tracking, rewrite every image/file/media URL to a local relative path.
  Preserve the course order of trainings and lessons.
- Video: best available quality, final `.mp4` (H.264/AAC if remux is enough; do not
  re-encode unless necessary). Pass the Referer/headers discovered in recon to yt-dlp.
  Capture manifests by intercepting network in Playwright when not present in HTML.
  Signed URLs may expire: resolve them right before downloading.
- Incremental runs via `manifest.json` (lesson content hash + per-media status);
  resume partial downloads; atomic writes.
- Failures → skip, log, placeholder with original-URL link on the lesson page,
  summary at the end + `failures.json`.
- Progress output: one line per lesson and per media item, plus totals at the end.
- After the crawl, (re)render the whole static site from the manifest so it is always
  consistent, even after partial runs.

## Phase 3 — Verification

1. Run on **one lesson** (temporary constant `LIMIT_LESSONS=1` in `config.py`), open it
   via `cd offline && python -m http.server 8000` and check text, images, video seeking,
   audio, file links. Show me the result.
2. Run on **one training**. Then the full run.
3. Run again with no changes and confirm nothing is re-downloaded.
4. Disconnect from the Internet (or check DevTools Network) and confirm the offline site
   makes **zero** external requests.
5. Write a short `README.md` (in Russian): setup, `.env`, `python download.py`,
   how to view, how to update. Commit.

## Definition of done

- `python download.py` downloads all accessible trainings into `./offline/` unattended.
- The offline site opens via `python -m http.server`, works with no Internet, and every
  accessible lesson shows its text, images, playable video/audio and downloadable files.
- Locked lessons appear greyed out in the TOC; failed media show a placeholder and are
  listed in `failures.json`.
- A second run only fetches new/changed content.
- No secrets or downloaded content in git.
