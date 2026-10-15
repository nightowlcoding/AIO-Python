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

## ProductMix and IC3 Item History
In the Production List Report, select a location and date range, then click the
production ingredient name. Use **Link IC3 Item** to search IC3's actual catalog
by description, nickname, or product number. Check the package size and save
the selection. Each link is saved for that location; changing report dates does
not change the link. **Change IC3 Item** and **Remove Link** only change the
ProductMix association, never IC3 inventory or orders.

The focused report shows IC3 supplier purchase quantities and recorded dates,
plus the number of saved inventory count dates and the quantity on each date.
Zero inventory counts are included. Same-day edits overwrite IC3's saved count,
so this is not a count of individual counting actions. Inventory snapshots are
not added together. Purchases use IC3's saved order totals, not an additional sum
of invoice quantities. Package information is shown, but quantities remain in
IC3's native units; no case-to-piece conversion or forecast is inferred.

Explicit date bounds are inclusive. Blank bounds mean all saved history. Both
ProductMix and IC3 need the updated code; older IC3 responses are rejected rather
than silently presenting a recent window as a full-period report. An outage is
shown as unavailable, not as zero purchases, and does not erase the saved link.

Portal requests normally use Dexter's authenticated `/app/ic3` proxy, so dynamic
IC3 ports are supported. `PM_DEXTER_BASE_URL` can override Dexter's trusted
internal origin; otherwise it uses loopback with `DEXTER_PORT`, then `PORT`
(Render), then port 5080. Never configure this as an untrusted external URL:
the bridge forwards the current Dexter session cookie and rejects redirects.
The proxy rechecks the active company/location; switch location in Dexter before
viewing another location's comparison.

For a dedicated IC3 service with a fixed address, set `PM_IC3_BASE_URL` to its
trusted internal origin. This avoids the extra Dexter proxy request and is also
the connection used by standalone, authenticated ProductMix. No browser cookies
are forwarded to a directly configured IC3 service. Keep internal app ports
private. An unauthenticated formula-mode comparison must be opened through Dexter.

Run the isolated integration checks from the workspace root:
```powershell
python -m unittest discover -s "Dexter Assistant/tests" -p test_productmix_ic3.py -v
```
The tests use temporary SQLite data and isolated Flask routes; they do not load
or edit live inventory, orders, or ProductMix records.

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
