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

## Predictive inventory par report
Use the IC3 API through Dexter's authenticated proxy:

```text
/app/ic3/api/reports/predictive-par-levels?location=Alice&start_date=2026-01-01&end_date=2026-12-31
```

Add `&format=csv` to download the same sorted report. Without dates, the endpoint
uses the last 364 days (52 weeks), ending yesterday. Explicit bounds are inclusive
and can cover a calendar year, including leap years. It reads the saved
`inventory_database.json` and `invoice_import_log.json` on each request and maps
product numbers to the runtime catalog. Products absent from the catalog are
included with `catalog_match=false`.

Each row contains overall daily usage, `avg_sunday_usage` through
`avg_saturday_usage`, seven-day `weekly_demand`, `velocity_band`, `target_dos`,
and `target_stock` (`avg_daily_usage * target_dos`), sorted by highest daily
usage. The installed velocity profile remains authoritative. Without the legacy
runtime profile, the matching rules are: fast at >= 2 units/day (6 target days),
medium at >= 0.5 (10 days), and slow below 0.5 (15 days).

Usage is beginning inventory plus receipts minus ending inventory between
successive counts. Counts mark the start of a day: receipts on the closing
count's date belong to the next interval. For gaps, interval usage is distributed
evenly over its days and labeled `estimated_gap`; it is **not** an observed
weekday-specific burn pattern. Gap totals are conserved, including when a
report selects only part of a gap. Quantities stay in saved inventory/receipt
units; no package conversion is inferred.

Negative-usage days are excluded from predictive averages, not counted as zero.
Valid zero-usage days remain included. Days without bounding counts are
unavailable and excluded from the denominator. Review `coverage_status`,
`covered_days`, `sample_days`, `estimated_days`, `unavailable_days`,
`anomaly_days_excluded`, and `weekday_sample_days` before relying on a par.
Items without usable samples have null averages and target stock; partial
history is never presented as a complete observed year.

Existing weekly usage now uses nonoverlapping seven-day windows clipped to the
requested dates, with four-week daily averages weighted by usable sample days.
For weekly reports only, missing inventory counts outside the available count
history are assumed to be zero at each report-window boundary. These days are
marked `assumed_zero` and counted in `assumed_zero_days` in the report and CSV.
Usage based on that assumption is an estimate: received stock might still be on
hand. Boundary sources are included in the API and CSV; stock-dependent order
recommendations and valuation are unavailable when the ending stock is assumed.
Actual counts continue to be used where available. Predictive par and
product activity reports do not make this zero-count assumption.
`avg_weekly_usage_4w` is seven-day demand; the compatibility field
`avg_8day_usage_4w` is eight-day demand, not a weekly total. Daily activity
retains signed usage and exposes estimates/unavailable days in `usage_summary`.
Clients must handle null values when counts cannot establish usage.

In the Product Activity report, select a shortened description to show its full
text, and scroll horizontally to view the date columns. On narrow screens, only
the product number stays fixed while scrolling so the dates remain visible.
In the Dexter portal, the Price Fluctuation report uses the selected location;
switch locations in the portal to report on another location.

Invalid request parameters return 400, an unknown inventory location returns
404, unavailable files return 503, and malformed data returns 422 with a server
log entry. The report does not write inventory, receipts, or saved par settings.

Run the isolated usage checks from the workspace root:
```powershell
python -m unittest discover -s "Dexter Assistant\tests" -p test_inventory_usage.py -v
```

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

## Memory management on small instances
The front door launches each portal app (Manager App, Inventory Control 3,
Product Mix) as its own Python process and proxies to it. On a 512 MB Render
instance those processes together can exceed the memory limit (Product Mix
loads pandas on its first report and keeps it resident), causing an
out-of-memory restart.

To prevent this, child apps with no proxied traffic are stopped automatically
and restarted on the next request (a short cold-start delay):
- `DEXTER_APP_IDLE_STOP_MINUTES` - minutes of inactivity before a child app is
  stopped. Defaults to `20` on Render and `0` (disabled) elsewhere. Set `0` to
  disable.
- `MALLOC_ARENA_MAX=2` - recommended on Linux deployments to reduce glibc
  memory fragmentation in threaded Python (set in `render.yaml`).

