# Scheduled Backup Tasks

## What Is Automated
- Fresh snapshot creation
- OneDrive sync bundle export
- Google Drive sync bundle export

## Master Script
- Tools/maintenance/run_all_cloud_backups.ps1

## Recommended Schedule
- Daily at 2:00 AM
- Every 4 hours while the machine is on
- At user logon

## Logs
- Tools/maintenance/logs/

## Notes
- These tasks are additive and copy-only.
- No original files are deleted or moved.
- If Google Drive is not mounted, that step is skipped and logged.
- If OneDrive is unavailable, that step is skipped and logged.
