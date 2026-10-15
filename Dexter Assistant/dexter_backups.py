"""Backup building blocks: system/company ZIP exports and off-site S3 upload."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

EXPORT_SCHEMA_VERSION = 2
SENSITIVE_COLUMN_RE = re.compile(r"(password|token|secret|salt|lockout|failed_login)", re.IGNORECASE)
SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
SKIP_SUFFIXES = {".py", ".pyc", ".pyo", "-wal", "-shm", "-journal"}
SKIP_DIR_NAMES = {"__pycache__", "templates", "static", ".venv", "venv", "node_modules", ".git", ".pytest_cache"}


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    uri = "file:" + quote(db_path.resolve().as_posix(), safe="/:") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_snapshot(src: Path, dst: Path) -> None:
    """Consistent copy of a live SQLite database."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_conn = _ro_connect(src)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _is_skipped(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(sfx) for sfx in SKIP_SUFFIXES)


class ZipManifestWriter:
    """Writes files into a ZIP and records sha256/size per entry."""

    def __init__(self, zip_path: Path, work_dir: Path):
        self.zip_path = zip_path
        self.work_dir = work_dir
        self.zf = zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True)
        self.files: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.sections: dict[str, int] = {}

    def _record(self, arcname: str, path: Path, section: str) -> None:
        self.files.append({"path": arcname, "bytes": int(path.stat().st_size), "sha256": sha256_file(path)})
        self.sections[section] = self.sections.get(section, 0) + 1

    def add_file(self, src: Path, arcname: str, section: str) -> None:
        if src.suffix.lower() in SQLITE_SUFFIXES:
            tmp = self.work_dir / f"snap_{len(self.files)}{src.suffix}"
            try:
                sqlite_snapshot(src, tmp)
                src = tmp
            except sqlite3.Error as exc:
                self.warnings.append(f"SQLite snapshot failed for {arcname}, copied raw: {exc}")
        self.zf.write(src, arcname)
        self._record(arcname, src, section)

    def add_dir(self, src_dir: Path, arc_prefix: str, section: str) -> None:
        if not src_dir.exists() or not src_dir.is_dir():
            self.warnings.append(f"{section}: folder not found ({src_dir})")
            return
        for path in sorted(src_dir.rglob("*")):
            rel_parts = path.relative_to(src_dir).parts
            if any(part in SKIP_DIR_NAMES for part in rel_parts):
                continue
            if not path.is_file() or path.is_symlink() or _is_skipped(path):
                continue
            self.add_file(path, f"{arc_prefix}/{'/'.join(rel_parts)}", section)

    def add_bytes(self, data: bytes, arcname: str, section: str) -> None:
        tmp = self.work_dir / f"blob_{len(self.files)}"
        tmp.write_bytes(data)
        self.zf.write(tmp, arcname)
        self._record(arcname, tmp, section)

    def add_rows_csv(self, columns: list[str], rows: Iterable[Iterable[Any]], arcname: str, section: str) -> int:
        tmp = self.work_dir / f"csv_{len(self.files)}.csv"
        count = 0
        # utf-8-sig so Excel opens accented names correctly.
        with tmp.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(list(row))
                count += 1
        self.zf.write(tmp, arcname)
        self._record(arcname, tmp, section)
        return count

    def add_rows_jsonl(self, columns: list[str], rows: Iterable[Iterable[Any]], arcname: str, section: str) -> int:
        tmp = self.work_dir / f"jsonl_{len(self.files)}.jsonl"
        count = 0
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                record = {
                    col: ({"__b64__": base64.b64encode(val).decode("ascii")} if isinstance(val, (bytes, bytearray)) else val)
                    for col, val in zip(columns, row)
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
        self.zf.write(tmp, arcname)
        self._record(arcname, tmp, section)
        return count

    def finish(self, manifest: dict[str, Any], readme: str) -> dict[str, Any]:
        manifest = dict(manifest)
        manifest["files"] = self.files
        manifest["sections"] = self.sections
        manifest["warnings"] = self.warnings
        self.zf.writestr("README.txt", readme)
        self.zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        self.zf.close()
        return manifest


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info([{table}])")]


def _table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    ]


def _export_query(
    writer: ZipManifestWriter,
    conn: sqlite3.Connection,
    table: str,
    where_sql: str,
    params: tuple[Any, ...],
    arc_dir: str,
    section: str,
) -> None:
    columns = [c for c in _table_columns(conn, table) if not SENSITIVE_COLUMN_RE.search(c)]
    if not columns:
        return
    col_sql = ", ".join(f"[{c}]" for c in columns)
    query = f"SELECT {col_sql} FROM [{table}] WHERE {where_sql}"
    writer.add_rows_csv(columns, (tuple(r) for r in conn.execute(query, params)), f"{arc_dir}/{table}.csv", section)
    raw_dir = "raw/" + arc_dir.split("/", 1)[1]
    writer.add_rows_jsonl(columns, (tuple(r) for r in conn.execute(query, params)), f"{raw_dir}/{table}.jsonl", section)


def _in_clause(values: list[int]) -> tuple[str, tuple[int, ...]]:
    if not values:
        return "(NULL)", ()
    return "(" + ",".join("?" for _ in values) + ")", tuple(int(v) for v in values)


def _export_dexter_rbac(writer: ZipManifestWriter, rbac_db: Path, company_id: int) -> None:
    section = "dexter_records"
    if not rbac_db.exists():
        writer.warnings.append("Dexter user/access database not found")
        return
    conn = _ro_connect(rbac_db)
    try:
        for table in _table_names(conn):
            cols = _table_columns(conn, table)
            if table == "companies":
                _export_query(writer, conn, table, "id = ?", (company_id,), "data/dexter", section)
            elif table == "users":
                where = "company_id = ? OR id IN (SELECT user_id FROM user_location_assignments WHERE company_id = ?)"
                _export_query(writer, conn, table, where, (company_id, company_id), "data/dexter", section)
            elif "company_id" in cols:
                _export_query(writer, conn, table, "company_id = ?", (company_id,), "data/dexter", section)
    finally:
        conn.close()


# Child tables that link to a restaurant through a parent table instead of a restaurant_id column.
_PM_CHILD_TABLES = {
    "production_plan_items": ("plan_id", "production_plans"),
    "restaurant_order_schedule_windows": ("schedule_id", "restaurant_order_schedules"),
}


def _export_productmix(writer: ZipManifestWriter, pm_db: Path, restaurant_ids: list[int]) -> None:
    section = "productmix"
    if not pm_db.exists():
        writer.warnings.append("ProductMix database not found")
        return
    if not restaurant_ids:
        writer.warnings.append("No ProductMix restaurants are linked to this company")
        return
    in_sql, in_params = _in_clause(restaurant_ids)
    conn = _ro_connect(pm_db)
    try:
        tables = _table_names(conn)
        for table in tables:
            cols = _table_columns(conn, table)
            if table == "restaurants":
                _export_query(writer, conn, table, f"id IN {in_sql}", in_params, "data/productmix", section)
            elif table == "users":
                where = f"restaurant_id IN {in_sql} OR id IN (SELECT user_id FROM user_restaurants WHERE restaurant_id IN {in_sql})"
                _export_query(writer, conn, table, where, in_params + in_params, "data/productmix", section)
            elif "restaurant_id" in cols:
                _export_query(writer, conn, table, f"restaurant_id IN {in_sql}", in_params, "data/productmix", section)
            elif table in _PM_CHILD_TABLES and _PM_CHILD_TABLES[table][1] in tables:
                fk, parent = _PM_CHILD_TABLES[table]
                where = f"[{fk}] IN (SELECT id FROM [{parent}] WHERE restaurant_id IN {in_sql})"
                _export_query(writer, conn, table, where, in_params, "data/productmix", section)
    finally:
        conn.close()


def manager_company_id_for_name(manager_db: Path, company_name: str) -> str | None:
    if not manager_db.exists() or not company_name.strip():
        return None
    conn = _ro_connect(manager_db)
    try:
        row = conn.execute(
            "SELECT id FROM companies WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) ORDER BY id LIMIT 1",
            (company_name,),
        ).fetchone()
        return str(row["id"]) if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _export_manager_db(writer: ZipManifestWriter, manager_db: Path, mgr_company_id: str) -> None:
    section = "manager_app_records"
    conn = _ro_connect(manager_db)
    try:
        for table in _table_names(conn):
            if table == "sessions" or table.startswith("__"):
                continue
            cols = _table_columns(conn, table)
            if table == "companies":
                _export_query(writer, conn, table, "id = ?", (mgr_company_id,), "data/manager_app", section)
            elif table == "users":
                where = "id IN (SELECT user_id FROM user_companies WHERE company_id = ?)"
                _export_query(writer, conn, table, where, (mgr_company_id,), "data/manager_app", section)
            elif "company_id" in cols:
                _export_query(writer, conn, table, "company_id = ?", (mgr_company_id,), "data/manager_app", section)
    finally:
        conn.close()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _export_ic3(writer: ZipManifestWriter, ic3_dir: Path, location_names: list[str]) -> None:
    section = "inventory"
    if not location_names:
        writer.warnings.append("No locations are linked to this company; inventory data skipped")
        return
    wanted = {name.strip().lower() for name in location_names if name.strip()}

    for filename, csv_name in (("inventory_database.json", "inventory_counts.csv"), ("orders_database.json", "orders.csv")):
        data = _load_json(ic3_dir / filename)
        if not isinstance(data, dict):
            writer.warnings.append(f"{filename} not found or unreadable")
            continue
        filtered = {loc: by_date for loc, by_date in data.items() if str(loc).strip().lower() in wanted}
        writer.add_bytes(json.dumps(filtered, indent=2).encode("utf-8"), f"raw/inventory/{filename}", section)

        def rows(source: dict[str, Any] = filtered) -> Iterable[tuple[Any, ...]]:
            for loc, by_date in source.items():
                if not isinstance(by_date, dict):
                    continue
                for day, products in sorted(by_date.items()):
                    if not isinstance(products, dict):
                        continue
                    for product, qty in products.items():
                        yield (loc, day, product, qty)

        writer.add_rows_csv(["location", "date", "product_number", "quantity"], rows(), f"data/inventory/{csv_name}", section)

    for filename in ("invoice_import_log.json", "order_price_log.json"):
        data = _load_json(ic3_dir / filename)
        if not isinstance(data, list):
            continue
        filtered_list = [e for e in data if isinstance(e, dict) and str(e.get("location") or "").strip().lower() in wanted]
        writer.add_bytes(json.dumps(filtered_list, indent=2).encode("utf-8"), f"raw/inventory/{filename}", section)


COMPANY_README = """Dexter company backup
=====================

Company: {company_name} (Dexter company #{company_id})
Created: {created_at} (UTC)

What's inside
- data/      Spreadsheet-friendly CSV files (open in Excel or Google Sheets)
  - inventory/   inventory counts and orders per location and date
  - productmix/  product mix uploads, items, production setup
  - dexter/      company profile, users (no passwords), tasks, activity log
  - manager_app/ Manager App company records, locations, activity log
- files/     Original uploaded files (daily logs, employee files, logos, ...)
- raw/       Original data in machine-readable JSON (used for restore)
- manifest.json  List of every file with a SHA-256 checksum

Passwords and login tokens are never included.
"""


def build_company_export_zip(
    *,
    dest_zip: Path,
    company: dict[str, Any],
    restaurants: list[dict[str, Any]],
    dexter_company_dir: Path,
    manager_company_data_root: Path,
    manager_db: Path,
    ic3_data_dir: Path,
    productmix_db: Path,
    rbac_db: Path,
    actor: str,
) -> dict[str, Any]:
    company_id = int(company["id"])
    company_name = str(company.get("name") or "")
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = dest_zip.with_suffix(".zip.part")
    with tempfile.TemporaryDirectory(prefix="dexter_export_") as work:
        writer = ZipManifestWriter(tmp_zip, Path(work))
        try:
            if dexter_company_dir.exists():
                writer.add_dir(dexter_company_dir, "files/dexter", "files")

            mgr_company_id = manager_company_id_for_name(manager_db, company_name)
            if mgr_company_id is None:
                writer.warnings.append("No Manager App company matches this company name; Manager App data skipped")
            else:
                mgr_dir = manager_company_data_root / str(mgr_company_id)
                if mgr_dir.exists():
                    writer.add_dir(mgr_dir, "files/manager_app", "files")
                _export_manager_db(writer, manager_db, mgr_company_id)

            _export_ic3(writer, ic3_data_dir, [str(r.get("location") or "") for r in restaurants])
            _export_productmix(writer, productmix_db, [int(r["id"]) for r in restaurants])
            _export_dexter_rbac(writer, rbac_db, company_id)

            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            manifest = writer.finish(
                {
                    "schema_version": EXPORT_SCHEMA_VERSION,
                    "kind": "company",
                    "company": {"id": company_id, "name": company_name, "slug": company.get("slug")},
                    "manager_app_company_id": mgr_company_id,
                    "restaurants": [{"id": int(r["id"]), "name": r.get("name"), "location": r.get("location")} for r in restaurants],
                    "created_at": created_at,
                    "created_by": actor,
                },
                COMPANY_README.format(company_name=company_name, company_id=company_id, created_at=created_at),
            )
        except BaseException:
            writer.zf.close()
            tmp_zip.unlink(missing_ok=True)
            raise
    tmp_zip.replace(dest_zip)
    return manifest


SYSTEM_README = """Dexter full system backup (INTERNAL - contains every company's data)
Created: {created_at} (UTC)
See manifest.json for the source path of each section and SHA-256 checksums.
"""


def build_system_export_zip(*, dest_zip: Path, sources: dict[str, Path], actor: str) -> dict[str, Any]:
    """sources maps a section name to a file or folder."""
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = dest_zip.with_suffix(".zip.part")
    with tempfile.TemporaryDirectory(prefix="dexter_sysexport_") as work:
        writer = ZipManifestWriter(tmp_zip, Path(work))
        try:
            for section, src in sources.items():
                if src.is_file():
                    writer.add_file(src, f"{section}/{src.name}", section)
                else:
                    writer.add_dir(src, section, section)
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            manifest = writer.finish(
                {
                    "schema_version": EXPORT_SCHEMA_VERSION,
                    "kind": "system",
                    "created_at": created_at,
                    "created_by": actor,
                    "sources": {k: str(v) for k, v in sources.items()},
                },
                SYSTEM_README.format(created_at=created_at),
            )
        except BaseException:
            writer.zf.close()
            tmp_zip.unlink(missing_ok=True)
            raise
    tmp_zip.replace(dest_zip)
    return manifest


def prune_local_exports(folder: Path, keep: int) -> list[str]:
    removed: list[str] = []
    zips = sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in zips[max(1, keep):]:
        try:
            old.unlink()
            removed.append(old.name)
        except OSError:
            continue
    return removed


# ---------------------------------------------------------------- restore

class RestoreError(Exception):
    pass


_MAX_RESTORE_FILES = 100_000
_PM_RESTORE_SKIP = {"users", "user_restaurants", "restaurants"}


def _restore_limit_bytes() -> int:
    return int(os.environ.get("DEXTER_RESTORE_MAX_UNCOMPRESSED_MB", "2048")) * 1024 * 1024


def _safe_member_name(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name or "\x00" in name:
        return False
    return all(part not in ("", ".", "..") for part in name.rstrip("/").split("/"))


def validate_company_zip(zip_path: Path) -> dict[str, Any]:
    """Reject unsafe, tampered or non-company archives before anything is planned."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise RestoreError("The file is not a valid ZIP archive") from exc
    with zf:
        for info in zf.infolist():
            if not _safe_member_name(info.filename):
                raise RestoreError(f"Unsafe path in backup: {info.filename!r}")
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > _MAX_RESTORE_FILES:
            raise RestoreError("Backup contains too many files")
        if sum(i.file_size for i in infos) > _restore_limit_bytes():
            raise RestoreError("Backup is too large to restore")
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except (KeyError, ValueError) as exc:
            raise RestoreError("Backup is missing a readable manifest.json") from exc
        if not isinstance(manifest, dict) or manifest.get("kind") != "company":
            raise RestoreError("This is not a company backup")
        version = int(manifest.get("schema_version") or 0)
        if version < 1 or version > EXPORT_SCHEMA_VERSION:
            raise RestoreError(f"Unsupported backup version {version}")
        listed = {str(f.get("path")): f for f in manifest.get("files") or [] if isinstance(f, dict)}
        present = {i.filename for i in infos} - {"manifest.json", "README.txt"}
        if present != set(listed):
            raise RestoreError("Backup contents do not match its manifest (files were added or removed)")
        for info in infos:
            entry = listed.get(info.filename)
            if entry is None:
                continue
            digest = hashlib.sha256()
            with zf.open(info) as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry.get("sha256"):
                raise RestoreError(f"Checksum mismatch for {info.filename}; the backup is damaged or was edited")
    return manifest


def _zip_json(zf: zipfile.ZipFile, name: str) -> Any:
    try:
        return json.loads(zf.read(name))
    except (KeyError, ValueError):
        return None


def _zip_jsonl(zf: zipfile.ZipFile, name: str) -> Iterable[dict[str, Any]]:
    with zf.open(name) as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            yield {
                k: (base64.b64decode(v["__b64__"]) if isinstance(v, dict) and "__b64__" in v else v)
                for k, v in record.items()
            }


def _contained(root: Path, rel: str) -> Path | None:
    root_resolved = root.resolve()
    candidate = (root_resolved / rel).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate


def _raw_tables(zf: zipfile.ZipFile, prefix: str) -> list[str]:
    return sorted(
        n[len(prefix):-len(".jsonl")] for n in zf.namelist() if n.startswith(prefix) and n.endswith(".jsonl") and "/" not in n[len(prefix):]
    )


def plan_company_restore(
    zip_path: Path,
    manifest: dict[str, Any],
    *,
    company_id: int,
    dexter_company_dir: Path,
    manager_company_dir: Path | None,
    manager_company_id: str | None,
    ic3_data_dir: Path,
    productmix_db: Path,
    restaurants: list[dict[str, Any]],
) -> dict[str, Any]:
    """Dry run: describe exactly what a restore would change. Nothing is written."""
    version = int(manifest.get("schema_version") or 1)
    plan: dict[str, Any] = {
        "company_id": int(company_id),
        "backup_company": manifest.get("company") or {},
        "backup_created_at": manifest.get("created_at"),
        "backup_created_by": manifest.get("created_by"),
        "schema_version": version,
        "targets": {
            "dexter_company_dir": str(dexter_company_dir),
            "manager_company_dir": str(manager_company_dir) if manager_company_dir else "",
            "manager_company_id": manager_company_id or "",
            "backup_manager_company_id": str(manifest.get("manager_app_company_id") or ""),
            "ic3_data_dir": str(ic3_data_dir),
            "productmix_db": str(productmix_db),
        },
        "file_ops": [],
        "files": {"new": 0, "changed": 0, "unchanged": 0, "skipped": 0},
        "inventory": [],
        "invoice_log_entries": 0,
        "productmix": {"restaurant_ids": [], "tables": {}},
        "dexter": {},
        "manager_app": {},
        "warnings": [],
    }
    current_locations = {str(r.get("location") or "").strip().lower() for r in restaurants if str(r.get("location") or "").strip()}

    with zipfile.ZipFile(zip_path) as zf:
        for entry in manifest.get("files") or []:
            path = str(entry.get("path"))
            if path.startswith("files/dexter/"):
                root, rel = dexter_company_dir, path[len("files/dexter/"):]
            elif path.startswith("files/manager_app/"):
                if manager_company_dir is None:
                    plan["files"]["skipped"] += 1
                    continue
                root, rel = manager_company_dir, path[len("files/manager_app/"):]
            else:
                continue
            target = _contained(root, rel)
            if target is None:
                plan["files"]["skipped"] += 1
                continue
            if target.is_file():
                status = "unchanged" if sha256_file(target) == entry.get("sha256") else "changed"
            else:
                status = "new"
            plan["files"][status] += 1
            plan["file_ops"].append({"path": path, "root": str(root), "rel": rel, "status": status})
        if plan["files"]["skipped"] and manager_company_dir is None:
            plan["warnings"].append("Manager App files skipped: no Manager App company matches this company name")

        for filename in ("inventory_database.json", "orders_database.json"):
            data = _zip_json(zf, f"raw/inventory/{filename}")
            if not isinstance(data, dict):
                continue
            for loc, by_date in data.items():
                if str(loc).strip().lower() not in current_locations:
                    plan["warnings"].append(f"Location '{loc}' is not linked to this company anymore; its {filename} data will be skipped")
                    continue
                plan["inventory"].append({"file": filename, "location": loc, "dates": len(by_date) if isinstance(by_date, dict) else 0})
        log = _zip_json(zf, "raw/inventory/invoice_import_log.json")
        if isinstance(log, list):
            plan["invoice_log_entries"] = sum(
                1 for e in log if isinstance(e, dict) and str(e.get("location") or "").strip().lower() in current_locations
            )

        if version < 2:
            plan["warnings"].append("This backup was made before database restore was supported; only files and inventory can be restored")
            return plan

        backup_restaurant_ids = {int(r["id"]) for r in manifest.get("restaurants") or [] if r.get("id") is not None}
        allowed_ids = sorted(backup_restaurant_ids & {int(r["id"]) for r in restaurants})
        if backup_restaurant_ids - set(allowed_ids):
            plan["warnings"].append("Some restaurants in the backup are no longer linked to this company; their ProductMix data will be skipped")
        plan["productmix"]["restaurant_ids"] = allowed_ids
        if allowed_ids and productmix_db.exists():
            live = _ro_connect(productmix_db)
            try:
                live_tables = set(_table_names(live))
            finally:
                live.close()
            for table in _raw_tables(zf, "raw/productmix/"):
                if table in _PM_RESTORE_SKIP or table not in live_tables:
                    continue
                plan["productmix"]["tables"][table] = sum(1 for _ in _zip_jsonl(zf, f"raw/productmix/{table}.jsonl"))

        for table in ("company_profiles", "tasks"):
            name = f"raw/dexter/{table}.jsonl"
            if name in zf.namelist():
                plan["dexter"][table] = sum(1 for _ in _zip_jsonl(zf, name))

        if manager_company_id and "raw/manager_app/locations.jsonl" in zf.namelist():
            plan["manager_app"]["locations"] = sum(1 for _ in _zip_jsonl(zf, "raw/manager_app/locations.jsonl"))
    return plan


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".restore_tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _upsert_row(conn: sqlite3.Connection, table: str, row: dict[str, Any], live_cols: set[str], exists: bool) -> None:
    cols = [c for c in row if c in live_cols]
    if exists:
        sets = ", ".join(f"[{c}] = ?" for c in cols if c != "id")
        conn.execute(f"UPDATE [{table}] SET {sets} WHERE id = ?", [row[c] for c in cols if c != "id"] + [row["id"]])
    else:
        conn.execute(
            f"INSERT INTO [{table}] ({', '.join(f'[{c}]' for c in cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [row[c] for c in cols],
        )


def _restore_files(zf: zipfile.ZipFile, plan: dict[str, Any], report: dict[str, Any]) -> None:
    for op in plan["file_ops"]:
        if op["status"] == "unchanged":
            continue
        target = _contained(Path(op["root"]), op["rel"])
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".restore_tmp")
        with zf.open(op["path"]) as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        os.replace(tmp, target)
        report["files_restored"] += 1


def _restore_ic3(zf: zipfile.ZipFile, plan: dict[str, Any], report: dict[str, Any]) -> None:
    ic3_dir = Path(plan["targets"]["ic3_data_dir"])
    allowed = {str(i["location"]).strip().lower() for i in plan["inventory"]}
    stamp = _utc_stamp()
    for filename in ("inventory_database.json", "orders_database.json"):
        backup = _zip_json(zf, f"raw/inventory/{filename}")
        if not isinstance(backup, dict) or not allowed:
            continue
        live_path = ic3_dir / filename
        live = _load_json(live_path) if live_path.exists() else {}
        if not isinstance(live, dict):
            raise RestoreError(f"Live {filename} is unreadable; restore stopped before changing it")
        key_map = {str(k).strip().lower(): k for k in live}
        restored_dates = 0
        for loc, by_date in backup.items():
            if str(loc).strip().lower() not in allowed or not isinstance(by_date, dict):
                continue
            live_key = key_map.get(str(loc).strip().lower(), loc)
            bucket = live.setdefault(live_key, {})
            for day, products in by_date.items():
                bucket[day] = products
                restored_dates += 1
        if restored_dates:
            if live_path.exists():
                shutil.copy2(live_path, live_path.with_name(f"{live_path.stem}.before_restore_{stamp}.json"))
            ic3_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(live_path, live)
        report["inventory_dates_restored"] += restored_dates

    backup_log = _zip_json(zf, "raw/inventory/invoice_import_log.json")
    log_path = ic3_dir / "invoice_import_log.json"
    if isinstance(backup_log, list) and allowed:
        live_log = _load_json(log_path) if log_path.exists() else []
        if not isinstance(live_log, list):
            raise RestoreError("Live invoice_import_log.json is unreadable; restore stopped before changing it")
        known = {e.get("import_id") for e in live_log if isinstance(e, dict)}
        added = [
            e for e in backup_log
            if isinstance(e, dict) and str(e.get("location") or "").strip().lower() in allowed and e.get("import_id") not in known
        ]
        if added:
            if log_path.exists():
                shutil.copy2(log_path, log_path.with_name(f"invoice_import_log.before_restore_{stamp}.json"))
            _atomic_write_json(log_path, live_log + added)
        report["invoice_log_entries_restored"] = len(added)


def _restore_productmix(zf: zipfile.ZipFile, plan: dict[str, Any], report: dict[str, Any]) -> None:
    allowed = set(plan["productmix"]["restaurant_ids"])
    tables = plan["productmix"]["tables"]
    if not allowed or not tables:
        return
    conn = sqlite3.connect(plan["targets"]["productmix_db"], timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Parents before children so child rows can be checked against restored parents.
        ordered = sorted(tables, key=lambda t: t in _PM_CHILD_TABLES)
        for table in ordered:
            live_cols = set(_table_columns(conn, table))
            if "id" not in live_cols:
                report["warnings"].append(f"ProductMix table {table} has no id column; skipped")
                continue
            child = _PM_CHILD_TABLES.get(table)
            restored = skipped = 0
            for row in _zip_jsonl(zf, f"raw/productmix/{table}.jsonl"):
                if "id" not in row:
                    skipped += 1
                    continue
                if child:
                    fk, parent = child
                    owner = conn.execute(f"SELECT restaurant_id FROM [{parent}] WHERE id = ?", (row.get(fk),)).fetchone()
                    if not owner or owner[0] not in allowed:
                        skipped += 1
                        continue
                    existing = conn.execute(
                        f"SELECT p.restaurant_id FROM [{table}] c LEFT JOIN [{parent}] p ON p.id = c.[{fk}] WHERE c.id = ?",
                        (row["id"],),
                    ).fetchone()
                else:
                    if row.get("restaurant_id") not in allowed:
                        skipped += 1
                        continue
                    existing = conn.execute(f"SELECT restaurant_id FROM [{table}] WHERE id = ?", (row["id"],)).fetchone()
                if existing is not None and existing[0] not in allowed:
                    # The id now belongs to another restaurant; never overwrite it.
                    skipped += 1
                    continue
                _upsert_row(conn, table, row, live_cols, exists=existing is not None)
                restored += 1
            report["productmix"][table] = {"restored": restored, "skipped": skipped}
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _restore_dexter_records(zf: zipfile.ZipFile, plan: dict[str, Any], report: dict[str, Any], rbac_conn: sqlite3.Connection) -> None:
    company_id = int(plan["company_id"])
    names = set(zf.namelist())
    if "raw/dexter/company_profiles.jsonl" in names:
        live_cols = set(_table_columns(rbac_conn, "company_profiles"))
        for row in _zip_jsonl(zf, "raw/dexter/company_profiles.jsonl"):
            if int(row.get("company_id") or 0) != company_id:
                continue
            cols = [c for c in row if c in live_cols]
            exists = rbac_conn.execute("SELECT 1 FROM company_profiles WHERE company_id = ?", (company_id,)).fetchone()
            if exists:
                sets = ", ".join(f"[{c}] = ?" for c in cols if c != "company_id")
                rbac_conn.execute(
                    f"UPDATE company_profiles SET {sets} WHERE company_id = ?",
                    [row[c] for c in cols if c != "company_id"] + [company_id],
                )
            else:
                rbac_conn.execute(
                    f"INSERT INTO company_profiles ({', '.join(f'[{c}]' for c in cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    [row[c] for c in cols],
                )
            report["dexter"]["company_profiles"] = 1
    if "raw/dexter/tasks.jsonl" in names:
        live_cols = set(_table_columns(rbac_conn, "tasks"))
        restored = skipped = 0
        for row in _zip_jsonl(zf, "raw/dexter/tasks.jsonl"):
            if int(row.get("company_id") or 0) != company_id or "id" not in row:
                skipped += 1
                continue
            existing = rbac_conn.execute("SELECT company_id FROM tasks WHERE id = ?", (row["id"],)).fetchone()
            if existing is not None and existing[0] != company_id:
                skipped += 1
                continue
            try:
                rbac_conn.execute("SAVEPOINT task_row")
                _upsert_row(rbac_conn, "tasks", row, live_cols, exists=existing is not None)
                rbac_conn.execute("RELEASE task_row")
                restored += 1
            except sqlite3.IntegrityError:
                # Usually the task's creator/assignee user no longer exists.
                rbac_conn.execute("ROLLBACK TO task_row")
                rbac_conn.execute("RELEASE task_row")
                skipped += 1
        report["dexter"]["tasks"] = {"restored": restored, "skipped": skipped}
    rbac_conn.commit()


def _restore_manager_locations(zf: zipfile.ZipFile, plan: dict[str, Any], report: dict[str, Any], manager_db: Path) -> None:
    target_cid = plan["targets"]["manager_company_id"]
    backup_cid = plan["targets"]["backup_manager_company_id"]
    if not target_cid or "raw/manager_app/locations.jsonl" not in zf.namelist() or not manager_db.exists():
        return
    conn = sqlite3.connect(manager_db, timeout=30)
    try:
        live_cols = set(_table_columns(conn, "locations"))
        added = 0
        for row in _zip_jsonl(zf, "raw/manager_app/locations.jsonl"):
            if backup_cid and str(row.get("company_id")) != backup_cid:
                continue
            row["company_id"] = target_cid
            cols = [c for c in row if c in live_cols]
            cur = conn.execute(
                f"INSERT OR IGNORE INTO locations ({', '.join(f'[{c}]' for c in cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols],
            )
            added += cur.rowcount
        conn.commit()
        report["manager_app"]["locations_added"] = added
    finally:
        conn.close()


def apply_company_restore(zip_path: Path, plan: dict[str, Any], *, rbac_conn: sqlite3.Connection, manager_db: Path) -> dict[str, Any]:
    """Merge restore: puts back everything in the backup; data added after the backup is kept."""
    report: dict[str, Any] = {
        "files_restored": 0,
        "inventory_dates_restored": 0,
        "invoice_log_entries_restored": 0,
        "productmix": {},
        "dexter": {},
        "manager_app": {},
        "warnings": list(plan.get("warnings") or []),
    }
    with zipfile.ZipFile(zip_path) as zf:
        _restore_files(zf, plan, report)
        _restore_ic3(zf, plan, report)
        if int(plan.get("schema_version") or 1) >= 2:
            _restore_productmix(zf, plan, report)
            _restore_dexter_records(zf, plan, report, rbac_conn)
            _restore_manager_locations(zf, plan, report, manager_db)
    return report


# ---------------------------------------------------------------- off-site (S3-compatible)

def offsite_config() -> dict[str, str] | None:
    bucket = (os.environ.get("DEXTER_OFFSITE_S3_BUCKET") or "").strip()
    key_id = (os.environ.get("DEXTER_OFFSITE_S3_ACCESS_KEY_ID") or "").strip()
    secret = (os.environ.get("DEXTER_OFFSITE_S3_SECRET_ACCESS_KEY") or "").strip()
    if not (bucket and key_id and secret):
        return None
    return {
        "bucket": bucket,
        "access_key_id": key_id,
        "secret_access_key": secret,
        "endpoint_url": (os.environ.get("DEXTER_OFFSITE_S3_ENDPOINT") or "").strip(),
        "region": (os.environ.get("DEXTER_OFFSITE_S3_REGION") or "").strip(),
        "prefix": (os.environ.get("DEXTER_OFFSITE_S3_PREFIX") or "dexter-backups").strip().strip("/"),
    }


def _s3_client(cfg: dict[str, str]):
    import boto3  # Imported lazily so the app still runs when off-site backup isn't configured.

    kwargs: dict[str, Any] = {
        "aws_access_key_id": cfg["access_key_id"],
        "aws_secret_access_key": cfg["secret_access_key"],
    }
    if cfg.get("endpoint_url"):
        kwargs["endpoint_url"] = cfg["endpoint_url"]
    if cfg.get("region"):
        kwargs["region_name"] = cfg["region"]
    return boto3.client("s3", **kwargs)


_SYSTEM_KEY_RE = re.compile(r"system_(\d{8}T\d{6}Z)\.zip$")


def select_retention(stamps: list[datetime], daily: int, weekly: int, monthly: int) -> set[datetime]:
    """Grandfather-father-son: newest per day/ISO week/month, up to the given counts."""
    keep: set[datetime] = set()
    ordered = sorted(stamps, reverse=True)
    for limit, bucket in (
        (daily, lambda d: d.date()),
        (weekly, lambda d: d.isocalendar()[:2]),
        (monthly, lambda d: (d.year, d.month)),
    ):
        seen: set[Any] = set()
        for stamp in ordered:
            key = bucket(stamp)
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > limit:
                break
            keep.add(stamp)
    return keep


def upload_offsite_and_prune(cfg: dict[str, str], zip_path: Path, stamp: str) -> dict[str, Any]:
    client = _s3_client(cfg)
    key = f"{cfg['prefix']}/system/system_{stamp}.zip"
    client.upload_file(str(zip_path), cfg["bucket"], key)

    existing: dict[datetime, str] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=cfg["bucket"], Prefix=f"{cfg['prefix']}/system/"):
        for obj in page.get("Contents", []) or []:
            match = _SYSTEM_KEY_RE.search(str(obj.get("Key", "")))
            if match:
                existing[datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")] = str(obj["Key"])

    keep = select_retention(
        list(existing),
        daily=int(os.environ.get("DEXTER_OFFSITE_KEEP_DAILY", "14")),
        weekly=int(os.environ.get("DEXTER_OFFSITE_KEEP_WEEKLY", "8")),
        monthly=int(os.environ.get("DEXTER_OFFSITE_KEEP_MONTHLY", "12")),
    )
    pruned = [k for stamp_dt, k in existing.items() if stamp_dt not in keep and k != key]
    for old_key in pruned:
        client.delete_object(Bucket=cfg["bucket"], Key=old_key)
    return {"key": key, "bucket": cfg["bucket"], "pruned": pruned, "kept": len(existing) - len(pruned)}


def run_offsite_backup(sources: dict[str, Path], actor: str) -> dict[str, Any]:
    cfg = offsite_config()
    if cfg is None:
        return {"ok": False, "message": "Off-site backup is not configured"}
    stamp = _utc_stamp()
    work_dir = Path(tempfile.mkdtemp(prefix="dexter_offsite_"))
    zip_path = work_dir / f"system_{stamp}.zip"
    try:
        manifest = build_system_export_zip(dest_zip=zip_path, sources=sources, actor=actor)
        upload = upload_offsite_and_prune(cfg, zip_path, stamp)
        return {
            "ok": True,
            "message": "Off-site backup uploaded",
            "bytes": int(zip_path.stat().st_size),
            "file_count": len(manifest["files"]),
            "warnings": manifest["warnings"],
            **upload,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
