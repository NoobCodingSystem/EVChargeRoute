from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env", override=False)

# Only Open Charge Map is optional and requires a free key. All other providers are keyless.
OPENCHARGEMAP_API_KEY = os.getenv("OPENCHARGEMAP_API_KEY", "").strip()
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
EV_ADMIN_TOKEN = os.getenv("EV_ADMIN_TOKEN", "").strip()
DB_PATH = Path(os.getenv("EV_DB_PATH", str(BASE_DIR / "evchargeroute.db")))
BEE_API_BASE = os.getenv("BEE_API_BASE", "https://ev-charging-stations-api.vercel.app").rstrip("/")
PHOTON_API_BASE = os.getenv("PHOTON_API_BASE", "https://photon.komoot.io").rstrip("/")
OSRM_API_BASE = os.getenv("OSRM_API_BASE", "https://router.project-osrm.org").rstrip("/")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
VEHICLE_INGEST_TOKEN = os.getenv("VEHICLE_INGEST_TOKEN", "").strip()


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()