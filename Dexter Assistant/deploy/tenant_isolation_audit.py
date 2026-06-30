from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def _rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def audit_rbac(rbac_db: Path) -> dict[str, Any]:
    if not rbac_db.exists():
        return {"exists": False, "path": str(rbac_db)}
    conn = sqlite3.connect(str(rbac_db))
    companies = _rows(
        conn,
        """
        SELECT c.id, c.name, c.slug, c.is_active,
               COALESCE(u.user_count, 0) AS user_count,
               COALESCE(m.manager_count, 0) AS manager_count
        FROM companies c
        LEFT JOIN (
            SELECT company_id, COUNT(*) AS user_count
            FROM users
            GROUP BY company_id
        ) u ON u.company_id = c.id
        LEFT JOIN (
            SELECT u.company_id, COUNT(*) AS manager_count
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE lower(r.name) = 'manager'
            GROUP BY u.company_id
        ) m ON m.company_id = c.id
        ORDER BY c.name
        """,
    )
    users_without_company = _rows(conn, "SELECT id, username FROM users WHERE company_id IS NULL ORDER BY id")
    conn.close()
    return {
        "exists": True,
        "path": str(rbac_db),
        "companies": companies,
        "users_without_company": users_without_company,
    }


def audit_manager_app(manager_db: Path, company_data_root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "db_exists": manager_db.exists(),
        "db_path": str(manager_db),
        "company_data_exists": company_data_root.exists(),
        "company_data_path": str(company_data_root),
    }

    if manager_db.exists():
        conn = sqlite3.connect(str(manager_db))
        companies = _rows(
            conn,
            """
            SELECT c.id, c.name, c.is_active,
                   COALESCE(uc.user_count, 0) AS member_count
            FROM companies c
            LEFT JOIN (
                SELECT company_id, COUNT(*) AS user_count
                FROM user_companies
                WHERE is_active = 1
                GROUP BY company_id
            ) uc ON uc.company_id = c.id
            ORDER BY c.name
            """,
        )
        dangling_memberships = _rows(
            conn,
            """
            SELECT uc.user_id, uc.company_id
            FROM user_companies uc
            LEFT JOIN companies c ON c.id = uc.company_id
            WHERE c.id IS NULL
            ORDER BY uc.user_id
            """,
        )
        conn.close()
        out["companies"] = companies
        out["dangling_memberships"] = dangling_memberships

    folders: list[dict[str, Any]] = []
    if company_data_root.exists() and company_data_root.is_dir():
        for folder in sorted([p for p in company_data_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
            file_count = sum(1 for f in folder.rglob("*") if f.is_file())
            folders.append({"folder": folder.name, "file_count": int(file_count)})
    out["company_data_folders"] = folders
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only tenant isolation audit for Dexter + Manager App")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="Dexter Assistant root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    rbac_db = root / "dexter_assistant_rbac.db"
    manager_db = root / "Manager App" / "manager_app.db"
    company_data_root = root / "Manager App" / "company_data"

    report = {
        "root": str(root),
        "rbac": audit_rbac(rbac_db),
        "manager_app": audit_manager_app(manager_db, company_data_root),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())