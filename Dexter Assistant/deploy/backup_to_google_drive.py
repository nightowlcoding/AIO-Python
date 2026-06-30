from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


DEFAULT_GDRIVE_FOLDER_ID = "1hDgvPFXlYeIWc9t9ah-CZgx3klahRYAQ"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _service_account_file(explicit: str | None) -> Path:
    raw = (explicit or _env("DEXTER_GDRIVE_SERVICE_ACCOUNT_FILE")).strip()
    if not raw:
        raise SystemExit("Missing Google Drive service account file. Set DEXTER_GDRIVE_SERVICE_ACCOUNT_FILE.")
    path = Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Google Drive service account file not found: {path}")
    return path


def _drive_service(credentials_file: Path):
    creds = service_account.Credentials.from_service_account_file(str(credentials_file), scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _guess_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def _create_folder(service, name: str, parent_id: str) -> str:
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=body, fields="id").execute()
    return str(created["id"])


def _upload_file(service, local_path: Path, parent_id: str) -> dict[str, Any]:
    media = MediaFileUpload(str(local_path), mimetype=_guess_mime_type(local_path), resumable=True)
    body = {"name": local_path.name, "parents": [parent_id]}
    created = service.files().create(body=body, media_body=media, fields="id,name,size,modifiedTime").execute()
    return {
        "name": local_path.name,
        "id": created.get("id"),
        "size": created.get("size"),
        "modifiedTime": created.get("modifiedTime"),
    }


def _upload_tree(service, local_root: Path, drive_parent_id: str) -> dict[str, Any]:
    folder_map: dict[Path, str] = {local_root: drive_parent_id}
    uploaded_files: list[dict[str, Any]] = []
    created_folders: list[dict[str, Any]] = []

    for path in sorted(local_root.rglob("*"), key=lambda p: (p.is_file(), str(p))):
        rel_parent = path.parent
        if path.is_dir():
            parent_drive_id = folder_map.get(rel_parent)
            if not parent_drive_id:
                continue
            drive_folder_id = _create_folder(service, path.name, parent_drive_id)
            folder_map[path] = drive_folder_id
            created_folders.append({"path": str(path.relative_to(local_root)), "id": drive_folder_id})
            continue

        parent_drive_id = folder_map.get(rel_parent)
        if not parent_drive_id:
            continue
        uploaded_files.append(_upload_file(service, path, parent_drive_id))

    return {"folders": created_folders, "files": uploaded_files}


def _list_child_folders(service, parent_id: str) -> list[dict[str, Any]]:
    response = service.files().list(
        q=(
            f"'{parent_id}' in parents and trashed = false and "
            "mimeType = 'application/vnd.google-apps.folder'"
        ),
        fields="files(id,name,modifiedTime)",
        pageSize=1000,
    ).execute()
    return list(response.get("files", []))


def _delete_folder_recursive(service, folder_id: str) -> None:
    children = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id,mimeType)",
        pageSize=1000,
    ).execute().get("files", [])
    for child in children:
        if child.get("mimeType") == "application/vnd.google-apps.folder":
            _delete_folder_recursive(service, child["id"])
        else:
            service.files().delete(fileId=child["id"]).execute()
    service.files().delete(fileId=folder_id).execute()


def _snapshot_timestamp_from_name(name: str) -> datetime | None:
    match = re.search(r"snapshot_(\d{8})_(\d{6})", name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _prune_old_snapshots(service, parent_id: str, retention_days: int) -> list[str]:
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    pruned: list[str] = []
    for folder in _list_child_folders(service, parent_id):
        snapshot_time = _snapshot_timestamp_from_name(str(folder.get("name") or ""))
        if snapshot_time and snapshot_time < cutoff:
            _delete_folder_recursive(service, str(folder["id"]))
            pruned.append(str(folder.get("name") or folder["id"]))
    return pruned


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a Dexter snapshot folder to Google Drive")
    parser.add_argument("--source-dir", required=True, help="Local snapshot folder to upload")
    parser.add_argument("--folder-id", default=_env("DEXTER_GDRIVE_FOLDER_ID") or DEFAULT_GDRIVE_FOLDER_ID)
    parser.add_argument("--credentials", default=_env("DEXTER_GDRIVE_SERVICE_ACCOUNT_FILE"))
    parser.add_argument("--retention-days", type=int, default=int(_env("DEXTER_GDRIVE_RETENTION_DAYS") or "15"))

    args = parser.parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"Source snapshot folder not found: {source_dir}", file=sys.stderr)
        return 2

    credentials_file = _service_account_file(args.credentials)
    service = _drive_service(credentials_file)

    remote_name = source_dir.name
    parent_id = str(args.folder_id).strip()
    if not parent_id:
        print("Missing Google Drive folder ID.", file=sys.stderr)
        return 2

    remote_folder_id = _create_folder(service, remote_name, parent_id)
    upload_result = _upload_tree(service, source_dir, remote_folder_id)
    pruned = _prune_old_snapshots(service, parent_id, max(1, int(args.retention_days)))

    summary = {
        "ok": True,
        "source_dir": str(source_dir),
        "remote_folder_name": remote_name,
        "remote_folder_id": remote_folder_id,
        "uploaded_folders": len(upload_result["folders"]),
        "uploaded_files": len(upload_result["files"]),
        "pruned": pruned,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())