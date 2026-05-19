# AIO Preventive Maintenance Plan

## Goal
Make every app recoverable, portable, and isolated without deleting existing files.

## What Has Been Added
- Enclosure automation script:
  - Tools/maintenance/create_enclosed_app_folders.ps1
- Snapshot automation script:
  - Tools/maintenance/create_aio_snapshot.ps1
- Cross-platform workflow guide:
  - docs/maintenance/cross_platform_workflow.md

## How To Run Enclosure Setup
Lightweight (recommended first pass):
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/create_enclosed_app_folders.ps1

Full copy mode (copies full directory apps into enclosures):
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/create_enclosed_app_folders.ps1 -FullCopy

## How To Run Snapshot Backup
- powershell -ExecutionPolicy Bypass -File Tools/maintenance/create_aio_snapshot.ps1

## Safety Notes
- These scripts are additive.
- They do not delete or move originals.
- Existing app paths remain untouched.

## Output Locations
- App enclosures:
  - AIO_Enclosed_Apps/
- Enclosure index:
  - AIO_Enclosed_Apps/ENCLOSURE_INDEX.csv
- Snapshot zips:
  - AIO_Snapshots/
