from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


RUNTIME_DATA_PREFIXES = [
    "Dexter Assistant/dexter_assistant_rbac.db",
    "Dexter Assistant/Manager App/manager_app.db",
    "Dexter Assistant/ProductMixRestaurantDB/product_mix.db",
    "Dexter Assistant/Manager App/company_data/",
    "Dexter Assistant/Inventory Control 3/data/",
    "Dexter Assistant/inventory_data/",
    "Dexter Assistant/daily_logs/",
    "Dexter Assistant/uploads/",
    "Dexter Assistant/OrderInvoices/",
    "Dexter Assistant/reports/",
    "Dexter Assistant/deploy/snapshots/",
]


def _git_status(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to run git status")
    return [line.rstrip("\n") for line in result.stdout.splitlines() if line.strip()]


def _extract_path(line: str) -> str:
    payload = line[3:] if len(line) > 3 else ""
    if " -> " in payload:
        value = payload.split(" -> ", 1)[1].strip()
    else:
        value = payload.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return value


def _is_runtime_data_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in RUNTIME_DATA_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Block release when runtime data files are dirty")
    parser.add_argument("--repo-root", required=True, help="Path to AIO-Python repo root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    lines = _git_status(repo_root)

    risky: list[dict[str, str]] = []
    safe: list[dict[str, str]] = []
    for line in lines:
        path = _extract_path(line)
        record = {"status": line[:2], "path": path}
        if _is_runtime_data_path(path):
            risky.append(record)
        else:
            safe.append(record)

    payload = {
        "repo_root": str(repo_root),
        "ok": len(risky) == 0,
        "risky_changes": risky,
        "other_changes": safe,
    }
    print(json.dumps(payload, indent=2))

    if risky:
        print("\nRelease preflight failed: runtime data changes detected.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
