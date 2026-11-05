from pathlib import Path

BASE_URL = "https://course.welldone.study"
OUTPUT_DIR = Path("offline")
AUTH_STATE = Path(".auth/state.json")
LOGIN_URL = f"{BASE_URL}/cms/system/login"

MEDIA_CONCURRENCY = 2       # concurrent media downloads
NAV_DELAY = (1.0, 3.0)      # random pause between page navigations (seconds)
YTDLP_FORMAT = "bestvideo+bestaudio"
LIMIT_LESSONS = 0           # 0 = no limit; set to 1 for Phase 3 testing
