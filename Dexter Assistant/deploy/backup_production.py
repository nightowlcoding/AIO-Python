"""Trigger and verify a Dexter Assistant production data backup.

Authentication uses the ops token (DEXTER_OPS_BACKUP_TOKEN) that is also set on the
Render service. No user password is ever required or stored.

Usage:
    $env:DEXTER_OPS_BACKUP_TOKEN = "<token>"
    python "Dexter Assistant/deploy/backup_production.py" --mode full
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

import requests

DEFAULT_BASE_URL = "https://dexterassist.com"
RUN_PATH = "/api/ops/backups/managerapp/run"
STATUS_PATH = "/api/ops/backups/managerapp/status"


def _pretty(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a production backup on Dexter Assistant.")
    parser.add_argument("--base-url", default=os.environ.get("DEXTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--mode", choices=["critical", "full"], default="full")
    parser.add_argument("--status-only", action="store_true", help="Only report backup status.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    token = (os.environ.get("DEXTER_OPS_BACKUP_TOKEN") or "").strip()
    if not token:
        token = getpass.getpass("DEXTER_OPS_BACKUP_TOKEN: ").strip()
    if len(token) < 24:
        print("A DEXTER_OPS_BACKUP_TOKEN of at least 24 characters is required.", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "dexter-ops-backup/1.0",
            "Accept": "application/json",
            "X-Dexter-Ops-Token": token,
        }
    )

    if args.status_only:
        status = session.get(f"{base_url}{STATUS_PATH}", timeout=120)
        print(f"HTTP {status.status_code}")
        try:
            print(_pretty(status.json()))
        except ValueError:
            print(status.text[:500])
        return 0 if status.status_code == 200 else 1

    print(f"Requesting {args.mode} backup on {base_url} ...")
    run = session.post(f"{base_url}{RUN_PATH}", json={"mode": args.mode}, timeout=900)
    if run.status_code == 401:
        print("Unauthorized - the ops token does not match the value set on the server.", file=sys.stderr)
        return 2
    try:
        run_payload = run.json()
    except ValueError:
        print(f"Unexpected response ({run.status_code}): {run.text[:500]}", file=sys.stderr)
        return 1

    print(_pretty(run_payload))
    if not run_payload.get("ok"):
        print("Backup did NOT complete successfully.", file=sys.stderr)
        return 1

    operations = run_payload.get("operations", [])
    copied = [op for op in operations if op.get("copied")]
    skipped = [op for op in operations if not op.get("copied")]
    print(f"\nSnapshot: {run_payload.get('snapshot_dir')}")
    print(f"Copied {len(copied)} data sets, {len(skipped)} missing/skipped.")
    for op in skipped:
        print(f"  - missing: {op.get('type')} ({op.get('source')})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
