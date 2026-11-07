import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

BASE_URL = "https://course.welldone.study"
OUTPUT_DIR = Path("offline")
AUTH_STATE = Path(".auth/state.json")
LOGIN_URL = f"{BASE_URL}/cms/system/login"

MEDIA_CONCURRENCY = 2       # concurrent media downloads
NAV_DELAY = (1.0, 3.0)      # random pause between page navigations (seconds)
YTDLP_FORMAT = "bestvideo+bestaudio"
LIMIT_LESSONS = 0           # 0 = no limit; set to 1 for Phase 3 testing
TRAINING_ID_FILTER = ""              # empty = all; set to one ID to test a single training

# Public Hetzner Object Storage base URL (no trailing slash).
# When set, rendered HTML uses S3 URLs for video/audio/PDF instead of local paths.
# Example: https://cooking-course.hel1.your-objectstorage.com
S3_MEDIA_BASE_URL = os.getenv("S3_MEDIA_BASE_URL", "")
