# Auto-Sync Database Documentation

## Overview

Auto-sync is an automated git synchronization system that ensures your database changes (product mixes, daily operation logs, inventory control data) are automatically committed and pushed to GitHub. This protects your data against server crashes and ensures all users have the latest information.

## What Gets Auto-Synced

The following folders are monitored and synced automatically:

- **ProductMixRestaurantDB/** - Product mix database and configuration
- **daily_logs/** - Daily operation logs (CSV files)
- **inventory_data/** - Inventory control product lists
- **Inventory Control 3/data/** - IC3 backup data

## How It Works

1. **Background Scheduler**: When Dexter Assistant starts, it initializes a background scheduler that runs every 30 minutes (configurable)
2. **Change Detection**: The scheduler checks if any tracked database files have changed
3. **Auto-Commit**: If changes are found, they are automatically committed to git with a timestamp
4. **Auto-Push**: Changes are automatically pushed to the `checkpoint/dexter-assist-20260601-173327` branch on GitHub
5. **Data Safety**: Even if Render crashes, your data is safely backed up on GitHub

## Environment Variables

You can customize auto-sync behavior with these environment variables on Render:

### Enable/Disable Auto-Sync
```
DEXTER_AUTOSYNC_ENABLED=1    # 1 to enable (default), 0 to disable
```

### Change Sync Interval
```
DEXTER_AUTOSYNC_INTERVAL_MINUTES=30    # Default: 30 minutes, adjust as needed
```

## API Endpoints

### Check Auto-Sync Status
```
GET /api/admin/autosync/status
```

**Response:**
```json
{
  "ok": true,
  "autosync_enabled": true,
  "autosync_interval_minutes": 30,
  "tracked_folders": [
    "ProductMixRestaurantDB/",
    "daily_logs/",
    "inventory_data/",
    "Dexter Assist 6-3-26/Dexter Assistant/Inventory Control 3/data/"
  ]
}
```

### Manually Trigger Sync
```
POST /api/admin/autosync/sync-now
```

**Response:**
```json
{
  "ok": true,
  "message": "Committed and pushed 3 file(s)",
  "synced_at": "2026-06-20T12:34:56.789123",
  "files_changed": [
    "ProductMixRestaurantDB/product_mix.db",
    "daily_logs/2026-06-20_Day.csv"
  ]
}
```

## Installation & Requirements

### New Packages
The following package was added to `requirements.txt`:
- **apscheduler** - Handles background scheduling of sync jobs

Install or update your environment:
```bash
pip install -r requirements.txt
```

### Local Testing
Test the auto-sync script locally:
```bash
cd "Dexter Assistant"
python auto_sync_git.py
```

This will:
1. Detect the git repository
2. Check for uncommitted changes
3. Show which files have changed
4. Attempt to sync if changes exist

## Git Commit Messages

Auto-sync commits use descriptive messages:
```
Auto-sync: Update database files [2026-06-20 12:34:56]

Changed: ProductMixRestaurantDB/product_mix.db, daily_logs/2026-06-20_Day.csv, +1 more
```

This makes it easy to identify automatic syncs in your git history.

## Troubleshooting

### Auto-sync not working?

1. **Check if it's enabled:**
   ```
   GET /api/admin/autosync/status
   ```

2. **Verify APScheduler is installed:**
   ```bash
   pip list | grep -i apscheduler
   ```

3. **Check Dexter logs for errors:**
   - Look for `[dexter] Auto-sync` messages in server output
   - Check for any warnings about git configuration

4. **Try manual sync:**
   ```
   POST /api/admin/autosync/sync-now
   ```

5. **Verify git credentials** on Render:
   - Ensure `GITHUB_TOKEN` or SSH keys are configured
   - Verify the branch name is correct

### Performance concerns?

- Reduce sync frequency: `DEXTER_AUTOSYNC_INTERVAL_MINUTES=60`
- Disable during peak hours if needed: Set `DEXTER_AUTOSYNC_ENABLED=0`
- Re-enable when appropriate: Set `DEXTER_AUTOSYNC_ENABLED=1`

### Large database files?

If database files are very large (>50MB):
1. Check if they should be `.gitignored`
2. Consider splitting data into smaller files
3. Reduce sync frequency to avoid server load

## Manual Sync (Local Development)

On your local machine, you can still manually sync:
```bash
cd /path/to/AIO-Python
git add -A
git commit -m "Manual update: [your message]"
git push origin checkpoint/dexter-assist-20260601-173327
```

Or use the one-liner from your workflow:
```bash
git add -A && git commit -m "Update" && git push origin checkpoint/dexter-assist-20260601-173327
```

## Best Practices

1. **Monitor sync status** - Check `/api/admin/autosync/status` periodically
2. **Test manual sync** - Use `POST /api/admin/autosync/sync-now` after major uploads
3. **Review git history** - Check your repo to confirm syncs are happening
4. **Set appropriate intervals** - Balance between data safety and server load
5. **Configure on Render** - Add environment variables to Render service settings

## Files Modified

- `Dexter Assistant/auto_sync_git.py` - New auto-sync module
- `Dexter Assistant/dexter_assistant.py` - Integrated scheduler and API endpoints
- `requirements.txt` - Added APScheduler dependency
