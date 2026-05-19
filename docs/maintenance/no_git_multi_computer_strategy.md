# No-Git Multi-Computer Strategy (OneDrive, Google Drive, NAS)

## Your Requirement
- No Git.
- Keep all files safe.
- Work across Windows, Mac, Linux.
- No deletes during cleanup.

## Recommended Order (Best to Worst)
1. NAS as primary shared storage (best control and speed at home)
2. OneDrive as cloud backup and off-site safety
3. Google Drive as additional off-site backup or secondary sync

## Critical Rule to Avoid File Conflicts
- Only one machine edits the same app folder at a time.
- Before switching devices:
  - wait for sync to fully complete
  - then open on the next machine

## Folder Pattern Per App
Each app should have:
- source
- data
- config
- logs
- backups
- docs
- scripts

## Daily Workflow (No Git)
1. Start on machine A:
   - wait for cloud/NAS sync to finish
   - run app
2. Before stopping on machine A:
   - run snapshot script
   - verify sync completed
3. Move to machine B:
   - wait for sync completed
   - run app checks

## Scripts You Now Have
- Enclosure generator:
  - Tools/maintenance/create_enclosed_app_folders.ps1
- Snapshot creator:
  - Tools/maintenance/create_aio_snapshot.ps1
- Tidy runner:
  - Tools/maintenance/tidy_up_aio.ps1
- Sync bundle exporter:
  - Tools/maintenance/sync_to_storage_target.ps1

## Example Commands
Create a fresh snapshot:
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/create_aio_snapshot.ps1

Run tidy pass (copy-only):
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/tidy_up_aio.ps1

Create OneDrive bundle:
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/sync_to_storage_target.ps1 -TargetPath "C:\Users\arnol\OneDrive" -TargetType OneDrive

Create NAS bundle (example):
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/sync_to_storage_target.ps1 -TargetPath "\\NAS\Projects" -TargetType NAS

## Safety Policy
- No automated delete step.
- Always copy first.
- Keep dated snapshots in AIO_Snapshots.
- Keep tidy run outputs in AIO_Tidy.
