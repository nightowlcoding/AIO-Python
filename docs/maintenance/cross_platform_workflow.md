# Cross-Platform Workflow (Mac, Windows, Linux)

## Core Rule
- Keep one canonical repo and sync through Git, not manual folder copying.

## Recommended Setup
- Use the same folder name on each machine, for example: AIO-Python.
- Keep one branch policy:
  - main for stable code
  - feature branches per task
- Use one Python version family across machines (for example 3.11.x or 3.12.x).

## Environment Standard
- Do not commit virtual environments.
- Create a local venv on each machine.
- Install dependencies from requirements.txt (or per-app requirements file).

Windows:
- py -3 -m venv .venv
- .\.venv\Scripts\activate
- pip install -r requirements.txt

Mac/Linux:
- python3 -m venv .venv
- source .venv/bin/activate
- pip install -r requirements.txt

## App Isolation Standard
- Each app gets its own folder with at least:
  - source
  - data
  - config
  - logs
  - backups
  - docs
  - scripts
- Shared assets can stay in shared top-level folders, but each app folder should have a manifest pointing to what it uses.

## Data Safety Standard
- Keep runtime data files under each app's data folder.
- Run daily snapshots to zip backups.
- Before major edits or merges, create a snapshot first.

## Operational Rules
- No deletes during maintenance without a separate explicit approval step.
- Prefer additive changes: copy, archive, then refactor.
- Keep restore notes in docs/maintenance after every incident.

## Multi-Computer Daily Routine
1. Pull latest changes.
2. Activate local virtual environment.
3. Run app checks/tests.
4. Work on feature branch.
5. Commit and push.
6. Pull on next machine before continuing.

## Optional Improvements
- Add pre-commit hooks for lint/format.
- Add CI checks for syntax and smoke tests.
- Use a dependency lock strategy per app for reproducibility.
