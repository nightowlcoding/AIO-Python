# Mobile Inventory Sync Bridge - Quick Start Guide

## Overview
The Mobile Inventory Sync Bridge is now integrated with your Inventory Control 3 app. It runs on port 5004 in a separate daemon thread and provides mobile-friendly APIs for inventory synchronization.

## What You Have

### Files Created:
1. **`mobile_sync_bridge.py`** - The bridge server (runs in daemon thread)
2. **`mobile/index.html`** - Mobile UI interface
3. **`mobile/script.js`** - Mobile client logic
4. **`test_mobile_sync_bridge.py`** - Automated test suite
5. **`restart_ic3_with_mobile_bridge.bat`** - Windows batch restart script
6. **`restart_ic3_with_mobile_bridge.ps1`** - PowerShell restart script

### Endpoints Available:
- `GET  /api/health` - Health check
- `GET  /api/token-info` - Token information
- `GET  /api/inventory/mobile-sheet` - Get all products with suggested quantities
- `POST /api/inventory/mobile-sync` - Sync inventory counts (requires API token)
- `GET  /` or `/mobile/` - Mobile UI interface

## How to Start

### Option 1: PowerShell (Recommended for your setup)
```powershell
# Navigate to IC3 directory
cd "c:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Inventory Control 3"

# Run the restart script
.\restart_ic3_with_mobile_bridge.ps1
```

### Option 2: Batch File
```cmd
# Double-click this file:
c:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Inventory Control 3\restart_ic3_with_mobile_bridge.bat
```

### Option 3: Manual Start
```powershell
cd "c:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Inventory Control 3"
python app.py
```

## When the App Starts

You'll see output like this:
```
[ic3] Restored products_list from backup products_2026-05-18_20-44-58.json (333 items)
[ic3] Restored inventory_data from disk (2 locations)
[ic3] Mobile sync bridge started on port 5004
[2026-06-06 02:52:49,533] mobile_sync_bridge - INFO - Full token: 6dhOFJbgVyrMHXKAOsI1LkboqlDbffCE1BmNZ105aZA
[2026-06-06 02:52:49,533] mobile_sync_bridge - INFO - Mobile UI: http://127.0.0.1:5004/mobile/
[ic3] Running via waitress on 127.0.0.1:5003 (threads=8)
```

**Copy the API Token** from the startup logs - you'll need it for the mobile UI.

## Access the Services

### Main App (IC3):
```
http://127.0.0.1:5003
```

### Mobile Inventory Sync UI:
```
http://127.0.0.1:5004/
or
http://127.0.0.1:5004/mobile/
```

## Using the Mobile UI

1. Open: `http://127.0.0.1:5004/`
2. Paste the API token from startup logs into the "API Token" field
3. Enter a location (e.g., "Front Counter")
4. Leave date as today (or change it)
5. Enter quantities for each product
6. Click "Submit Counts"

The UI will:
- Load all 333 products automatically
- Show Par Level, Current On Hand, and Suggested quantities
- Track how many items you've filled in (real-time)
- Validate your form before submission
- Save your API token to browser storage for convenience

## Testing

Run the automated test suite to verify everything works:

```powershell
cd "c:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Inventory Control 3"
$env:MOBILE_SYNC_API_TOKEN="<paste-token-from-logs>"
python test_mobile_sync_bridge.py
```

Expected output:
```
Results: 6/6 tests passed
```

## API Token Security

- Token is auto-generated on each app startup (32 characters, URL-safe)
- Required for POST /api/inventory/mobile-sync endpoint
- Supports multiple auth methods:
  - Header: `Authorization: Bearer <token>`
  - Header: `X-API-Token: <token>`
  - Query param: `?token=<token>`
- Mobile UI stores token in browser localStorage for convenience
- Clear browser storage if you need to reset the token

## Troubleshooting

### Mobile UI returns 404
- The bridge needs to be restarted to serve static files
- Use the restart script above

### "Cannot connect to bridge" message
- Make sure IC3 is running
- Check that port 5004 is not in use by another process
- Try accessing http://127.0.0.1:5004/api/health directly

### API token not working
- Copy the token from the startup logs (don't share it!)
- Paste it exactly into the mobile UI token field
- Each app restart generates a new token

### Bridge not starting
- Check the app startup logs for errors
- Verify mobile_sync_bridge.py is in the correct directory
- Check Python imports are available

## Project Structure
```
Inventory Control 3/
├── app.py                          (Main app - now starts mobile bridge)
├── mobile_sync_bridge.py           (Bridge server)
├── test_mobile_sync_bridge.py      (Test suite)
├── restart_ic3_with_mobile_bridge.bat
├── restart_ic3_with_mobile_bridge.ps1
└── mobile/
    ├── index.html                  (Mobile UI)
    └── script.js                   (Mobile client logic)
```

## Next Steps

1. **Test the Setup:**
   - Restart IC3 using the script
   - Access mobile UI at http://127.0.0.1:5004/
   - Run the test suite

2. **Customize (Optional):**
   - Edit mobile/index.html for branding
   - Modify mobile/script.js for additional features
   - Add custom product filters or sorting

3. **Deploy (Production):**
   - Set MOBILE_SYNC_API_TOKEN environment variable
   - Use production WSGI server (waitress, gunicorn)
   - Run behind reverse proxy with HTTPS

## Questions or Issues?

All files are well-documented with comments. Check:
- `mobile_sync_bridge.py` - Backend logic
- `mobile/script.js` - Frontend logic
- `test_mobile_sync_bridge.py` - Test examples and usage patterns
