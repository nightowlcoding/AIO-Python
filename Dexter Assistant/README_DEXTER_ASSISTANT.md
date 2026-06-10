# Dexter Assistant

Dexter Assistant is a front-door launcher/proxy around exact copies of:
- `ProductMixRestaurantDB`
- `Inventory Control 3`

## Safety model
- Original source apps are not modified.
- This folder contains independent copies used by Dexter Assistant.
- The launcher/proxy code lives outside copied app folders.

## Start
1. Run `start_dexter_assistant.bat`
2. Open `http://127.0.0.1:5080`
3. Use website navigation pages:
	- Home: `http://127.0.0.1:5080/`
	- ProductMix portal: `http://127.0.0.1:5080/portal/productmix`
	- Inventory portal: `http://127.0.0.1:5080/portal/ic3`
	- Admin controls: `http://127.0.0.1:5080/admin`

## Notes
- ProductMix is started with `PM_DEBUG=0` and `PM_OPEN_BROWSER=0`.
- IC3 is started as copied via `Inventory Control 3/app.py`.
- Logs are written to `runtime_logs/`.
- Dexter Assistant auto-starts both apps at launch (with preflight checks).

## Recommended security environment variables
Use these in production or any HTTPS-backed deployment:
- `DEXTER_SECRET_KEY` - required; set a stable secret for session signing.
- `DEXTER_SESSION_COOKIE_SECURE=1` - marks the session cookie `Secure` when served over HTTPS.
- `DEXTER_SESSION_COOKIE_NAME=dexter_session` - optional custom session cookie name.
- `DEXTER_ENABLE_HSTS=1` - enables `Strict-Transport-Security` on secure requests.
- `DEXTER_ADMIN_USER` / `DEXTER_ADMIN_PASS` - optional bootstrap Super Admin credentials.

Suggested defaults:
- Development over HTTP: leave `DEXTER_SESSION_COOKIE_SECURE` and `DEXTER_ENABLE_HSTS` unset.
- Production behind HTTPS: set `DEXTER_SESSION_COOKIE_SECURE=1` and `DEXTER_ENABLE_HSTS=1`.
