from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_count_query(db_path: Path, query: str) -> int | None:
    if not db_path.exists() or not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        value = conn.execute(query).fetchone()[0]
        conn.close()
        return int(value)
    except Exception:
        return None


def collect_integrity(source_root: Path) -> dict[str, Any]:
    auth_users_path = source_root / "dexter_assistant_users.json"
    rbac_db_path = source_root / "dexter_assistant_rbac.db"
    manager_db_path = source_root / "Manager App" / "manager_app.db"
    manager_company_data = source_root / "Manager App" / "company_data"
    ic3_data_path = source_root / "Inventory Control 3" / "data"

    auth_users_count = None
    if auth_users_path.exists() and auth_users_path.is_file():
        try:
            payload = json.loads(auth_users_path.read_text(encoding="utf-8"))
            auth_users_count = len(payload.get("users", []))
        except Exception:
            auth_users_count = None

    manager_company_files = 0
    if manager_company_data.exists() and manager_company_data.is_dir():
        manager_company_files = sum(1 for p in manager_company_data.rglob("*") if p.is_file())

    ic3_files = 0
    if ic3_data_path.exists() and ic3_data_path.is_dir():
        ic3_files = sum(1 for p in ic3_data_path.rglob("*") if p.is_file())

    return {
        "captured_at": datetime.utcnow().isoformat(),
        "paths": {
            "auth_users": str(auth_users_path),
            "rbac_db": str(rbac_db_path),
            "manager_db": str(manager_db_path),
            "manager_company_data": str(manager_company_data),
            "ic3_data": str(ic3_data_path),
        },
        "counts": {
            "auth_users_json_users": auth_users_count,
            "rbac_users": _safe_count_query(rbac_db_path, "SELECT COUNT(*) FROM users"),
            "rbac_managers": _safe_count_query(
                rbac_db_path,
                "SELECT COUNT(*) FROM users u JOIN roles r ON r.id = u.role_id WHERE lower(r.name) = 'manager'",
            ),
            "manager_employees": _safe_count_query(manager_db_path, "SELECT COUNT(*) FROM employees"),
            "manager_company_data_files": manager_company_files,
            "ic3_data_files": ic3_files,
        },
    }


def run_snapshot(source_root: Path, out_root: Path) -> int:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    snapshot_root = out_root / f"snapshot_{stamp}"
    snapshot_root.mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        source_root / "dexter_assistant_users.json",
        source_root / "dexter_assistant_rbac.db",
        source_root / "Manager App" / "manager_app.db",
    ]
    dirs_to_copy = [
        source_root / "Manager App" / "company_data",
        source_root / "Inventory Control 3" / "data",
    ]

    copied_files: list[dict[str, Any]] = []
    copied_dirs: list[dict[str, Any]] = []

    for src in files_to_copy:
        rel = str(src.relative_to(source_root))
        if src.exists() and src.is_file():
            dst = snapshot_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied_files.append(
                {
                    "path": rel,
                    "exists": True,
                    "bytes": int(dst.stat().st_size),
                    "sha256": _sha256(dst),
                }
            )
        else:
            copied_files.append({"path": rel, "exists": False})

    for src in dirs_to_copy:
        rel = str(src.relative_to(source_root))
        if src.exists() and src.is_dir():
            dst = snapshot_root / rel
            shutil.copytree(src, dst, dirs_exist_ok=True)
            file_count = sum(1 for p in dst.rglob("*") if p.is_file())
            copied_dirs.append({"path": rel, "exists": True, "file_count": int(file_count)})
        else:
            copied_dirs.append({"path": rel, "exists": False, "file_count": 0})

    integrity = collect_integrity(source_root)
    manifest = {
        "created_at": datetime.utcnow().isoformat(),
        "source_root": str(source_root),
        "snapshot_root": str(snapshot_root),
        "files": copied_files,
        "directories": copied_dirs,
        "integrity": integrity,
    }

    manifest_path = snapshot_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(str(manifest_path))
    return 0


def run_check(source_root: Path, baseline_manifest: Path, strict: bool) -> int:
    if not baseline_manifest.exists() or not baseline_manifest.is_file():
        print(f"Baseline manifest not found: {baseline_manifest}", file=sys.stderr)
        return 2

    baseline_payload = json.loads(baseline_manifest.read_text(encoding="utf-8"))
    baseline_counts = (baseline_payload.get("integrity") or {}).get("counts") or {}
    current_counts = collect_integrity(source_root).get("counts") or {}

    keys = sorted(set(baseline_counts.keys()) | set(current_counts.keys()))
    mismatches: list[dict[str, Any]] = []
    for key in keys:
        before = baseline_counts.get(key)
        after = current_counts.get(key)
        if before != after:
            mismatches.append({"metric": key, "before": before, "after": after})

    report = {
        "source_root": str(source_root),
        "baseline_manifest": str(baseline_manifest),
        "checked_at": datetime.utcnow().isoformat(),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "baseline_counts": baseline_counts,
        "current_counts": current_counts,
    }
    print(json.dumps(report, indent=2))

    if strict and mismatches:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dexter pre-deploy snapshot and post-deploy integrity checks")
    parser.add_argument(
        "--source-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Dexter Assistant project root",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Create a local snapshot + integrity manifest")
    snapshot_parser.add_argument(
        "--out-root",
        default=str(Path(__file__).resolve().parent / "snapshots"),
        help="Where snapshot directories are created",
    )

    check_parser = subparsers.add_parser("check", help="Compare current integrity counts against a baseline manifest")
    check_parser.add_argument("--baseline", required=True, help="Path to baseline manifest.json")
    check_parser.add_argument("--strict", action="store_true", help="Exit with code 1 when mismatches are detected")

    args = parser.parse_args()
    source_root = Path(args.source_root).resolve()

    if args.command == "snapshot":
        out_root = Path(args.out_root).resolve()
        return run_snapshot(source_root, out_root)

    if args.command == "check":
        baseline = Path(args.baseline).resolve()
        return run_check(source_root, baseline, bool(args.strict))

    return 2


if __name__ == "__main__":
    raise SystemExit(main())