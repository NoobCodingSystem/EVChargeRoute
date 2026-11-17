# EVChargeRoute India — Google-free edition

This rebuild keeps the existing React + FastAPI app features (dashboard, owner/vehicle profile, route planner, charging-station search, free/premium mode, simulated queue estimator, subscription/purchase history, admin data console and light/dark theme) while replacing Google APIs.

## Provider setup (no mandatory API keys)

| Capability | Provider | Key required? |
|---|---|---|
| India charging stations | India EV Charging Station API, based on BEE public dataset | No |
| Extra station records | Open Charge Map | Optional free key |
| Map display | MapLibre + OpenFreeMap | No |
| Address autocomplete/geocoding | Photon, bounded to India | No |
| Road route and route matrix | OSRM public demo | No |

**Data accuracy note:** the BEE-derived directory currently represents the published snapshot through 26 October 2025. It is not live charger telemetry and does not guarantee current operating status, plug availability, pricing or opening hours. Queue values in this app are simulated. Check station details with the operator before setting out. Public Photon/OSRM endpoints are community services with fair-use limits and no uptime guarantee; for a high-traffic production launch, use a managed/self-hosted instance.

## 1. Run locally (Windows)

1. Install Python 3.11+ and Node.js 20+.
2. Open a terminal in `backend`:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   Copy-Item .env.example .env
   uvicorn app.main:app --reload --port 8000
   ```
3. Open another terminal in `frontend`:
   ```powershell
   npm install
   Copy-Item .env.example .env
   npm run dev
   ```
4. Open the Vite URL (normally http://localhost:5173).

## 2. Optional Open Charge Map API key

The project works without this key. The BEE-derived India directory is the primary source. Add OCM only if you want additional crowd-sourced station records.

1. Visit https://openchargemap.org/site/login and sign in/create an account.
2. Open your profile, choose **My Apps**, then **Register an Application**.
3. Copy the issued API key.
4. Paste it in `backend/.env`:
   ```env
   OPENCHARGEMAP_API_KEY=your_actual_key_here
   ```
5. Restart the FastAPI backend. Do not put this key in frontend `.env`, React code, GitHub, or screenshots.

Official instructions: https://www.openchargemap.org/develop/api

## 3. Netlify + Render deployment

### Render (backend)
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Add environment variables:
  - `CORS_ORIGINS=https://YOUR-NETLIFY-SITE.netlify.app`
  - `EV_ADMIN_TOKEN=` a long random secret for the Data Console
  - `OPENCHARGEMAP_API_KEY=` optional
- Persistent disk is recommended if you need SQLite profiles and purchase history to survive service restarts/redeploys. Set `EV_DB_PATH` to a path on that disk.

### Netlify (frontend)
- Base directory: `frontend`
- Build command: `npm run build`
- Publish directory: `dist`
- Environment variable: `VITE_API_BASE=https://YOUR-RENDER-SERVICE.onrender.com`

After changing frontend environment variables, trigger a fresh deploy. Update Render `CORS_ORIGINS` with the exact Netlify origin.

## 4. India-only behaviour

- Photon autocomplete uses an India bounding box and the backend validates coordinates.
- Route planning rejects points outside India.
- Charging-station results are filtered to plausible India coordinates.
- OSRM calculates road routes; its public demo may occasionally be unavailable or rate-limited.

## 5. API health check

Open `http://localhost:8000/api/health`. The response reports Google removal and provider configuration.

## 6. Important limitations

- BEE station data is a dated public directory, not live availability.
- OCM is crowd-sourced; records may be incomplete or stale.
- Queue/wait estimates are simulated for demonstration and must not be presented as actual station queue data.
- Public Photon and OSRM instances are best for a prototype/demo and not a service-level guarantee.
- OpenFreeMap public tiles require no API key; follow the provider's fair-use guidance.


## 7. Email OTP verification

Profile registration and profile loading now require a verified email. Configure the SMTP variables in `backend/.env` (for Gmail, use an App Password with 2-Step Verification enabled). The OTP expires after 10 minutes, allows at most five attempts, and the verified email remains trusted for 24 hours. Without SMTP configuration, OTP requests are intentionally disabled and the API explains which settings are missing.

## 8. Vehicle telemetry integration (hardware / manufacturer cloud required)

The backend now exposes:
- `POST /api/telemetry/ingest` — authenticated webhook endpoint for a manufacturer's cloud service or a vehicle-side gateway.
- `GET /api/telemetry?email=...` — reads the latest telemetry for a verified account.

Send `X-Vehicle-Token: <VEHICLE_INGEST_TOKEN>` with JSON such as:
```json
{
  "email": "owner@example.com",
  "battery_pct": 72,
  "range_km": 285,
  "odometer_km": 18420,
  "lat": 22.5726,
  "lng": 88.3639,
  "speed_kmh": 0
}
```
This is a secure integration point, not a universal direct connection to every EV. A production connection still needs the specific make/model's authorized API, OAuth consent and credentials (or a compatible telematics/OBD device). Do not scrape a manufacturer's app or collect vehicle credentials. Battery/location data must be protected and transmitted only with the owner's explicit consent. The website does not fabricate telemetry; only station demo values are simulated.

## 9. Station search and demo-data labels

Nearby discovery now tries the BEE-derived directory, optional Open Charge Map, and OpenStreetMap/Overpass as a fallback. Search requires selecting an autocomplete suggestion (not merely typing). Missing price, connectors, power, status, queue and wait are populated with stable demo estimates; each generated field is flagged as simulated in the API. These are not actual charger prices, operational status or queue telemetry.
