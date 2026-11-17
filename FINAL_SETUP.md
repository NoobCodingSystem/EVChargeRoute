# EVChargeRoute India — updated setup

## Backend
1. Install Python 3.11+.
2. In `backend`, create/activate a virtual environment and run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Configure SMTP values to enable email OTP. Gmail users should use an App Password, not their account password.
5. Set a long random `VEHICLE_INGEST_TOKEN` before accepting vehicle telemetry.
6. Run `uvicorn app.main:app --reload --port 8000`.

## Frontend
1. In `frontend`, run `npm install`.
2. Copy `.env.example` to `.env` and set `VITE_API_BASE=http://localhost:8000`.
3. Run `npm run dev`.

## Implemented updates
- Nearby station search submit button is now a real form submit.
- Nearby station discovery tries BEE-derived data, optional Open Charge Map and OpenStreetMap/Overpass fallback.
- Missing station price, connector/power, status, queue and wait fields receive deterministic simulated demo values and API flags.
- Profile creation/loading requires email OTP. Configure SMTP first.
- Vehicle telemetry ingestion and verified-owner read endpoints are available. A real vehicle-cloud/OEM connector is still required for actual telemetry.

## Important production notes
- Demo station fields are not live facts. The UI labels simulated values.
- The BEE data is a dated public directory, not live availability.
- Telemetry ingestion is a generic authenticated webhook, not a direct OEM integration. Add the correct manufacturer's authorized API/OAuth integration for each supported make/model.
- Before public deployment, add HTTPS, robust per-IP/email OTP throttling, stronger account/session authentication, secret rotation, audit logging, and a privacy/consent flow for location telemetry.
