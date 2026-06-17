# --- Place at the very end of the file, after all other routes and logic ---

from __future__ import annotations

import csv
import json
import inspect
import os
import re
import sqlite3
import socket
import smtplib
import secrets
import ssl
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

import requests
from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "dexter_assistant_config.json"
RUNTIME_LOG_DIR = ROOT / "runtime_logs"
FRONT_DOOR_FAVICON = ROOT / "favicon.svg"
BRANDING_LOGO_PATH = ROOT / "dexter_logo.png"
LEGACY_BRANDING_LOGO_PATH = ROOT.parent / "Restaurant Management" / "Manager App" / "static" / "img" / "Dexter.png"
AUTH_USERS_PATH = ROOT / "dexter_assistant_users.json"
RBAC_DB_PATH = ROOT / "dexter_assistant_rbac.db"
COMPANY_STORAGE_ROOT = ROOT.parent / "company_data"
SESSION_USER_KEY = "dexter_user"
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15
MAX_COMPANY_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_COMPANY_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


RBAC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK (name IN ('Super Admin', 'Manager', 'Employee')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    company_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    last_failed_login TEXT,
    lockout_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS user_location_assignments (
    user_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    restaurant_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, company_id, restaurant_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in-progress', 'completed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    created_by INTEGER NOT NULL,
    assigned_to INTEGER,
    company_id INTEGER,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (assigned_to) REFERENCES users(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id INTEGER,
    company_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (actor_user_id) REFERENCES users(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS migration_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_profiles (
    company_id INTEGER PRIMARY KEY,
    contact_email TEXT,
    email_enabled INTEGER NOT NULL DEFAULT 1,
    email_from_name TEXT,
    email_reply_to TEXT,
    daily_log_email_enabled INTEGER NOT NULL DEFAULT 0,
    daily_log_email_recipients TEXT,
    daily_log_email_time TEXT,
    daily_log_email_last_sent_for TEXT,
    contact_phone TEXT,
    website TEXT,
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    state_region TEXT,
    postal_code TEXT,
    country TEXT,
    tax_id TEXT,
    notes TEXT,
    logo_rel_path TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_user_location_assignments_company_id ON user_location_assignments(company_id);
CREATE INDEX IF NOT EXISTS idx_user_location_assignments_restaurant_id ON user_location_assignments(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at DESC);
"""

def get_rbac_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(RBAC_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def seed_default_roles(conn: sqlite3.Connection) -> None:
    for role_name in ("Super Admin", "Manager", "Employee"):
        conn.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role_name,))

def _slugify_company_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return base or "company"

def ensure_default_company(conn: sqlite3.Connection) -> int:
    default_name = "Default Company"
    row = conn.execute("SELECT id FROM companies WHERE name = ? LIMIT 1", (default_name,)).fetchone()
    if row:
        return int(row["id"])

    slug_base = _slugify_company_name(default_name)
    slug = slug_base
    suffix = 1
    while conn.execute("SELECT 1 FROM companies WHERE slug = ? LIMIT 1", (slug,)).fetchone():
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    cur = conn.execute(
        """
        INSERT INTO companies (name, slug, is_active, created_at, updated_at)
        VALUES (?, ?, 1, datetime('now'), datetime('now'))
        """,
        (default_name, slug),
    )
    return int(cur.lastrowid)

def initialize_rbac_db() -> None:
    conn = get_rbac_db_connection()
    try:
        conn.executescript(RBAC_SCHEMA_SQL)
        seed_default_roles(conn)
        conn.commit()
    finally:
        conn.close()

def _get_role_id(conn: sqlite3.Connection, role_name: str) -> int:
    row = conn.execute("SELECT id FROM roles WHERE name = ? LIMIT 1", (role_name,)).fetchone()
    if not row:
        raise ValueError(f"Unknown role: {role_name}")
    return int(row["id"])

def _get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT u.id, u.username, u.password_hash, u.is_active, u.last_login,
               u.company_id, c.name AS company_name, r.name AS role_name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE LOWER(u.username) = LOWER(?)
        LIMIT 1
        """,
        (username,),
    ).fetchone()

def _mark_migration_complete(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        """
        INSERT INTO migration_meta (key, value, updated_at)
        VALUES (?, '1', datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key,),
    )

def _is_migration_complete(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT value FROM migration_meta WHERE key = ? LIMIT 1", (key,)).fetchone()
    return bool(row and str(row["value"]) == "1")

def migrate_legacy_json_users_to_sqlite() -> None:
    migration_key = "json_users_migrated_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return

        users = load_auth_users()
        for username, payload in users.items():
            if not isinstance(payload, dict):
                continue

            normalized_username = str(username or "").strip()
            password_hash = str(payload.get("password_hash") or "").strip()
            if not normalized_username or not password_hash:
                continue

            role_name = "Super Admin" if bool(payload.get("is_admin", False)) else "Employee"
            role_id = _get_role_id(conn, role_name)
            created_at = payload.get("created_at") or datetime.now().isoformat(timespec="seconds")
            last_login = payload.get("last_login")

            existing = _get_user_by_username(conn, normalized_username)
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?,
                        role_id = ?,
                        is_active = 1,
                        updated_at = datetime('now'),
                        last_login = COALESCE(?, last_login)
                    WHERE id = ?
                    """,
                    (password_hash, role_id, last_login, int(existing["id"])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, is_active, created_at, updated_at, last_login)
                    VALUES (?, ?, ?, 1, ?, datetime('now'), ?)
                    """,
                    (normalized_username, password_hash, role_id, created_at, last_login),
                )

        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_task_fields_v1() -> None:
    migration_key = "tasks_due_date_priority_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")
        except Exception:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")
        except Exception:
            pass  # column already exists
        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_password_reset_fields_v1() -> None:
    migration_key = "users_password_reset_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return
        try:
            conn.execute("ALTER TABLE users ADD COLUMN password_reset_token TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN password_reset_expires TEXT")
        except Exception:
            pass
        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_company_scope_v1() -> None:
    migration_key = "company_scope_v1"
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        if _is_migration_complete(conn, migration_key):
            return

        try:
            conn.execute("ALTER TABLE users ADD COLUMN company_id INTEGER")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN company_id INTEGER")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN company_id INTEGER")
        except Exception:
            pass

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_company_id ON tasks(company_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_company_id ON audit_logs(company_id)")

        default_company_id = ensure_default_company(conn)
        conn.execute("UPDATE users SET company_id = ? WHERE company_id IS NULL", (default_company_id,))
        conn.execute("UPDATE tasks SET company_id = ? WHERE company_id IS NULL", (default_company_id,))
        conn.execute("UPDATE audit_logs SET company_id = ? WHERE company_id IS NULL", (default_company_id,))

        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_login_lockout_fields_v1() -> None:
    migration_key = "users_login_lockout_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return
        try:
            conn.execute("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN last_failed_login TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN lockout_until TEXT")
        except Exception:
            pass
        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_company_profiles_v1() -> None:
    migration_key = "company_profiles_v1"
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_profiles (
                company_id INTEGER PRIMARY KEY,
                contact_email TEXT,
                email_enabled INTEGER NOT NULL DEFAULT 1,
                email_from_name TEXT,
                email_reply_to TEXT,
                daily_log_email_enabled INTEGER NOT NULL DEFAULT 0,
                daily_log_email_recipients TEXT,
                daily_log_email_time TEXT,
                daily_log_email_last_sent_for TEXT,
                contact_phone TEXT,
                website TEXT,
                address_line1 TEXT,
                address_line2 TEXT,
                city TEXT,
                state_region TEXT,
                postal_code TEXT,
                country TEXT,
                tax_id TEXT,
                notes TEXT,
                logo_rel_path TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
            """
        )

        if _is_migration_complete(conn, migration_key):
            return

        conn.execute(
            """
            INSERT INTO company_profiles (company_id, updated_at)
            SELECT c.id, datetime('now')
            FROM companies c
            LEFT JOIN company_profiles cp ON cp.company_id = c.id
            WHERE cp.company_id IS NULL
            """
        )

        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_company_email_settings_v1() -> None:
    migration_key = "company_email_settings_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN email_enabled INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN email_from_name TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN email_reply_to TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN daily_log_email_enabled INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN daily_log_email_recipients TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN daily_log_email_time TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE company_profiles ADD COLUMN daily_log_email_last_sent_for TEXT")
        except Exception:
            pass
        conn.execute("UPDATE company_profiles SET email_enabled = COALESCE(email_enabled, 1)")
        conn.execute("UPDATE company_profiles SET daily_log_email_enabled = COALESCE(daily_log_email_enabled, 0)")
        conn.execute("UPDATE company_profiles SET daily_log_email_time = COALESCE(NULLIF(TRIM(daily_log_email_time), ''), '01:00')")
        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def migrate_add_user_location_assignments_v1() -> None:
    migration_key = "user_location_assignments_v1"
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_location_assignments (
                user_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                restaurant_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, company_id, restaurant_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_location_assignments_company_id ON user_location_assignments(company_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_location_assignments_restaurant_id ON user_location_assignments(restaurant_id)")

        if _is_migration_complete(conn, migration_key):
            return

        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()

def ensure_default_super_admin_user() -> None:
    admin_username = os.environ.get("DEXTER_ADMIN_USER", "").strip()
    admin_password = os.environ.get("DEXTER_ADMIN_PASS", "").strip()
    if not admin_username or not admin_password:
        return

    conn = get_rbac_db_connection()
    try:
        default_company_id = ensure_default_company(conn)
        role_id = _get_role_id(conn, "Super Admin")
        existing = _get_user_by_username(conn, admin_username)
        if existing:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, role_id = ?, is_active = 1,
                    company_id = COALESCE(company_id, ?), updated_at = datetime('now')
                WHERE id = ?
                """,
                (generate_password_hash(admin_password), role_id, default_company_id, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role_id, company_id, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'))
                """,
                (admin_username, generate_password_hash(admin_password), role_id, default_company_id),
            )
        conn.commit()
    finally:
        conn.close()

def find_auth_user(identifier: str) -> tuple[str | None, dict[str, Any] | None]:
    normalized = str(identifier or "").strip()
    if not normalized:
        return None, None

    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
             SELECT u.id, u.username, u.password_hash, u.is_active, u.last_login,
                 u.failed_login_attempts, u.last_failed_login, u.lockout_until,
                   u.company_id, c.name AS company_name, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN companies c ON c.id = u.company_id
            WHERE LOWER(u.username) = LOWER(?)
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        if not row:
            return None, None
        return str(row["username"]), dict(row)
    finally:
        conn.close()

def update_user_last_login(user_id: int) -> None:
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET last_login = datetime('now'),
                failed_login_attempts = 0,
                last_failed_login = NULL,
                lockout_until = NULL,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (int(user_id),),
        )
        conn.commit()
    finally:
        conn.close()

def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None

def is_user_locked_out(user: dict[str, Any]) -> bool:
    lockout_dt = _parse_iso_datetime(user.get("lockout_until"))
    return bool(lockout_dt and datetime.now() < lockout_dt)

def register_failed_login_attempt(user_id: int) -> tuple[int, datetime | None]:
    now = datetime.now()
    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            "SELECT failed_login_attempts FROM users WHERE id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        current_attempts = int(row["failed_login_attempts"] if row and row["failed_login_attempts"] is not None else 0)
        next_attempts = current_attempts + 1

        lockout_until: datetime | None = None
        lockout_text: str | None = None
        if next_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            lockout_until = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            lockout_text = lockout_until.isoformat(timespec="seconds")

        conn.execute(
            """
            UPDATE users
            SET failed_login_attempts = ?,
                last_failed_login = ?,
                lockout_until = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (next_attempts, now.isoformat(timespec="seconds"), lockout_text, int(user_id)),
        )
        conn.commit()
        return next_attempts, lockout_until
    finally:
        conn.close()

def current_user_id() -> int | None:
    raw_id = (session.get(SESSION_USER_KEY) or {}).get("user_id")
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None

def current_user_company_id() -> int | None:
    raw_company_id = (session.get(SESSION_USER_KEY) or {}).get("company_id")
    if raw_company_id is None:
        return None
    try:
        return int(raw_company_id)
    except (TypeError, ValueError):
        return None

def current_selected_company_id() -> int | None:
    raw_selected_company_id = (session.get(SESSION_USER_KEY) or {}).get("selected_company_id")
    if raw_selected_company_id is None:
        return None
    try:
        return int(raw_selected_company_id)
    except (TypeError, ValueError):
        return None

def current_selected_restaurant_id() -> int | None:
    raw_selected_restaurant_id = (session.get(SESSION_USER_KEY) or {}).get("selected_restaurant_id")
    normalized = _normalize_proxy_location_id(raw_selected_restaurant_id)
    if normalized is None:
        return None
    return int(normalized)

def _set_session_selected_restaurant_context(restaurant_id: int | None) -> None:
    user = session.get(SESSION_USER_KEY) or {}
    if not user:
        return
    user["selected_restaurant_id"] = int(restaurant_id) if restaurant_id is not None else None
    session[SESSION_USER_KEY] = user
    session.modified = True

def _set_session_company_context(company_id: int | None, company_name: str | None = None) -> None:
    user = session.get(SESSION_USER_KEY) or {}
    if not user:
        return
    previous_company_id = _normalize_company_id(user.get("selected_company_id"))
    next_company_id = _normalize_company_id(company_id)
    if previous_company_id != next_company_id:
        user["selected_restaurant_id"] = None
    user["selected_company_id"] = int(company_id) if company_id is not None else None
    if company_id is not None:
        user["company_id"] = int(company_id)
    if company_name is not None:
        user["company_name"] = str(company_name)
    session[SESSION_USER_KEY] = user
    session.modified = True

def _get_company_by_id(company_id: int, require_active: bool = False) -> sqlite3.Row | None:
    conn = get_rbac_db_connection()
    try:
        if require_active:
            return conn.execute(
                "SELECT id, name, slug, is_active FROM companies WHERE id = ? AND is_active = 1 LIMIT 1",
                (int(company_id),),
            ).fetchone()
        return conn.execute(
            "SELECT id, name, slug, is_active FROM companies WHERE id = ? LIMIT 1",
            (int(company_id),),
        ).fetchone()
    finally:
        conn.close()

def _company_id_for_user(user_id: int) -> int | None:
    conn = get_rbac_db_connection()
    try:
        row = conn.execute("SELECT company_id FROM users WHERE id = ? LIMIT 1", (int(user_id),)).fetchone()
        if not row or row["company_id"] is None:
            return None
        return int(row["company_id"])
    finally:
        conn.close()

def _company_id_for_task(task_id: int) -> int | None:
    conn = get_rbac_db_connection()
    try:
        row = conn.execute("SELECT company_id FROM tasks WHERE id = ? LIMIT 1", (int(task_id),)).fetchone()
        if not row or row["company_id"] is None:
            return None
        return int(row["company_id"])
    finally:
        conn.close()

def _company_storage_root(company_id: int, create: bool = False) -> Path:
    storage_root = COMPANY_STORAGE_ROOT / f"company_{int(company_id)}"
    if create:
        storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root

def _resolve_company_storage_path(company_id: int, relative_path: str, create_parent: bool = False) -> Path | None:
    storage_root = _company_storage_root(int(company_id), create=create_parent)
    cleaned_relative_path = str(relative_path or "").strip()
    if not cleaned_relative_path:
        return storage_root.resolve()
    if Path(cleaned_relative_path).is_absolute():
        return None
    candidate = (storage_root / cleaned_relative_path.lstrip("/\\")).resolve()
    try:
        candidate.relative_to(storage_root.resolve())
    except ValueError:
        return None
    if create_parent:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate

def _list_company_storage_entries(company_id: int, relative_dir: str = "") -> list[dict[str, Any]]:
    target_dir = _resolve_company_storage_path(int(company_id), relative_dir, create_parent=False)
    if target_dir is None:
        return []
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for item in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        entries.append(
            {
                "name": item.name,
                "path": str(item.relative_to(_company_storage_root(int(company_id), create=False))),
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else None,
            }
        )
    return entries

def _super_admin_scope_violation_message(scoped_company_id: int | None) -> str | None:
    if scoped_company_id is None:
        return "No active company scope is selected"
    return None

def _ensure_target_in_super_admin_scope(target_company_id: int | None, entity_label: str) -> str | None:
    scoped_company_id = _effective_company_scope()
    base_error = _super_admin_scope_violation_message(scoped_company_id)
    if base_error is not None:
        return base_error
    if target_company_id is not None and scoped_company_id is not None and int(target_company_id) != int(scoped_company_id):
        return f"Forbidden: {entity_label} is outside selected company scope"
    return None

def _strict_company_scope_for_mutation() -> tuple[int | None, str | None]:
    role_name = current_role_name()
    if role_name == "Manager":
        company_id = current_user_company_id()
        if company_id is None:
            return None, "Manager account has no company assigned."
        return int(company_id), None
    if role_name == "Super Admin":
        selected_company_id = current_selected_company_id()
        if selected_company_id is None:
            return None, "No active company scope is selected"
        selected_company = _get_company_by_id(int(selected_company_id), require_active=True)
        if not selected_company:
            return None, "Selected company is not active or does not exist"
        return int(selected_company["id"]), None
    return None, "Only Super Admin or Manager can perform this action."

def _api_status_from_outcome(ok: bool, message: str, default_error_status: int = 400) -> int:
    if ok:
        return 200
    if str(message or "").strip().lower().startswith("forbidden"):
        return 403
    return int(default_error_status)

def _productmix_db_path() -> Path:
    productmix_cfg = CONFIG.get("apps", {}).get("productmix", {})
    productmix_cwd = str(productmix_cfg.get("cwd") or "ProductMixRestaurantDB").strip() or "ProductMixRestaurantDB"
    return ROOT / productmix_cwd / "product_mix.db"

def _list_restaurants_for_company_id(company_id: int | None) -> list[dict[str, Any]]:
    normalized_company_id = _normalize_company_id(company_id)
    if normalized_company_id is None:
        return []

    company_row = _get_company_by_id(int(normalized_company_id), require_active=False)
    company_name = str(company_row["name"] or "").strip() if company_row else ""
    if not company_name:
        return []

    pm_db_path = _productmix_db_path()
    if not pm_db_path.exists():
        return []

    conn = sqlite3.connect(pm_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, name, location, city, state
            FROM restaurants
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
            ORDER BY id ASC
            """,
            (company_name,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    options: list[dict[str, Any]] = []
    for row in rows:
        name = str(row["name"] or "").strip()
        location = str(row["location"] or "").strip()
        label = f"{name} - {location}" if location else name
        options.append(
            {
                "id": int(row["id"]),
                "name": name,
                "location": location,
                "city": str(row["city"] or "").strip(),
                "state": str(row["state"] or "").strip(),
                "label": label,
            }
        )
    return options

def _effective_restaurant_options_for_scope(company_id: int | None = None) -> list[dict[str, Any]]:
    normalized_company_id = _normalize_company_id(company_id)
    if normalized_company_id is None:
        normalized_company_id = _effective_company_scope(require_active=True)
    normalized_company_id = _normalize_company_id(normalized_company_id)
    if normalized_company_id is None:
        return []

    options = _list_restaurants_for_company_id(int(normalized_company_id))
    assigned_ids = _effective_user_restaurant_ids_for_scope(int(normalized_company_id))
    if assigned_ids is None:
        return options
    return [item for item in options if int(item["id"]) in assigned_ids]

def _effective_selected_restaurant_id_for_scope(
    company_id: int | None = None,
    ensure_default: bool = True,
) -> int | None:
    options = _effective_restaurant_options_for_scope(company_id)
    valid_ids = {int(item["id"]) for item in options}

    selected_restaurant_id = current_selected_restaurant_id()
    if selected_restaurant_id is not None and selected_restaurant_id in valid_ids:
        return int(selected_restaurant_id)

    next_selected_restaurant_id = int(options[0]["id"]) if ensure_default and options else None
    _set_session_selected_restaurant_context(next_selected_restaurant_id)
    return next_selected_restaurant_id

def _selected_restaurant_record_for_scope(company_id: int | None = None) -> dict[str, Any] | None:
    options = _effective_restaurant_options_for_scope(company_id)
    if not options:
        return None
    selected_restaurant_id = _effective_selected_restaurant_id_for_scope(company_id, ensure_default=True)
    for option in options:
        if int(option["id"]) == int(selected_restaurant_id or 0):
            return option
    return None

def _normalize_restaurant_ids(values: Any) -> list[int]:
    if values is None:
        return []
    if isinstance(values, (str, int)):
        raw_values = [values]
    else:
        raw_values = list(values)

    normalized_ids: list[int] = []
    seen_ids: set[int] = set()
    for raw_value in raw_values:
        normalized = _normalize_proxy_location_id(raw_value)
        if normalized is None or normalized in seen_ids:
            continue
        seen_ids.add(int(normalized))
        normalized_ids.append(int(normalized))
    return normalized_ids

def _assigned_restaurant_ids_for_user_company(
    conn: sqlite3.Connection,
    user_id: int,
    company_id: int | None,
) -> list[int]:
    normalized_company_id = _normalize_company_id(company_id)
    if normalized_company_id is None:
        return []
    rows = conn.execute(
        """
        SELECT restaurant_id
        FROM user_location_assignments
        WHERE user_id = ? AND company_id = ?
        ORDER BY restaurant_id ASC
        """,
        (int(user_id), int(normalized_company_id)),
    ).fetchall()
    return [int(row["restaurant_id"]) for row in rows]

def _replace_user_restaurant_assignments(
    conn: sqlite3.Connection,
    user_id: int,
    company_id: int | None,
    restaurant_ids: list[int],
) -> None:
    normalized_company_id = _normalize_company_id(company_id)
    if normalized_company_id is None:
        conn.execute("DELETE FROM user_location_assignments WHERE user_id = ?", (int(user_id),))
        return

    conn.execute(
        "DELETE FROM user_location_assignments WHERE user_id = ? AND company_id = ?",
        (int(user_id), int(normalized_company_id)),
    )
    for restaurant_id in restaurant_ids:
        conn.execute(
            """
            INSERT INTO user_location_assignments (user_id, company_id, restaurant_id)
            VALUES (?, ?, ?)
            """,
            (int(user_id), int(normalized_company_id), int(restaurant_id)),
        )

def _validate_restaurant_assignments_for_company(
    company_id: int | None,
    restaurant_ids: Any,
) -> tuple[bool, list[int], str | None]:
    normalized_company_id = _normalize_company_id(company_id)
    normalized_ids = _normalize_restaurant_ids(restaurant_ids)
    if normalized_company_id is None:
        if normalized_ids:
            return False, [], "Company is required for location assignments."
        return True, [], None

    available_ids = {int(item["id"]) for item in _list_restaurants_for_company_id(int(normalized_company_id))}
    invalid_ids = [restaurant_id for restaurant_id in normalized_ids if restaurant_id not in available_ids]
    if invalid_ids:
        return False, [], "One or more selected locations do not belong to the active company."
    return True, normalized_ids, None

def _effective_user_restaurant_ids_for_scope(company_id: int | None) -> set[int] | None:
    normalized_company_id = _normalize_company_id(company_id)
    if normalized_company_id is None:
        return None
    if current_role_name() == "Super Admin":
        return None

    user_id = current_user_id()
    if user_id is None:
        return None

    conn = get_rbac_db_connection()
    try:
        assigned_ids = _assigned_restaurant_ids_for_user_company(conn, int(user_id), int(normalized_company_id))
    finally:
        conn.close()

    if not assigned_ids:
        return None
    return {int(restaurant_id) for restaurant_id in assigned_ids}

def _first_active_company() -> sqlite3.Row | None:
    conn = get_rbac_db_connection()
    try:
        return conn.execute(
            "SELECT id, name, slug, is_active FROM companies WHERE is_active = 1 ORDER BY LOWER(name) ASC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

def current_role_name() -> str:
    user = session.get(SESSION_USER_KEY) or {}
    role_name = str(user.get("role_name") or "").strip()
    if role_name:
        return role_name
    if bool(user.get("is_admin")):
        return "Super Admin"
    return "Employee"

def _normalize_company_id(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    parsed = int(text)
    if parsed <= 0:
        return None
    return parsed

def _company_exists(conn: sqlite3.Connection, company_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM companies WHERE id = ? LIMIT 1", (int(company_id),)).fetchone())

def _get_actor_context(conn: sqlite3.Connection, actor_user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT u.id, u.company_id, u.is_active, r.name AS role_name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.id = ?
        LIMIT 1
        """,
        (int(actor_user_id),),
    ).fetchone()

def list_companies(active_only: bool = False) -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        where_sql = "WHERE c.is_active = 1" if active_only else ""
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.slug, c.is_active, c.created_at, c.updated_at,
                   COALESCE(user_counts.total_users, 0) AS total_users
            FROM companies c
            LEFT JOIN (
                SELECT company_id, COUNT(*) AS total_users
                FROM users
                GROUP BY company_id
            ) AS user_counts ON user_counts.company_id = c.id
            {where_sql}
            ORDER BY LOWER(c.name) ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def list_company_health() -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.slug, c.is_active, c.created_at, c.updated_at,
                   COALESCE(user_counts.total_users, 0) AS total_users,
                   COALESCE(user_counts.active_users, 0) AS active_users,
                   COALESCE(task_counts.total_tasks, 0) AS total_tasks,
                   COALESCE(task_counts.open_tasks, 0) AS open_tasks,
                   COALESCE(task_counts.completed_tasks, 0) AS completed_tasks
            FROM companies c
            LEFT JOIN (
                SELECT company_id,
                       COUNT(*) AS total_users,
                       SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_users
                FROM users
                GROUP BY company_id
            ) AS user_counts ON user_counts.company_id = c.id
            LEFT JOIN (
                SELECT company_id,
                       COUNT(*) AS total_tasks,
                       SUM(CASE WHEN status IN ('pending', 'in-progress') THEN 1 ELSE 0 END) AS open_tasks,
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks
                FROM tasks
                GROUP BY company_id
            ) AS task_counts ON task_counts.company_id = c.id
            ORDER BY LOWER(c.name) ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def create_company(actor_user_id: int, company_name: str) -> tuple[bool, str]:
    cleaned_name = str(company_name or "").strip()
    if len(cleaned_name) < 2:
        return False, "Company name must be at least 2 characters."

    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or str(actor["role_name"]) != "Super Admin":
            return False, "Only Super Admin can create companies."

        if conn.execute("SELECT 1 FROM companies WHERE LOWER(name) = LOWER(?) LIMIT 1", (cleaned_name,)).fetchone():
            return False, "Company already exists."

        slug_base = _slugify_company_name(cleaned_name)
        slug = slug_base
        suffix = 1
        while conn.execute("SELECT 1 FROM companies WHERE slug = ? LIMIT 1", (slug,)).fetchone():
            suffix += 1
            slug = f"{slug_base}-{suffix}"

        cur = conn.execute(
            """
            INSERT INTO companies (name, slug, is_active, created_at, updated_at)
            VALUES (?, ?, 1, datetime('now'), datetime('now'))
            """,
            (cleaned_name, slug),
        )
        new_company_id = int(cur.lastrowid)
        conn.commit()
        add_audit_log(actor_user_id, "create_company", "companies", new_company_id, json.dumps({"name": cleaned_name}), company_id=new_company_id)
        return True, "Company created."
    finally:
        conn.close()

def rename_company(actor_user_id: int, company_id: int, new_name: str) -> tuple[bool, str]:
    cleaned_name = str(new_name or "").strip()
    if len(cleaned_name) < 2:
        return False, "Company name must be at least 2 characters."

    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or str(actor["role_name"]) != "Super Admin":
            return False, "Only Super Admin can rename companies."

        company = conn.execute(
            "SELECT id, name, slug FROM companies WHERE id = ? LIMIT 1",
            (int(company_id),),
        ).fetchone()
        if not company:
            return False, "Company not found."

        duplicate = conn.execute(
            "SELECT 1 FROM companies WHERE LOWER(name) = LOWER(?) AND id <> ? LIMIT 1",
            (cleaned_name, int(company_id)),
        ).fetchone()
        if duplicate:
            return False, "Another company already uses that name."

        slug_base = _slugify_company_name(cleaned_name)
        slug = slug_base
        suffix = 1
        while conn.execute("SELECT 1 FROM companies WHERE slug = ? AND id <> ? LIMIT 1", (slug, int(company_id))).fetchone():
            suffix += 1
            slug = f"{slug_base}-{suffix}"

        conn.execute(
            "UPDATE companies SET name = ?, slug = ?, updated_at = datetime('now') WHERE id = ?",
            (cleaned_name, slug, int(company_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "rename_company",
            "companies",
            int(company_id),
            json.dumps({"from": str(company["name"]), "to": cleaned_name}),
            company_id=int(company_id),
        )
        return True, "Company renamed."
    finally:
        conn.close()

def set_company_active_state(actor_user_id: int, company_id: int, is_active: bool) -> tuple[bool, str]:
    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or str(actor["role_name"]) != "Super Admin":
            return False, "Only Super Admin can activate/deactivate companies."

        company = conn.execute(
            "SELECT id, name, is_active FROM companies WHERE id = ? LIMIT 1",
            (int(company_id),),
        ).fetchone()
        if not company:
            return False, "Company not found."

        target_active = 1 if is_active else 0
        if int(company["is_active"]) == target_active:
            return True, "Company already in requested state."

        if not is_active:
            users_count_row = conn.execute(
                "SELECT COUNT(*) AS total FROM users WHERE company_id = ?",
                (int(company_id),),
            ).fetchone()
            users_count = int(users_count_row["total"] if users_count_row else 0)
            if users_count > 0:
                return False, "Cannot deactivate a company that still has users."

            active_companies_row = conn.execute(
                "SELECT COUNT(*) AS total FROM companies WHERE is_active = 1",
            ).fetchone()
            if int(active_companies_row["total"] if active_companies_row else 0) <= 1:
                return False, "Cannot deactivate the last active company."

        conn.execute(
            "UPDATE companies SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            (target_active, int(company_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "activate_company" if is_active else "deactivate_company",
            "companies",
            int(company_id),
            json.dumps({"name": str(company["name"])}),
            company_id=int(company_id),
        )
        return True, "Company updated."
    finally:
        conn.close()

def get_company_profile(company_id: int) -> dict[str, Any] | None:
    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT c.id, c.name, c.slug, c.is_active,
                   cp.contact_email, cp.email_enabled, cp.email_from_name, cp.email_reply_to,
                     cp.daily_log_email_enabled, cp.daily_log_email_recipients, cp.daily_log_email_time, cp.daily_log_email_last_sent_for,
                   cp.contact_phone, cp.website,
                   cp.address_line1, cp.address_line2, cp.city, cp.state_region,
                   cp.postal_code, cp.country, cp.tax_id, cp.notes,
                   cp.logo_rel_path, cp.updated_at
            FROM companies c
            LEFT JOIN company_profiles cp ON cp.company_id = c.id
            WHERE c.id = ?
            LIMIT 1
            """,
            (int(company_id),),
        ).fetchone()
        if not row:
            return None

        return {
            "company_id": int(row["id"]),
            "company_name": str(row["name"]),
            "company_slug": str(row["slug"]),
            "is_active": int(row["is_active"]),
            "contact_email": str(row["contact_email"] or ""),
            "email_enabled": int(row["email_enabled"] if row["email_enabled"] is not None else 1),
            "email_from_name": str(row["email_from_name"] or ""),
            "email_reply_to": str(row["email_reply_to"] or ""),
            "daily_log_email_enabled": int(row["daily_log_email_enabled"] if row["daily_log_email_enabled"] is not None else 0),
            "daily_log_email_recipients": str(row["daily_log_email_recipients"] or ""),
            "daily_log_email_time": str(row["daily_log_email_time"] or "01:00"),
            "daily_log_email_last_sent_for": str(row["daily_log_email_last_sent_for"] or ""),
            "contact_phone": str(row["contact_phone"] or ""),
            "website": str(row["website"] or ""),
            "address_line1": str(row["address_line1"] or ""),
            "address_line2": str(row["address_line2"] or ""),
            "city": str(row["city"] or ""),
            "state_region": str(row["state_region"] or ""),
            "postal_code": str(row["postal_code"] or ""),
            "country": str(row["country"] or ""),
            "tax_id": str(row["tax_id"] or ""),
            "notes": str(row["notes"] or ""),
            "logo_rel_path": str(row["logo_rel_path"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
    finally:
        conn.close()

def upsert_company_profile(company_id: int, profile_data: dict[str, Any]) -> None:
    cleaned = {
        "contact_email": str(profile_data.get("contact_email") or "").strip(),
        "email_enabled": 1 if str(profile_data.get("email_enabled", "1")).strip() in {"1", "true", "yes", "on"} else 0,
        "email_from_name": str(profile_data.get("email_from_name") or "").strip(),
        "email_reply_to": str(profile_data.get("email_reply_to") or "").strip(),
        "daily_log_email_enabled": 1 if str(profile_data.get("daily_log_email_enabled", "0")).strip() in {"1", "true", "yes", "on"} else 0,
        "daily_log_email_recipients": str(profile_data.get("daily_log_email_recipients") or "").strip(),
        "daily_log_email_time": str(profile_data.get("daily_log_email_time") or "01:00").strip() or "01:00",
        "daily_log_email_last_sent_for": str(profile_data.get("daily_log_email_last_sent_for") or "").strip(),
        "contact_phone": str(profile_data.get("contact_phone") or "").strip(),
        "website": str(profile_data.get("website") or "").strip(),
        "address_line1": str(profile_data.get("address_line1") or "").strip(),
        "address_line2": str(profile_data.get("address_line2") or "").strip(),
        "city": str(profile_data.get("city") or "").strip(),
        "state_region": str(profile_data.get("state_region") or "").strip(),
        "postal_code": str(profile_data.get("postal_code") or "").strip(),
        "country": str(profile_data.get("country") or "").strip(),
        "tax_id": str(profile_data.get("tax_id") or "").strip(),
        "notes": str(profile_data.get("notes") or "").strip(),
        "logo_rel_path": str(profile_data.get("logo_rel_path") or "").strip(),
    }

    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO company_profiles (
                company_id, contact_email, email_enabled, email_from_name, email_reply_to, contact_phone, website,
                daily_log_email_enabled, daily_log_email_recipients, daily_log_email_time, daily_log_email_last_sent_for,
                address_line1, address_line2, city, state_region,
                postal_code, country, tax_id, notes, logo_rel_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(company_id) DO UPDATE SET
                contact_email = excluded.contact_email,
                email_enabled = excluded.email_enabled,
                email_from_name = excluded.email_from_name,
                email_reply_to = excluded.email_reply_to,
                daily_log_email_enabled = excluded.daily_log_email_enabled,
                daily_log_email_recipients = excluded.daily_log_email_recipients,
                daily_log_email_time = excluded.daily_log_email_time,
                daily_log_email_last_sent_for = excluded.daily_log_email_last_sent_for,
                contact_phone = excluded.contact_phone,
                website = excluded.website,
                address_line1 = excluded.address_line1,
                address_line2 = excluded.address_line2,
                city = excluded.city,
                state_region = excluded.state_region,
                postal_code = excluded.postal_code,
                country = excluded.country,
                tax_id = excluded.tax_id,
                notes = excluded.notes,
                logo_rel_path = excluded.logo_rel_path,
                updated_at = datetime('now')
            """,
            (
                int(company_id),
                cleaned["contact_email"],
                cleaned["email_enabled"],
                cleaned["email_from_name"],
                cleaned["email_reply_to"],
                cleaned["daily_log_email_enabled"],
                cleaned["daily_log_email_recipients"],
                cleaned["daily_log_email_time"],
                cleaned["daily_log_email_last_sent_for"],
                cleaned["contact_phone"],
                cleaned["website"],
                cleaned["address_line1"],
                cleaned["address_line2"],
                cleaned["city"],
                cleaned["state_region"],
                cleaned["postal_code"],
                cleaned["country"],
                cleaned["tax_id"],
                cleaned["notes"],
                cleaned["logo_rel_path"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

def _company_email_preferences(company_id: int | None) -> dict[str, Any]:
    normalized_company_id = _normalize_company_id(company_id)
    if normalized_company_id is None:
        return {
            "email_enabled": True,
            "email_from_name": "",
            "email_reply_to": "",
            "contact_email": "",
        }
    profile = get_company_profile(int(normalized_company_id)) or {}
    return {
        "email_enabled": bool(int(profile.get("email_enabled", 1) or 0)),
        "email_from_name": str(profile.get("email_from_name") or "").strip(),
        "email_reply_to": str(profile.get("email_reply_to") or "").strip(),
        "contact_email": str(profile.get("contact_email") or "").strip(),
        "daily_log_email_enabled": bool(int(profile.get("daily_log_email_enabled", 0) or 0)),
        "daily_log_email_recipients": str(profile.get("daily_log_email_recipients") or "").strip(),
        "daily_log_email_time": str(profile.get("daily_log_email_time") or "01:00").strip() or "01:00",
        "daily_log_email_last_sent_for": str(profile.get("daily_log_email_last_sent_for") or "").strip(),
    }

def _save_company_logo(company_id: int, uploaded_file) -> tuple[bool, str, str]:
    filename = str(getattr(uploaded_file, "filename", "") or "").strip()
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_COMPANY_LOGO_EXTENSIONS:
        return False, "Logo must be PNG, JPG, JPEG, or WEBP.", ""

    file_bytes = uploaded_file.stream.read(MAX_COMPANY_LOGO_BYTES + 1)
    if not file_bytes:
        return False, "Uploaded logo file is empty.", ""
    if len(file_bytes) > MAX_COMPANY_LOGO_BYTES:
        return False, "Logo file is too large (max 2MB).", ""

    profile_dir = _resolve_company_storage_path(int(company_id), "profile", create_parent=True)
    if profile_dir is None:
        return False, "Invalid profile storage path.", ""

    for existing in profile_dir.glob("logo.*"):
        if existing.is_file():
            try:
                existing.unlink()
            except Exception:
                pass

    logo_relative_path = f"profile/logo{extension}"
    logo_path = _resolve_company_storage_path(int(company_id), logo_relative_path, create_parent=True)
    if logo_path is None:
        return False, "Invalid logo path.", ""
    logo_path.write_bytes(file_bytes)
    return True, "", logo_relative_path

def user_has_role(user_id: int, allowed_roles: tuple[str, ...]) -> bool:
    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ? AND u.is_active = 1
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        if not row:
            return False
        return str(row["role_name"]) in allowed_roles
    finally:
        conn.close()

def can_user_create_task(user_id: int) -> bool:
    """Allow task creation only for Super Admin or Manager roles."""
    return user_has_role(int(user_id), ("Super Admin", "Manager"))

def add_audit_log(
    actor_user_id: int,
    action: str,
    target_table: str,
    target_id: int | None = None,
    details: str | None = None,
    company_id: int | None = None,
) -> None:
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO audit_logs (actor_user_id, action, target_table, target_id, company_id, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(actor_user_id),
                str(action),
                str(target_table),
                int(target_id) if target_id is not None else None,
                int(company_id) if company_id is not None else None,
                details,
            ),
        )
        conn.commit()
    finally:
        conn.close()

def _redact_audit_details(details: str | None, viewer_role: str) -> str | None:
    if not details:
        return details
    if viewer_role == "Super Admin":
        return details

    try:
        payload = json.loads(details)
    except Exception:
        return "[REDACTED]"

    def _mask(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): _mask(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_mask(item) for item in value]
        if isinstance(value, str):
            return "[REDACTED]"
        return value

    return json.dumps(_mask(payload))

def role_required(*allowed_roles: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if current_role_name() in allowed_roles:
                return view_func(*args, **kwargs)
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "Forbidden"}), 403
            return jsonify({"ok": False, "message": "Forbidden"}), 403
        return wrapped
    return decorator

def list_users_with_roles(company_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        normalized_company_id = _normalize_company_id(company_id)
        if normalized_company_id is not None:
            rows = conn.execute(
                """
                SELECT u.id, u.username, u.is_active, u.created_at, u.updated_at, u.last_login,
                       u.company_id, c.name AS company_name, r.name AS role_name
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN companies c ON c.id = u.company_id
                WHERE u.company_id = ?
                ORDER BY LOWER(u.username) ASC
                """,
                (normalized_company_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT u.id, u.username, u.is_active, u.created_at, u.updated_at, u.last_login,
                       u.company_id, c.name AS company_name, r.name AS role_name
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN companies c ON c.id = u.company_id
                ORDER BY LOWER(u.username) ASC
                """
            ).fetchall()

        users = [dict(r) for r in rows]
        restaurant_label_map: dict[int, str] = {}
        assigned_by_user: dict[int, list[int]] = {}

        if normalized_company_id is not None:
            restaurant_options = _list_restaurants_for_company_id(int(normalized_company_id))
            restaurant_label_map = {int(item["id"]): str(item["label"]) for item in restaurant_options}
            assignment_rows = conn.execute(
                """
                SELECT user_id, restaurant_id
                FROM user_location_assignments
                WHERE company_id = ?
                ORDER BY user_id ASC, restaurant_id ASC
                """,
                (int(normalized_company_id),),
            ).fetchall()
            for row in assignment_rows:
                assigned_by_user.setdefault(int(row["user_id"]), []).append(int(row["restaurant_id"]))

        for user in users:
            assigned_ids = assigned_by_user.get(int(user["id"]), [])
            user["assigned_restaurant_ids"] = assigned_ids
            user["assigned_restaurant_labels"] = [
                restaurant_label_map[restaurant_id]
                for restaurant_id in assigned_ids
                if restaurant_id in restaurant_label_map
            ]
            user["has_location_restrictions"] = bool(assigned_ids)
        return users
    finally:
        conn.close()

def _active_super_admin_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.is_active = 1 AND r.name = 'Super Admin'
        """
    ).fetchone()
    return int(row["total"] if row else 0)

def create_user_account(
    actor_user_id: int,
    username: str,
    password: str,
    role_name: str = "Employee",
    company_id: int | None = None,
    assigned_restaurant_ids: Any = None,
) -> tuple[bool, str]:
    normalized_username = str(username or "").strip()
    if len(normalized_username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password or "") < 8:
        return False, "Password must be at least 8 characters."
    if role_name not in {"Super Admin", "Manager", "Employee"}:
        return False, "Invalid role name."

    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or int(actor["is_active"]) != 1:
            return False, "Actor is invalid or inactive."

        actor_role = str(actor["role_name"])
        actor_company_id = int(actor["company_id"]) if actor["company_id"] is not None else None

        target_company_id = _normalize_company_id(company_id)
        if actor_role == "Super Admin":
            if target_company_id is None:
                target_company_id = actor_company_id
            if role_name != "Super Admin" and target_company_id is None:
                return False, "Company is required for non-Super Admin users."
            if target_company_id is not None and not _company_exists(conn, target_company_id):
                return False, "Selected company does not exist."
        elif actor_role == "Manager":
            if role_name == "Super Admin":
                return False, "Manager cannot assign Super Admin role."
            if actor_company_id is None:
                return False, "Manager account has no company assigned."
            target_company_id = actor_company_id
        else:
            return False, "Only Super Admin or Manager can create users."

        exists = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (normalized_username,),
        ).fetchone()
        if exists:
            return False, "Username already exists."

        role_id = _get_role_id(conn, role_name)
        normalized_assigned_restaurant_ids: list[int] = []
        if role_name != "Super Admin":
            ok_assignments, normalized_assigned_restaurant_ids, assignment_error = _validate_restaurant_assignments_for_company(
                target_company_id,
                assigned_restaurant_ids,
            )
            if not ok_assignments:
                return False, assignment_error or "Invalid location assignments."

        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role_id, company_id, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'))
            """,
            (normalized_username, generate_password_hash(password), role_id, target_company_id),
        )
        if role_name != "Super Admin":
            _replace_user_restaurant_assignments(
                conn,
                int(cur.lastrowid),
                target_company_id,
                normalized_assigned_restaurant_ids,
            )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "create_user",
            "users",
            int(cur.lastrowid),
            json.dumps(
                {
                    "username": normalized_username,
                    "role": role_name,
                    "company_id": target_company_id,
                    "assigned_restaurant_ids": normalized_assigned_restaurant_ids,
                }
            ),
            company_id=target_company_id,
        )
        return True, "User created."
    finally:
        conn.close()

def set_user_active_state(actor_user_id: int, target_user_id: int, is_active: bool) -> tuple[bool, str]:
    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or int(actor["is_active"]) != 1:
            return False, "Actor is invalid or inactive."

        actor_role = str(actor["role_name"])
        actor_company_id = int(actor["company_id"]) if actor["company_id"] is not None else None

        target = conn.execute(
            """
            SELECT u.id, u.username, u.is_active, u.company_id, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(target_user_id),),
        ).fetchone()
        if not target:
            return False, "User not found."

        target_company_id = int(target["company_id"]) if target["company_id"] is not None else None

        if actor_role == "Manager":
            if actor_company_id is None or target_company_id != actor_company_id:
                return False, "Manager can only manage users in the same company."
            if str(target["role_name"]) == "Super Admin":
                return False, "Manager cannot manage Super Admin users."
        elif actor_role != "Super Admin":
            return False, "Only Super Admin or Manager can update users."

        if int(actor_user_id) == int(target["id"]) and not is_active:
            return False, "You cannot deactivate your own account."

        if str(target["role_name"]) == "Super Admin" and not is_active and _active_super_admin_count(conn) <= 1:
            return False, "Cannot deactivate the last active Super Admin."

        conn.execute(
            "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if is_active else 0, int(target_user_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "activate_user" if is_active else "deactivate_user",
            "users",
            int(target_user_id),
            json.dumps({"username": str(target["username"]), "role": str(target["role_name"])}),
            company_id=target_company_id,
        )
        return True, "User updated."
    finally:
        conn.close()

def set_user_role_name(actor_user_id: int, target_user_id: int, role_name: str) -> tuple[bool, str]:
    if role_name not in {"Super Admin", "Manager", "Employee"}:
        return False, "Invalid role name."

    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or int(actor["is_active"]) != 1:
            return False, "Actor is invalid or inactive."

        actor_role = str(actor["role_name"])
        actor_company_id = int(actor["company_id"]) if actor["company_id"] is not None else None

        target = conn.execute(
            """
            SELECT u.id, u.username, u.is_active, u.company_id, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(target_user_id),),
        ).fetchone()
        if not target:
            return False, "User not found."

        target_company_id = int(target["company_id"]) if target["company_id"] is not None else None

        if actor_role == "Manager":
            if actor_company_id is None or target_company_id != actor_company_id:
                return False, "Manager can only manage users in the same company."
            if str(target["role_name"]) == "Super Admin" or role_name == "Super Admin":
                return False, "Manager cannot assign Super Admin role."
        elif actor_role != "Super Admin":
            return False, "Only Super Admin or Manager can change roles."

        if str(target["role_name"]) == "Super Admin" and role_name != "Super Admin" and _active_super_admin_count(conn) <= 1:
            return False, "Cannot demote the last active Super Admin."

        role_id = _get_role_id(conn, role_name)
        conn.execute(
            "UPDATE users SET role_id = ?, updated_at = datetime('now') WHERE id = ?",
            (role_id, int(target_user_id)),
        )
        if role_name == "Super Admin":
            _replace_user_restaurant_assignments(conn, int(target_user_id), target_company_id, [])
        conn.commit()
        add_audit_log(
            actor_user_id,
            "change_role",
            "users",
            int(target_user_id),
            json.dumps({"username": str(target["username"]), "from": str(target["role_name"]), "to": role_name}),
            company_id=target_company_id,
        )
        return True, "Role updated."
    finally:
        conn.close()

def set_user_location_assignments(
    actor_user_id: int,
    target_user_id: int,
    restaurant_ids: Any,
) -> tuple[bool, str]:
    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or int(actor["is_active"]) != 1:
            return False, "Actor is invalid or inactive."

        actor_role = str(actor["role_name"])
        actor_company_id = int(actor["company_id"]) if actor["company_id"] is not None else None

        target = conn.execute(
            """
            SELECT u.id, u.username, u.company_id, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(target_user_id),),
        ).fetchone()
        if not target:
            return False, "User not found."

        target_company_id = int(target["company_id"]) if target["company_id"] is not None else None
        target_role = str(target["role_name"])

        if target_role == "Super Admin":
            return False, "Super Admin users are not restricted to specific locations."

        if actor_role == "Manager":
            if actor_company_id is None or target_company_id != actor_company_id:
                return False, "Manager can only manage users in the same company."
        elif actor_role != "Super Admin":
            return False, "Only Super Admin or Manager can update locations."

        ok_assignments, normalized_restaurant_ids, assignment_error = _validate_restaurant_assignments_for_company(
            target_company_id,
            restaurant_ids,
        )
        if not ok_assignments:
            return False, assignment_error or "Invalid location assignments."

        _replace_user_restaurant_assignments(conn, int(target_user_id), target_company_id, normalized_restaurant_ids)
        conn.commit()
        add_audit_log(
            actor_user_id,
            "set_user_locations",
            "users",
            int(target_user_id),
            json.dumps(
                {
                    "username": str(target["username"]),
                    "assigned_restaurant_ids": normalized_restaurant_ids,
                }
            ),
            company_id=target_company_id,
        )
        if normalized_restaurant_ids:
            return True, "User location access updated."
        return True, "User now has access to all company locations."
    finally:
        conn.close()

def create_task_record(
    actor_user_id: int,
    title: str,
    description: str,
    assigned_to: int | None,
    due_date: str | None = None,
    priority: str = "normal",
    company_id: int | None = None,
) -> tuple[bool, str]:
    cleaned_title = str(title or "").strip()
    if not cleaned_title:
        return False, "Task title is required."

    valid_priorities = {"urgent", "high", "normal", "low"}
    cleaned_priority = str(priority or "normal").strip().lower()
    if cleaned_priority not in valid_priorities:
        cleaned_priority = "normal"

    cleaned_due_date: str | None = str(due_date or "").strip() or None

    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or int(actor["is_active"]) != 1:
            return False, "Actor is invalid or inactive."

        actor_role = str(actor["role_name"])
        actor_company_id = int(actor["company_id"]) if actor["company_id"] is not None else None

        effective_company_id = _normalize_company_id(company_id)
        if actor_role == "Manager":
            if actor_company_id is None:
                return False, "Manager account has no company assigned."
            effective_company_id = actor_company_id
        elif actor_role == "Super Admin":
            if effective_company_id is None:
                effective_company_id = actor_company_id
            if effective_company_id is None:
                return False, "Company is required to create tasks."
            if not _company_exists(conn, effective_company_id):
                return False, "Selected company does not exist."
        else:
            return False, "Only Super Admin or Manager can create tasks."

        assigned_user_id = int(assigned_to) if assigned_to is not None else None
        if assigned_user_id is not None:
            assigned_row = conn.execute(
                "SELECT id, is_active, company_id FROM users WHERE id = ? LIMIT 1",
                (assigned_user_id,),
            ).fetchone()
            if not assigned_row or int(assigned_row["is_active"]) != 1:
                return False, "Assigned user must be an active user."
            assigned_company_id = int(assigned_row["company_id"]) if assigned_row["company_id"] is not None else None
            if assigned_company_id != effective_company_id:
                return False, "Assigned user must belong to the selected company."

        cur = conn.execute(
            """
            INSERT INTO tasks (title, description, status, created_by, assigned_to, due_date, priority, company_id, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                cleaned_title,
                str(description or "").strip() or None,
                int(actor_user_id),
                assigned_user_id,
                cleaned_due_date,
                cleaned_priority,
                effective_company_id,
            ),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "create_task",
            "tasks",
            int(cur.lastrowid),
            json.dumps({"title": cleaned_title, "assigned_to": assigned_user_id, "priority": cleaned_priority}),
            company_id=effective_company_id,
        )
        return True, "Task created."
    finally:
        conn.close()

def update_task_status(actor_user_id: int, task_id: int, status: str) -> tuple[bool, str]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"pending", "in-progress", "completed"}:
        return False, "Invalid status value."

    conn = get_rbac_db_connection()
    try:
        actor = _get_actor_context(conn, actor_user_id)
        if not actor or int(actor["is_active"]) != 1:
            return False, "Actor is invalid or inactive."

        actor_role = str(actor["role_name"])
        actor_company_id = int(actor["company_id"]) if actor["company_id"] is not None else None

        row = conn.execute("SELECT id, title, company_id FROM tasks WHERE id = ? LIMIT 1", (int(task_id),)).fetchone()
        if not row:
            return False, "Task not found."

        task_company_id = int(row["company_id"]) if row["company_id"] is not None else None
        if actor_role == "Manager" and actor_company_id != task_company_id:
            return False, "Manager can only update tasks in their company."
        if actor_role not in {"Super Admin", "Manager"}:
            return False, "Only Super Admin or Manager can update task status."

        completed_at = "datetime('now')" if normalized_status == "completed" else "NULL"
        conn.execute(
            f"""
            UPDATE tasks
            SET status = ?,
                updated_at = datetime('now'),
                completed_at = {completed_at}
            WHERE id = ?
            """,
            (normalized_status, int(task_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "update_task_status",
            "tasks",
            int(task_id),
            json.dumps({"status": normalized_status, "title": str(row["title"])}),
            company_id=task_company_id,
        )
        return True, "Task status updated."
    finally:
        conn.close()

def list_tasks(limit: int = 200, status_filter: str | None = None, company_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        normalized_company_id = _normalize_company_id(company_id)
        if status_filter and status_filter in {"pending", "in-progress", "completed"}:
            if normalized_company_id is not None:
                rows = conn.execute(
                    """
                    SELECT t.id, t.title, t.description, t.status, t.due_date, t.priority,
                           t.created_at, t.updated_at, t.completed_at, t.company_id,
                           creator.username AS created_by_username,
                           assignee.username AS assigned_to_username
                    FROM tasks t
                    JOIN users creator ON creator.id = t.created_by
                    LEFT JOIN users assignee ON assignee.id = t.assigned_to
                    WHERE t.status = ? AND t.company_id = ?
                    ORDER BY
                        CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END,
                        t.due_date ASC NULLS LAST,
                        t.id DESC
                    LIMIT ?
                    """,
                    (status_filter, normalized_company_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT t.id, t.title, t.description, t.status, t.due_date, t.priority,
                           t.created_at, t.updated_at, t.completed_at, t.company_id,
                           creator.username AS created_by_username,
                           assignee.username AS assigned_to_username
                    FROM tasks t
                    JOIN users creator ON creator.id = t.created_by
                    LEFT JOIN users assignee ON assignee.id = t.assigned_to
                    WHERE t.status = ?
                    ORDER BY
                        CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END,
                        t.due_date ASC NULLS LAST,
                        t.id DESC
                    LIMIT ?
                    """,
                    (status_filter, int(limit)),
                ).fetchall()
        else:
            if normalized_company_id is not None:
                rows = conn.execute(
                    """
                    SELECT t.id, t.title, t.description, t.status, t.due_date, t.priority,
                           t.created_at, t.updated_at, t.completed_at, t.company_id,
                           creator.username AS created_by_username,
                           assignee.username AS assigned_to_username
                    FROM tasks t
                    JOIN users creator ON creator.id = t.created_by
                    LEFT JOIN users assignee ON assignee.id = t.assigned_to
                    WHERE t.company_id = ?
                    ORDER BY
                        CASE t.status WHEN 'pending' THEN 1 WHEN 'in-progress' THEN 2 ELSE 3 END,
                        CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END,
                        t.due_date ASC NULLS LAST,
                        t.id DESC
                    LIMIT ?
                    """,
                    (normalized_company_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT t.id, t.title, t.description, t.status, t.due_date, t.priority,
                           t.created_at, t.updated_at, t.completed_at, t.company_id,
                           creator.username AS created_by_username,
                           assignee.username AS assigned_to_username
                    FROM tasks t
                    JOIN users creator ON creator.id = t.created_by
                    LEFT JOIN users assignee ON assignee.id = t.assigned_to
                    ORDER BY
                        CASE t.status WHEN 'pending' THEN 1 WHEN 'in-progress' THEN 2 ELSE 3 END,
                        CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END,
                        t.due_date ASC NULLS LAST,
                        t.id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def list_audit_logs(limit: int = 300, company_id: int | None = None, viewer_role: str = "Super Admin") -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        normalized_company_id = _normalize_company_id(company_id)
        if normalized_company_id is not None:
            rows = conn.execute(
                """
                SELECT a.id, a.action, a.target_table, a.target_id, a.company_id, a.details, a.created_at,
                       u.username AS actor_username
                FROM audit_logs a
                JOIN users u ON u.id = a.actor_user_id
                WHERE a.company_id = ?
                ORDER BY a.id DESC
                LIMIT ?
                """,
                (normalized_company_id, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT a.id, a.action, a.target_table, a.target_id, a.company_id, a.details, a.created_at,
                       u.username AS actor_username
                FROM audit_logs a
                JOIN users u ON u.id = a.actor_user_id
                ORDER BY a.id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        results = [dict(r) for r in rows]
        if viewer_role != "Super Admin":
            for row in results:
                row["details"] = _redact_audit_details(row.get("details"), viewer_role)
        return results
    finally:
        conn.close()

def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

def _env_text(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()

def _is_email_like(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value or "").strip()))

def _mail_settings() -> dict[str, Any]:
    mail_cfg = CONFIG.get("mail", {}) if isinstance(CONFIG.get("mail", {}), dict) else {}
    username_env = str(mail_cfg.get("username_env") or "DEXTER_SMTP_USERNAME").strip() or "DEXTER_SMTP_USERNAME"
    password_env = str(mail_cfg.get("password_env") or "DEXTER_SMTP_PASSWORD").strip() or "DEXTER_SMTP_PASSWORD"

    smtp_port_raw = _env_text("DEXTER_SMTP_PORT", str(mail_cfg.get("smtp_port") or "587"))
    try:
        smtp_port = int(smtp_port_raw)
    except (TypeError, ValueError):
        smtp_port = 587

    use_ssl = _env_flag("DEXTER_SMTP_USE_SSL", default=bool(mail_cfg.get("use_ssl", False)))
    use_starttls = _env_flag("DEXTER_SMTP_USE_STARTTLS", default=bool(mail_cfg.get("use_starttls", not use_ssl)))
    if use_ssl:
        use_starttls = False

    return {
        "enabled": _env_flag("DEXTER_SMTP_ENABLED", default=bool(mail_cfg.get("enabled", False))),
        "smtp_host": _env_text("DEXTER_SMTP_HOST", str(mail_cfg.get("smtp_host") or "")),
        "smtp_port": smtp_port,
        "use_ssl": use_ssl,
        "use_starttls": use_starttls,
        "username_env": username_env,
        "password_env": password_env,
        "username": _env_text(username_env),
        "password": _env_text(password_env),
        "from_email": _env_text("DEXTER_MAIL_FROM_EMAIL", str(mail_cfg.get("from_email") or "admin@dexterassist.com")),
        "from_name": _env_text("DEXTER_MAIL_FROM_NAME", str(mail_cfg.get("from_name") or "Dexter Assist")),
        "reply_to": _env_text("DEXTER_MAIL_REPLY_TO", str(mail_cfg.get("reply_to") or "admin@dexterassist.com")),
        "public_base_url": _env_text("DEXTER_PUBLIC_BASE_URL", str(mail_cfg.get("public_base_url") or "")),
    }

def _mail_delivery_status() -> dict[str, Any]:
    settings = _mail_settings()
    problems: list[str] = []
    if not settings["enabled"]:
        problems.append("SMTP delivery is disabled.")
    if not settings["smtp_host"]:
        problems.append("SMTP host is not configured.")
    if not settings["from_email"] or not _is_email_like(settings["from_email"]):
        problems.append("From email is missing or invalid.")
    if not settings["username"]:
        problems.append(f"SMTP username env var {settings['username_env']} is empty.")
    if not settings["password"]:
        problems.append(f"SMTP password env var {settings['password_env']} is empty.")
    return {
        "ready": not problems,
        "problems": problems,
        "settings": settings,
    }

def _public_base_url() -> str:
    configured = str(_mail_settings().get("public_base_url") or "").strip().rstrip("/")
    if configured:
        return configured
    if request.headers.get("X-Forwarded-Proto") and request.headers.get("Host"):
        proto = str(request.headers.get("X-Forwarded-Proto") or "http").split(",", 1)[0].strip()
        host = str(request.headers.get("Host") or "").strip()
        if proto and host:
            return f"{proto}://{host}".rstrip("/")
    return request.host_url.rstrip("/")

def send_email_message(
    to_addresses: list[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
    company_id: int | None = None,
) -> tuple[bool, str]:
    status = _mail_delivery_status()
    if not status["ready"]:
        return False, " ".join(status["problems"])

    company_mail = _company_email_preferences(company_id)
    if not company_mail["email_enabled"]:
        return False, "Email is disabled for the selected company."

    recipients = [str(item or "").strip() for item in to_addresses if str(item or "").strip()]
    if not recipients:
        return False, "No recipient email address provided."

    settings = status["settings"]
    message = EmailMessage()
    from_name = str(company_mail.get("email_from_name") or settings.get("from_name") or "").strip()
    from_email = str(settings.get("from_email") or "").strip()
    message["Subject"] = str(subject or "Dexter Assist Notification")
    message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    message["To"] = ", ".join(recipients)
    reply_to = str(company_mail.get("email_reply_to") or settings.get("reply_to") or "").strip()
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(str(text_body or ""))
    if html_body:
        message.add_alternative(str(html_body), subtype="html")

    try:
        if settings["use_ssl"]:
            with smtplib.SMTP_SSL(settings["smtp_host"], int(settings["smtp_port"]), timeout=20, context=ssl.create_default_context()) as smtp:
                smtp.login(settings["username"], settings["password"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings["smtp_host"], int(settings["smtp_port"]), timeout=20) as smtp:
                smtp.ehlo()
                if settings["use_starttls"]:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(settings["username"], settings["password"])
                smtp.send_message(message)
    except Exception as exc:
        return False, f"Email send failed: {exc}"

    return True, "Email sent."

def _password_reset_email_payload(username: str, reset_url: str) -> tuple[str, str, str]:
    clean_username = str(username or "user").strip() or "user"
    clean_url = str(reset_url or "").strip()
    subject = "Dexter Assist password reset"
    text_body = (
        f"Hello {clean_username},\n\n"
        "A Dexter Assist password reset was requested for your account.\n"
        f"Use this link to set a new password: {clean_url}\n\n"
        "This link expires in 1 hour. If you did not request this, you can ignore this email.\n"
    )
    html_body = (
        "<p>Hello {user},</p>"
        "<p>A Dexter Assist password reset was requested for your account.</p>"
        "<p><a href=\"{url}\">Set a new password</a></p>"
        "<p>This link expires in 1 hour. If you did not request this, you can ignore this email.</p>"
    ).format(user=clean_username, url=clean_url)
    return subject, text_body, html_body

def _account_invite_email_payload(username: str, role_name: str, reset_url: str) -> tuple[str, str, str]:
    clean_username = str(username or "user").strip() or "user"
    clean_role = str(role_name or "Employee").strip() or "Employee"
    clean_url = str(reset_url or "").strip()
    subject = "You have been invited to Dexter Assist"
    text_body = (
        f"Hello {clean_username},\n\n"
        f"An account has been created for you in Dexter Assist with the role {clean_role}.\n"
        "Use the link below to set your password and finish setup:\n"
        f"{clean_url}\n\n"
        "This setup link expires in 48 hours.\n"
    )
    html_body = (
        "<p>Hello {user},</p>"
        "<p>An account has been created for you in Dexter Assist with the role <strong>{role}</strong>.</p>"
        "<p><a href=\"{url}\">Set your password and finish setup</a></p>"
        "<p>This setup link expires in 48 hours.</p>"
    ).format(user=clean_username, role=clean_role, url=clean_url)
    return subject, text_body, html_body

def load_auth_users() -> dict[str, Any]:
    if not AUTH_USERS_PATH.exists():
        return {}
    try:
        with AUTH_USERS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def ensure_default_admin_user() -> None:
    admin_username = os.environ.get("DEXTER_ADMIN_USER", "").strip()
    admin_password = os.environ.get("DEXTER_ADMIN_PASS", "").strip()
    if not admin_username or not admin_password:
        print(
            "[dexter] WARNING: DEXTER_ADMIN_USER / DEXTER_ADMIN_PASS env vars not set. "
            "Default admin account will NOT be created automatically.",
            file=sys.stderr,
        )
        return
    users = load_auth_users()
    current = users.get(admin_username)
    if not current or not current.get("is_admin"):
        users[admin_username] = {
            "password_hash": generate_password_hash(admin_password),
            "created_at": current.get("created_at") if isinstance(current, dict) else datetime.now().isoformat(timespec="seconds"),
            "last_login": current.get("last_login") if isinstance(current, dict) else None,
            "is_admin": True,
            "email": admin_username,
        }
        save_auth_users(users)

def _parse_email_recipients(raw_value: str) -> list[str]:
    parts = re.split(r"[;,\n]+", str(raw_value or ""))
    recipients: list[str] = []
    seen: set[str] = set()
    for part in parts:
        email = str(part or "").strip().lower()
        if not _is_email_like(email) or email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients

def _parse_hhmm(raw_value: str, default_hour: int = 1, default_minute: int = 0) -> tuple[int, int]:
    text = str(raw_value or "").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", text):
        return default_hour, default_minute
    hour = int(text[:2])
    minute = int(text[3:5])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default_hour, default_minute
    return hour, minute

def _manager_app_company_root(company_id: int) -> Path:
    primary = ROOT / "Manager App" / "company_data" / str(int(company_id))
    if primary.exists():
        return primary
    return ROOT.parent / "company_data" / str(int(company_id))

def _parse_daily_log_csv(file_path: Path) -> dict[str, Any] | None:
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
    except Exception:
        return None

    parsed: dict[str, Any] = {
        "date": "",
        "shift": "",
        "notes": "",
        "employees": [],
        "deductions": [],
        "deposit_amount": "",
        "file_name": file_path.name,
    }
    section = ""
    for row in rows:
        if not row:
            continue
        key = str(row[0] or "").strip()
        if key == "Date" and len(row) > 1:
            parsed["date"] = str(row[1] or "").strip()
            continue
        if key == "Shift" and len(row) > 1:
            parsed["shift"] = str(row[1] or "").strip()
            continue
        if key == "Notes" and len(row) > 1:
            parsed["notes"] = str(row[1] or "").strip()
            continue
        if key == "Employee Entries":
            section = "employees"
            continue
        if key == "Cash Deductions":
            section = "deductions"
            continue
        if key == "Deposit Summary":
            section = "deposit"
            continue
        if key == "Cash Drawer Count":
            section = "drawer"
            continue
        if section == "employees":
            if key == "Name":
                continue
            if key:
                parsed["employees"].append(key)
            continue
        if section == "deductions":
            if key:
                parsed["deductions"].append(key)
            continue
        if section == "deposit" and key == "DEPOSIT AMOUNT" and len(row) > 1:
            parsed["deposit_amount"] = str(row[1] or "").strip()
            continue
    return parsed

def _daily_log_has_meaningful_text(entry: dict[str, Any]) -> bool:
    if str(entry.get("notes") or "").strip():
        return True
    if any(str(name or "").strip() for name in entry.get("employees") or []):
        return True
    if any(str(desc or "").strip() for desc in entry.get("deductions") or []):
        return True
    return False

def _collect_daily_log_entries_for_company(company_id: int, target_date: str) -> list[dict[str, Any]]:
    company_root = _manager_app_company_root(int(company_id))
    if not company_root.exists():
        return []

    target_prefix = target_date.replace("-", "") + "_"
    location_label_map = {
        int(item["id"]): str(item.get("label") or item.get("name") or f"Location {item['id']}")
        for item in _list_restaurants_for_company_id(int(company_id))
    }
    entries: list[dict[str, Any]] = []
    candidate_dirs = [company_root / "daily_logs"]
    locations_root = company_root / "locations"
    if locations_root.exists():
        for child in locations_root.iterdir():
            candidate_dirs.append(child / "daily_logs")

    for directory in candidate_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for file_path in sorted(directory.glob(f"{target_prefix}*.csv")):
            parsed = _parse_daily_log_csv(file_path)
            if not parsed or not _daily_log_has_meaningful_text(parsed):
                continue
            location_label = "Company Default"
            path_parts = file_path.parts
            if "locations" in path_parts:
                loc_index = path_parts.index("locations")
                if loc_index + 1 < len(path_parts):
                    raw_location_id = path_parts[loc_index + 1]
                    if str(raw_location_id).isdigit():
                        location_label = location_label_map.get(int(raw_location_id), f"Location {raw_location_id}")
            parsed["location_label"] = location_label
            entries.append(parsed)
    return entries

def _daily_log_email_payload(company_name: str, target_date: str, entries: list[dict[str, Any]]) -> tuple[str, str, str]:
    subject = f"{company_name} daily operations log - {target_date}"
    text_lines = [f"Daily operations log for {company_name}", f"Date: {target_date}", ""]
    html_sections = [f"<p><strong>Daily operations log for {company_name}</strong><br>Date: {target_date}</p>"]

    for entry in entries:
        shift = str(entry.get("shift") or "").strip() or "Unknown shift"
        location_label = str(entry.get("location_label") or "Company Default").strip()
        notes = str(entry.get("notes") or "").strip()
        employees = [str(name).strip() for name in (entry.get("employees") or []) if str(name).strip()]
        deductions = [str(desc).strip() for desc in (entry.get("deductions") or []) if str(desc).strip()]
        deposit_amount = str(entry.get("deposit_amount") or "").strip()

        text_lines.append(f"Location: {location_label}")
        text_lines.append(f"Shift: {shift}")
        if notes:
            text_lines.append(f"Notes: {notes}")
        if employees:
            text_lines.append("Employees: " + ", ".join(employees))
        if deductions:
            text_lines.append("Deductions: " + ", ".join(deductions))
        if deposit_amount:
            text_lines.append(f"Deposit Amount: {deposit_amount}")
        text_lines.append("")

        html = [f"<h3 style=\"margin-bottom:4px\">{location_label}</h3>", f"<p><strong>Shift:</strong> {shift}</p>"]
        if notes:
            html.append(f"<p><strong>Notes:</strong> {notes}</p>")
        if employees:
            html.append(f"<p><strong>Employees:</strong> {', '.join(employees)}</p>")
        if deductions:
            html.append(f"<p><strong>Deductions:</strong> {', '.join(deductions)}</p>")
        if deposit_amount:
            html.append(f"<p><strong>Deposit Amount:</strong> {deposit_amount}</p>")
        html_sections.append("".join(html))

    return subject, "\n".join(text_lines).strip(), "<html><body style=\"font-family:Segoe UI,Trebuchet MS,sans-serif;color:#1f2937\">" + "".join(html_sections) + "</body></html>"

def _mark_daily_log_email_sent(company_id: int, target_date: str) -> None:
    profile = get_company_profile(int(company_id)) or {}
    if not profile:
        return
    payload = dict(profile)
    payload["daily_log_email_last_sent_for"] = str(target_date)
    upsert_company_profile(int(company_id), payload)

def _run_daily_log_email_scheduler_once() -> None:
    now = datetime.now()
    target_date = (now.date() - timedelta(days=1)).isoformat()
    for company in list_companies(active_only=True):
        company_id = int(company["id"])
        prefs = _company_email_preferences(company_id)
        if not prefs.get("email_enabled") or not prefs.get("daily_log_email_enabled"):
            continue
        recipients = _parse_email_recipients(str(prefs.get("daily_log_email_recipients") or ""))
        if not recipients:
            recipients = _parse_email_recipients(str(prefs.get("contact_email") or ""))
        if not recipients:
            continue
        send_hour, send_minute = _parse_hhmm(str(prefs.get("daily_log_email_time") or "01:00"))
        if (now.hour, now.minute) < (send_hour, send_minute):
            continue
        if str(prefs.get("daily_log_email_last_sent_for") or "") == target_date:
            continue
        entries = _collect_daily_log_entries_for_company(company_id, target_date)
        if not entries:
            continue
        subject, text_body, html_body = _daily_log_email_payload(str(company.get("name") or f"Company {company_id}"), target_date, entries)
        sent, _message = send_email_message(recipients, subject, text_body, html_body, company_id=company_id)
        if sent:
            _mark_daily_log_email_sent(company_id, target_date)

def start_daily_log_email_scheduler(interval_seconds: int = 60) -> None:
    def _watch() -> None:
        while True:
            try:
                _run_daily_log_email_scheduler_once()
            except Exception:
                pass
            time.sleep(max(30, int(interval_seconds)))

    t = threading.Thread(target=_watch, name="dexter-daily-log-email", daemon=True)
    t.start()

def save_auth_users(users: dict[str, Any]) -> None:
    with AUTH_USERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def get_next_path(default_path: str = "/portal/managerapp") -> str:
    next_path = (request.args.get("next") or request.form.get("next") or "").strip()
    if not next_path.startswith("/") or next_path.startswith("//"):
        return default_path
    return next_path

def default_post_login_path() -> str:
    return "/portal/managerapp"

def default_company_switch_path() -> str:
    return "/portal/managerapp?company_switched=1"

def default_location_switch_path() -> str:
    return "/portal/managerapp?location_switched=1"

def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if session.get(SESSION_USER_KEY):
            return view_func(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": "Authentication required"}), 401
        return redirect(url_for("auth_login", next=request.full_path.rstrip("?")))
    return wrapped

def is_port_open(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()

def is_port_free(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def find_free_port(host: str) -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()

def open_url_in_chrome(url: str) -> bool:
    """Best-effort open in Google Chrome, with sensible fallbacks."""
    chrome_candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]

    for chrome_exe in chrome_candidates:
        if chrome_exe and chrome_exe.exists():
            try:
                subprocess.Popen([str(chrome_exe), url])
                return True
            except Exception:
                pass

    try:
        subprocess.Popen(["cmd", "/c", "start", "", "chrome", url])
        return True
    except Exception:
        pass

    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False

def check_health(url: str, timeout: float = 1.5) -> bool:
    try:
        with urlopen(url, timeout=timeout):
            return True
    except (URLError, TimeoutError, ValueError):
        return False

class AppManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[Any] | None] = {
            name: None for name in config["apps"].keys()
        }
        self._runtime_base_urls: dict[str, str | None] = {
            name: None for name in config["apps"].keys()
        }
        RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _app_cfg(self, name: str) -> dict[str, Any]:
        name = self.resolve_name(name)
        if not name:
            raise KeyError(f"Unknown app: {name}")
        return self.config["apps"][name]

    def resolve_name(self, name: str) -> str | None:
        candidate = (name or "").strip().lower()
        if not candidate:
            return None
        if candidate in self.config["apps"]:
            return candidate

        alias_pairs = {
            "manager": "managerapp",
            "managerapp": "manager",
        }
        alias = alias_pairs.get(candidate)
        if alias and alias in self.config["apps"]:
            return alias
        return None

    def _parse_host_port(self, base_url: str) -> tuple[str, int]:
        parts = base_url.replace("http://", "").replace("https://", "").split("/")[0]
        host, port = parts.split(":", 1)
        return host, int(port)

    def _base_url_for_app(self, name: str) -> str:
        app = self._app_cfg(name)
        runtime = self._runtime_base_urls.get(name)
        if runtime:
            return runtime
        return str(app["base_url"])

    def get_base_url(self, name: str) -> str:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            raise KeyError(f"Unknown app: {name}")
        with self._lock:
            return self._base_url_for_app(resolved_name)

    def _runtime_health_url(self, name: str) -> str:
        app = self._app_cfg(name)
        return urljoin(self._base_url_for_app(name), app.get("health_path", "/"))

    def _log_file(self, name: str) -> Path:
        return RUNTIME_LOG_DIR / f"{name}.log"

    def _tail_log(self, name: str, max_lines: int = 40) -> str:
        log_file = self._log_file(name)
        if not log_file.exists():
            return ""
        with log_file.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])

    def _rotate_log(self, name: str) -> None:
        log_file = self._log_file(name)
        if log_file.exists() and log_file.stat().st_size > 200 * 1024:
            old = log_file.with_suffix(".log.old")
            try:
                log_file.rename(old)
            except OSError:
                pass

    def status(self) -> dict[str, Any]:
        snapshots: dict[str, dict[str, Any]] = {}
        with self._lock:
            for name, app in self.config["apps"].items():
                proc = self._procs.get(name)
                running = proc is not None and proc.poll() is None
                resolved_base_url = self._base_url_for_app(name)
                snapshots[name] = {
                    "display_name": app["display_name"],
                    "base_url": resolved_base_url,
                    "health_url": urljoin(resolved_base_url, app.get("health_path", "/")),
                    "running": running,
                    "pid": proc.pid if running else None,
                    "log_tail": self._tail_log(name),
                }

        out: dict[str, Any] = {}
        for name, snap in snapshots.items():
            healthy = check_health(snap["health_url"]) if snap["running"] else False
            out[name] = {
                "display_name": snap["display_name"],
                "base_url": snap["base_url"],
                "running": snap["running"],
                "healthy": healthy,
                "pid": snap["pid"],
                "log_tail": snap["log_tail"],
            }
        return out

    def preflight(self) -> dict[str, Any]:
        issues: dict[str, list[str]] = {}
        for name, app in self.config["apps"].items():
            app_issues: list[str] = []
            cwd = ROOT / app["cwd"]
            entry = cwd / app["entrypoint"]
            if not cwd.exists():
                app_issues.append(f"Missing folder: {cwd}")
            if not entry.exists():
                app_issues.append(f"Missing entrypoint: {entry}")
            host, port = self._parse_host_port(app["base_url"])
            auto_port = bool(app.get("auto_port"))
            if (not auto_port) and (not is_port_open(host, port)) and (not is_port_free(host, port)):
                app_issues.append(f"Port unavailable: {host}:{port}")
            if app_issues:
                issues[name] = app_issues
        return {"ok": len(issues) == 0, "issues": issues}

    def start(self, name: str) -> dict[str, Any]:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return {"ok": False, "message": f"Unknown app: {name}"}

        with self._lock:
            app = self._app_cfg(resolved_name)
            proc = self._procs.get(resolved_name)
            if proc is not None and proc.poll() is None:
                return {"ok": True, "message": f"{resolved_name} already running"}

            cwd = ROOT / app["cwd"]
            entry = cwd / app["entrypoint"]
            if not entry.exists():
                return {"ok": False, "message": f"Entrypoint not found: {entry}"}

            host, port = self._parse_host_port(app["base_url"])
            auto_port = bool(app.get("auto_port"))
            if not is_port_free(host, port):
                if auto_port:
                    port = find_free_port(host)
                else:
                    return {"ok": False, "message": f"Port in use by another process: {host}:{port}"}

            runtime_base_url = f"http://{host}:{port}"

            env = os.environ.copy()
            env.update(app.get("env", {}))
            if resolved_name == "productmix":
                env.setdefault("PM_HOST", host)
                env.setdefault("PM_PORT", str(port))
            elif resolved_name == "managerapp":
                env.setdefault("MGR_HOST", host)
                env.setdefault("MGR_PORT", str(port))
            elif resolved_name == "ic3":
                env.setdefault("IC3_HOST", host)
                env.setdefault("IC3_PORT", str(port))
            
            log_file = self._log_file(resolved_name)
            self._rotate_log(resolved_name)
            with log_file.open("a", encoding="utf-8") as lf:
                lf.write(f"\n=== START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

            stdout_stream = log_file.open("a", encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(entry)],
                cwd=str(cwd),
                env=env,
                stdout=stdout_stream,
                stderr=subprocess.STDOUT,
            )
            self._procs[resolved_name] = proc
            self._runtime_base_urls[resolved_name] = runtime_base_url
            return {"ok": True, "message": f"Started {resolved_name}", "pid": proc.pid, "base_url": runtime_base_url}

    def stop(self, name: str) -> dict[str, Any]:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return {"ok": False, "message": f"Unknown app: {name}"}

        with self._lock:
            proc = self._procs.get(resolved_name)
            if proc is None or proc.poll() is not None:
                self._procs[resolved_name] = None
                self._runtime_base_urls[resolved_name] = None
                return {"ok": True, "message": f"{resolved_name} already stopped"}

            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self._procs[resolved_name] = None
            self._runtime_base_urls[resolved_name] = None
            return {"ok": True, "message": f"Stopped {resolved_name}"}

    def restart(self, name: str) -> dict[str, Any]:
        self.stop(name)
        return self.start(name)

    def start_all(self) -> dict[str, Any]:
        preflight = self.preflight()
        if not preflight["ok"]:
            return {"ok": False, "message": "Preflight failed", "preflight": preflight}

        results = {name: self.start(name) for name in self.config["apps"].keys()}
        return {"ok": True, "results": results}

    def stop_all(self) -> dict[str, Any]:
        results = {name: self.stop(name) for name in self.config["apps"].keys()}
        return {"ok": True, "results": results}

    def start_watchdog(self, interval: int = 30) -> None:
        def _watch() -> None:
            while True:
                time.sleep(interval)
                for name in list(self.config["apps"].keys()):
                    proc = self._procs.get(name)
                    if proc is not None and proc.poll() is not None:
                        print(
                            f"[dexter watchdog] '{name}' has exited (rc={proc.returncode}). Restarting…",
                            file=sys.stderr,
                        )
                        try:
                            self.start(name)
                        except Exception as exc:  # noqa: BLE001
                            print(
                                f"[dexter watchdog] Failed to restart '{name}': {exc}",
                                file=sys.stderr,
                            )

        t = threading.Thread(target=_watch, name="dexter-watchdog", daemon=True)
        t.start()
        print("[dexter watchdog] Started — checking every %ds." % interval, file=sys.stderr)

CONFIG = load_config()
MANAGER = AppManager(CONFIG)
app = Flask(__name__, static_folder=None)
_secret = os.environ.get("DEXTER_SECRET_KEY") or os.environ.get("SECRET_KEY")
if not _secret:
    _secret = os.urandom(32)
    print(
        "[dexter] WARNING: DEXTER_SECRET_KEY env var not set. "
        "Using a random secret — all sessions will be invalidated on restart.",
        file=sys.stderr,
    )
app.secret_key = _secret
app.config["WTF_CSRF_SECRET_KEY"] = _secret
_session_hours = int(CONFIG.get("front_door", {}).get("session_hours", 8))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=_session_hours)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _env_flag("DEXTER_SESSION_COOKIE_SECURE", default=False)
app.config["SESSION_COOKIE_NAME"] = str(os.environ.get("DEXTER_SESSION_COOKIE_NAME", "dexter_session") or "dexter_session")
app.config["PREFERRED_URL_SCHEME"] = "https" if app.config["SESSION_COOKIE_SECURE"] else "http"
csrf = CSRFProtect(app)


# ----- Dexter UI brand injection -------------------------------------------
_DEXTER_UI_DIR = ROOT / "dexter-ui"

def _dexter_ui_static(filename: str):
    return send_file(_DEXTER_UI_DIR / filename, max_age=3600)

def _dexter_ui_brand(filename: str):
    return send_file(_DEXTER_UI_DIR / "brand" / filename, max_age=3600)

if _DEXTER_UI_DIR.exists():
    app.add_url_rule(
        "/dexter-ui/<path:filename>",
        endpoint="_dexter_ui_static",
        view_func=_dexter_ui_static,
    )
    app.add_url_rule(
        "/dexter-ui/brand/<path:filename>",
        endpoint="_dexter_ui_brand",
        view_func=_dexter_ui_brand,
    )

_DEXTER_UI_HEAD = (
    '<meta name="theme-color" content="#22427A">'
    '<link rel="icon" type="image/x-icon" href="/dexter-ui/brand/favicon.ico">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/dexter-ui/brand/favicon-32.png">'
    '<link rel="apple-touch-icon" sizes="180x180" href="/dexter-ui/brand/apple-touch-icon.png">'
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
    '<link rel="stylesheet" href="/dexter-ui/tokens.css">'
    '<link rel="stylesheet" href="/dexter-ui/components.css">'
    "<style>"
    "body{font-family:var(--dx-font-sans)!important;background:var(--dx-bg)!important;color:var(--dx-text)!important;}"
    ".navbar,header.navbar,nav.navbar{background:var(--dx-primary)!important;}"
    ".navbar-brand,.navbar a,.navbar .nav-link{color:var(--dx-primary-contrast)!important;}"
    ".btn-primary{background:var(--dx-primary)!important;border-color:var(--dx-primary)!important;color:var(--dx-primary-contrast)!important;}"
    ".btn-primary:hover{background:var(--dx-navy-2)!important;border-color:var(--dx-navy-2)!important;}"
    ".card,.panel,.box,.modal-content{background:var(--dx-surface)!important;color:var(--dx-text)!important;border-color:var(--dx-border-soft)!important;}"
    ".form-control,.form-select,input,select,textarea{background:var(--dx-surface)!important;color:var(--dx-text)!important;border-color:var(--dx-border-soft)!important;}"
    "</style>"
)
_DEXTER_UI_BODY = (
    '<script src="/dexter-ui/theme.js" defer></script>'
    '<div class="dx-version-badge" aria-hidden="true">Dexter · Launcher · v0.9-demo</div>'
)
_DEXTER_UI_MARKER = "__dexter_ui_installed"

@app.after_request
def _inject_dexter_ui(response: Response) -> Response:
    content_type = (response.content_type or "").lower()
    if "text/html" not in content_type:
        return response
    if response.direct_passthrough:
        response.direct_passthrough = False
    try:
        body = response.get_data(as_text=True)
    except UnicodeDecodeError:
        return response
    if _DEXTER_UI_MARKER in body:
        return response
    if "</head>" not in body and "</body>" not in body:
        return response

    updated = body
    if "</head>" in updated:
        updated = updated.replace(
            "</head>",
            _DEXTER_UI_HEAD + f'<meta name="dexter-ui" content="1" data-{_DEXTER_UI_MARKER}="1"></head>',
            1,
        )
    else:
        updated = _DEXTER_UI_HEAD + updated
    if "</body>" in updated:
        updated = updated.replace("</body>", _DEXTER_UI_BODY + "</body>", 1)
    else:
        updated = updated + _DEXTER_UI_BODY

    response.set_data(updated)
    if "Content-Length" in response.headers:
        response.headers["Content-Length"] = str(len(response.get_data()))
    return response

@app.after_request
def _apply_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'; object-src 'none'; base-uri 'self'")

    hsts_enabled = _env_flag("DEXTER_ENABLE_HSTS", default=False)
    if hsts_enabled and request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
# ----- /Dexter UI brand injection -------------------------------------------


def _rate_limit_key() -> str:
    dexter_user = (request.headers.get("X-Dexter-User") or "").strip().lower()
    if dexter_user:
        return f"dexter-user:{dexter_user}"
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded_for:
        return f"ip:{forwarded_for}"
    return f"ip:{get_remote_address()}"

limiter = Limiter(
    key_func=_rate_limit_key,
    app=app,
    default_limits=[],
)

initialize_rbac_db()
migrate_legacy_json_users_to_sqlite()
migrate_add_task_fields_v1()
migrate_add_password_reset_fields_v1()
migrate_add_company_scope_v1()
migrate_add_company_profiles_v1()
migrate_add_company_email_settings_v1()
migrate_add_login_lockout_fields_v1()
migrate_add_user_location_assignments_v1()
ensure_default_super_admin_user()

@app.before_request
def require_auth_for_protected_routes() -> Response | None:
    public_prefixes = (
        "/auth/login",
        "/auth/register",
        "/auth/forgot-password",
        "/auth/reset-password/",
        "/branding/logo",
        "/dexter-ui/",
        "/favicon.ico",
        "/api/health",
    )
    if request.path.startswith(public_prefixes):
        return None
    if session.get(SESSION_USER_KEY):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "message": "Authentication required"}), 401
    return redirect(url_for("auth_login", next=request.full_path.rstrip("?")))

@app.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def auth_login() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(default_post_login_path())

    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key, user = find_auth_user(username)
        if user and int(user.get("is_active", 1)) == 1 and is_user_locked_out(user):
            error = f"Account temporarily locked. Try again in {LOGIN_LOCKOUT_MINUTES} minutes."
        elif user and int(user.get("is_active", 1)) == 1 and check_password_hash(str(user.get("password_hash", "")), password):
            update_user_last_login(int(user["id"]))
            role_name = str(user.get("role_name") or "Employee")
            session[SESSION_USER_KEY] = {
                "username": key or username,
                "user_id": int(user["id"]),
                "role_name": role_name,
                "company_id": int(user["company_id"]) if user.get("company_id") is not None else None,
                "selected_company_id": int(user["company_id"]) if user.get("company_id") is not None else None,
                "selected_restaurant_id": None,
                "company_name": str(user.get("company_name") or ""),
                "is_admin": role_name == "Super Admin",
                "email": key or username,
            }
            session.permanent = True
            if role_name in ("Super Admin", "Manager"):
                MANAGER.start_all()
            return redirect(default_post_login_path())
        elif user and int(user.get("is_active", 1)) == 1:
            attempts, lockout_until = register_failed_login_attempt(int(user["id"]))
            if lockout_until is not None:
                error = f"Account temporarily locked. Try again in {LOGIN_LOCKOUT_MINUTES} minutes."
            else:
                remaining = max(0, MAX_FAILED_LOGIN_ATTEMPTS - attempts)
                if remaining > 0:
                    error = f"Invalid username or password. {remaining} attempts remaining before temporary lockout."
                else:
                    error = "Invalid username or password."
        elif user and int(user.get("is_active", 1)) != 1:
            error = "Invalid username or password."
        else:
            error = "Invalid username or password."

    return Response(
        render_template(
            "login.html",
            error=error,
            next_path=request.args.get("next", ""),
            action_url=url_for("auth_login"),
            register_url=url_for("auth_register"),
        )
    )

@app.route("/auth/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def auth_register() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(default_post_login_path())

    if not CONFIG.get("front_door", {}).get("registration_open", False):
        return Response(
            render_template(
                "register.html",
                error="Self-registration is currently disabled. Contact your administrator.",
                next_path="",
                action_url=url_for("auth_register"),
                login_url=url_for("auth_login"),
            )
        )

    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if len(username) < 3:
            error = "Username must be at least 3 characters."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            conn = get_rbac_db_connection()
            try:
                existing = conn.execute(
                    "SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
                    (username,),
                ).fetchone()
                if existing:
                    error = "Username already exists."
                else:
                    employee_role_id = _get_role_id(conn, "Employee")
                    default_company_id = ensure_default_company(conn)
                    cur = conn.execute(
                        """
                        INSERT INTO users (username, password_hash, role_id, company_id, is_active, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'))
                        """,
                        (username, generate_password_hash(password), employee_role_id, default_company_id),
                    )
                    conn.commit()
                    session[SESSION_USER_KEY] = {
                        "username": username,
                        "user_id": int(cur.lastrowid),
                        "role_name": "Employee",
                        "company_id": default_company_id,
                        "selected_company_id": default_company_id,
                        "selected_restaurant_id": None,
                        "company_name": "Default Company",
                        "is_admin": False,
                        "email": username,
                    }
                    session.permanent = True
                    return redirect(default_post_login_path())
            finally:
                conn.close()

    return Response(
        render_template(
            "register.html",
            error=error,
            next_path=request.args.get("next", ""),
            action_url=url_for("auth_register"),
            login_url=url_for("auth_login"),
        )
    )

@app.route("/auth/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def auth_forgot_password() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(default_post_login_path())

    error = ""
    reset_url = None
    success_message = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        if not username:
            error = "Please enter your username."
        else:
            conn = get_rbac_db_connection()
            try:
                row = conn.execute(
                    "SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND is_active = 1 LIMIT 1",
                    (username,),
                ).fetchone()
                if row:
                    token = secrets.token_urlsafe(32)
                    expires = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
                    conn.execute(
                        "UPDATE users SET password_reset_token = ?, password_reset_expires = ? WHERE id = ?",
                        (token, expires, int(row["id"])),
                    )
                    conn.commit()
                    base_url = _public_base_url()
                    reset_url = f"{base_url}/auth/reset-password/{token}"
                    if _is_email_like(username):
                        subject, text_body, html_body = _password_reset_email_payload(username, reset_url)
                        user_company_id = int(row["company_id"]) if row["company_id"] is not None else None
                        sent, send_message = send_email_message([username], subject, text_body, html_body, company_id=user_company_id)
                        if sent:
                            success_message = f"Password reset email sent to {username}."
                            reset_url = None
                        else:
                            error = f"Email could not be sent automatically. {send_message}"
                else:
                    error = "If that username exists, a reset link has been generated. Ask an admin."
            finally:
                conn.close()

    return Response(
        render_template(
            "forgot_password.html",
            error=error,
            reset_url=reset_url,
            success_message=success_message,
        )
    )

@app.route("/auth/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def auth_reset_password(token: str) -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(default_post_login_path())

    token = str(token or "").strip()
    error = ""
    done = False

    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT id, password_reset_expires FROM users
            WHERE password_reset_token = ? AND is_active = 1
            LIMIT 1
            """,
            (token,),
        ).fetchone()

        if not row:
            return Response(
                render_template("reset_password.html", error="Invalid or expired reset link.", done=False)
            )

        expires_str = str(row["password_reset_expires"] or "")
        try:
            expires_dt = datetime.fromisoformat(expires_str)
        except ValueError:
            expires_dt = datetime.min

        if datetime.now() > expires_dt:
            conn.execute(
                "UPDATE users SET password_reset_token = NULL, password_reset_expires = NULL WHERE id = ?",
                (int(row["id"]),),
            )
            conn.commit()
            return Response(
                render_template("reset_password.html", error="Reset link has expired. Please request a new one.", done=False)
            )

        if request.method == "POST":
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm") or ""
            if len(password) < 8:
                error = "Password must be at least 8 characters."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?,
                        password_reset_token = NULL,
                        password_reset_expires = NULL,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (generate_password_hash(password), int(row["id"])),
                )
                conn.commit()
                done = True
    finally:
        conn.close()

    return Response(render_template("reset_password.html", error=error, done=done))

@app.route("/auth/logout", methods=["POST", "GET"])
def auth_logout() -> Response:
    session.pop(SESSION_USER_KEY, None)
    return redirect(url_for("auth_login"))

@app.route("/favicon.ico")
def front_door_favicon() -> Response:
    if FRONT_DOOR_FAVICON.exists():
        return send_file(FRONT_DOOR_FAVICON, mimetype="image/svg+xml", max_age=3600)
    return jsonify({"ok": False, "message": "Not found"}), 404

@app.route("/branding/logo")
def branding_logo() -> Response:
    return _default_branding_logo_response()

def _default_branding_logo_response() -> Response:
    if BRANDING_LOGO_PATH.exists():
        return send_file(BRANDING_LOGO_PATH, mimetype="image/png", max_age=3600)
    if LEGACY_BRANDING_LOGO_PATH.exists():
        return send_file(LEGACY_BRANDING_LOGO_PATH, mimetype="image/png", max_age=3600)
    if FRONT_DOOR_FAVICON.exists():
        return send_file(FRONT_DOOR_FAVICON, mimetype="image/svg+xml", max_age=3600)
    return jsonify({"ok": False, "message": "Not found"}), 404

@app.route("/branding/company-logo")
@login_required
def branding_company_logo() -> Response:
    selected_company_id = _effective_company_scope(require_active=True)
    if selected_company_id is None:
        return _default_branding_logo_response()

    profile = get_company_profile(int(selected_company_id))
    logo_rel_path = str((profile or {}).get("logo_rel_path") or "").strip()
    if not logo_rel_path:
        return _default_branding_logo_response()

    logo_path = _resolve_company_storage_path(int(selected_company_id), logo_rel_path)
    if logo_path is None or not logo_path.exists() or not logo_path.is_file():
        return _default_branding_logo_response()

    return send_file(logo_path, as_attachment=False, download_name=logo_path.name, max_age=300)

@app.route("/")
@login_required
def index() -> str:
    referer = request.headers.get("Referer", "")
    if "/app/productmix/" in referer or "/portal/productmix" in referer:
        return _proxy("productmix", "")

    return redirect("/portal/managerapp")

@app.route("/admin")
@login_required
def admin() -> str:
    if current_role_name() == "Super Admin":
        return redirect("/admin/users")
    return redirect("/admin/company-profile")

def _effective_company_scope(require_active: bool = True) -> int | None:
    role_name = current_role_name()
    if role_name != "Super Admin":
        return current_user_company_id()

    role_name = current_role_name()
    user_company_id = current_user_company_id()

    if role_name != "Super Admin":
        if user_company_id is not None:
            company_row = _get_company_by_id(int(user_company_id), require_active=require_active)
            if company_row:
                _set_session_company_context(int(company_row["id"]), str(company_row["name"]))
                return int(company_row["id"])
        _set_session_company_context(None, "")
        return None

    selected_company_id = current_selected_company_id() or user_company_id
    if selected_company_id is not None:
        company_row = _get_company_by_id(int(selected_company_id), require_active=require_active)
        if company_row:
            _set_session_company_context(int(company_row["id"]), str(company_row["name"]))
            return int(company_row["id"])

    fallback = _first_active_company() if require_active else None
    if fallback:
        _set_session_company_context(int(fallback["id"]), str(fallback["name"]))
        return int(fallback["id"])

    _set_session_company_context(None, "")
    return None

@app.route("/admin/company-scope", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_company_scope_switch() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    target_company_id = _normalize_company_id(request.form.get("company_id"))
    if target_company_id is None:
        return redirect("/admin/users?error=Invalid+company+selection")

    target_company = _get_company_by_id(int(target_company_id), require_active=True)
    if not target_company:
        return redirect("/admin/users?error=Selected+company+is+not+active+or+does+not+exist")

    previous_company_id = _effective_company_scope(require_active=False)
    _set_session_company_context(int(target_company["id"]), str(target_company["name"]))
    _effective_selected_restaurant_id_for_scope(int(target_company["id"]), ensure_default=True)

    add_audit_log(
        int(actor_id),
        "switch_company_scope",
        "companies",
        int(target_company["id"]),
        json.dumps(
            {
                "from_company_id": previous_company_id,
                "to_company_id": int(target_company["id"]),
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_agent": request.headers.get("User-Agent", ""),
            }
        ),
        company_id=int(target_company["id"]),
    )

    next_path = str(request.form.get("next_path") or "").strip()
    if next_path.startswith("/") and not next_path.startswith("//"):
        separator = "&" if "?" in next_path else "?"
        return redirect(f"{next_path}{separator}company_switched=1")
    return redirect(default_company_switch_path())

@app.route("/api/admin/company-scope", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin")
def api_admin_company_scope_switch() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    payload = request.get_json(silent=True) or {}
    target_company_id = _normalize_company_id(payload.get("company_id"))
    if target_company_id is None:
        return jsonify({"ok": False, "message": "Invalid company selection"}), 400

    target_company = _get_company_by_id(int(target_company_id), require_active=True)
    if not target_company:
        return jsonify({"ok": False, "message": "Selected company is not active or does not exist"}), 400

    previous_company_id = _effective_company_scope(require_active=False)
    _set_session_company_context(int(target_company["id"]), str(target_company["name"]))
    _effective_selected_restaurant_id_for_scope(int(target_company["id"]), ensure_default=True)

    add_audit_log(
        int(actor_id),
        "switch_company_scope",
        "companies",
        int(target_company["id"]),
        json.dumps(
            {
                "from_company_id": previous_company_id,
                "to_company_id": int(target_company["id"]),
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_agent": request.headers.get("User-Agent", ""),
                "api": True,
            }
        ),
        company_id=int(target_company["id"]),
    )

    return jsonify(
        {
            "ok": True,
            "company": {
                "id": int(target_company["id"]),
                "name": str(target_company["name"]),
                "slug": str(target_company["slug"]),
            },
            "redirect_to": default_company_switch_path(),
        }
    )

@app.route("/admin/location-scope", methods=["POST"])
@login_required
def admin_location_scope_switch() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/?error=Session+expired")

    selected_company_id = _effective_company_scope(require_active=True)
    if selected_company_id is None:
        return redirect("/?error=No+active+company+scope+is+selected")

    target_restaurant_id = _normalize_proxy_location_id(request.form.get("restaurant_id"))
    available_options = _effective_restaurant_options_for_scope(int(selected_company_id))
    available_ids = {int(item["id"]) for item in available_options}
    if target_restaurant_id is None or int(target_restaurant_id) not in available_ids:
        return redirect("/?error=Invalid+location+selection")

    previous_restaurant_id = current_selected_restaurant_id()
    _set_session_selected_restaurant_context(int(target_restaurant_id))

    add_audit_log(
        int(actor_id),
        "switch_location_scope",
        "restaurants",
        int(target_restaurant_id),
        json.dumps(
            {
                "from_restaurant_id": previous_restaurant_id,
                "to_restaurant_id": int(target_restaurant_id),
                "company_id": int(selected_company_id),
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_agent": request.headers.get("User-Agent", ""),
            }
        ),
        company_id=int(selected_company_id),
    )

    next_path = str(request.form.get("next_path") or "").strip()
    if next_path.startswith("/") and not next_path.startswith("//"):
        separator = "&" if "?" in next_path else "?"
        return redirect(f"{next_path}{separator}location_switched=1")
    return redirect(default_location_switch_path())

@app.route("/api/admin/location-scope", methods=["PATCH"])
@csrf.exempt
@login_required
def api_admin_location_scope_switch() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    selected_company_id = _effective_company_scope(require_active=True)
    if selected_company_id is None:
        return jsonify({"ok": False, "message": "No active company scope is selected"}), 403

    payload = request.get_json(silent=True) or {}
    target_restaurant_id = _normalize_proxy_location_id(payload.get("restaurant_id"))
    available_options = _effective_restaurant_options_for_scope(int(selected_company_id))
    available_by_id = {int(item["id"]): item for item in available_options}
    if target_restaurant_id is None or int(target_restaurant_id) not in available_by_id:
        return jsonify({"ok": False, "message": "Invalid location selection"}), 400

    previous_restaurant_id = current_selected_restaurant_id()
    _set_session_selected_restaurant_context(int(target_restaurant_id))

    add_audit_log(
        int(actor_id),
        "switch_location_scope",
        "restaurants",
        int(target_restaurant_id),
        json.dumps(
            {
                "from_restaurant_id": previous_restaurant_id,
                "to_restaurant_id": int(target_restaurant_id),
                "company_id": int(selected_company_id),
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_agent": request.headers.get("User-Agent", ""),
                "api": True,
            }
        ),
        company_id=int(selected_company_id),
    )

    restaurant = available_by_id[int(target_restaurant_id)]
    return jsonify(
        {
            "ok": True,
            "restaurant": {
                "id": int(restaurant["id"]),
                "name": str(restaurant.get("name") or "").strip(),
                "location": str(restaurant.get("location") or "").strip(),
                "label": str(restaurant.get("label") or "").strip(),
            },
            "redirect_to": default_location_switch_path(),
        }
    )

@app.route("/admin/companies")
@login_required
@role_required("Super Admin")
def admin_companies_page() -> Response:
    return Response(
        render_template(
            "admin_companies.html",
            companies=list_companies(),
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/companies/create", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_companies_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/companies?error=Session+expired")

    ok, msg = create_company(actor_id, request.form.get("name") or "")
    key = "message" if ok else "error"
    return redirect(f"/admin/companies?{key}={requests.utils.quote(msg)}")

@app.route("/admin/companies/<int:company_id>/rename", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_companies_rename(company_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/companies?error=Session+expired")

    ok, msg = rename_company(actor_id, int(company_id), request.form.get("name") or "")
    key = "message" if ok else "error"
    return redirect(f"/admin/companies?{key}={requests.utils.quote(msg)}")

@app.route("/admin/companies/<int:company_id>/active", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_companies_active(company_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/companies?error=Session+expired")

    is_active = str(request.form.get("is_active", "1")).strip() == "1"
    ok, msg = set_company_active_state(actor_id, int(company_id), is_active)
    key = "message" if ok else "error"
    return redirect(f"/admin/companies?{key}={requests.utils.quote(msg)}")

@app.route("/admin/company-health")
@login_required
@role_required("Super Admin")
def admin_company_health_page() -> Response:
    companies = list_company_health()
    summary = {
        "total_companies": len(companies),
        "active_companies": sum(1 for c in companies if int(c.get("is_active", 0)) == 1),
        "total_users": sum(int(c.get("total_users", 0)) for c in companies),
        "open_tasks": sum(int(c.get("open_tasks", 0)) for c in companies),
    }
    return Response(render_template("admin_company_health.html", companies=companies, summary=summary))

@app.route("/admin/email")
@login_required
@role_required("Super Admin", "Manager")
def admin_email_page() -> Response:
    is_super_admin = current_role_name() == "Super Admin"
    companies = list_companies(active_only=True) if is_super_admin else []
    selected_company_id = _effective_company_scope()
    if is_super_admin and selected_company_id is None and companies:
        selected_company_id = int(companies[0]["id"])

    preferred_target = ""
    if selected_company_id is not None:
        profile = get_company_profile(int(selected_company_id)) or {}
        preferred_target = str(profile.get("contact_email") or "").strip()

    session_username = str((session.get(SESSION_USER_KEY) or {}).get("username") or "").strip()
    if not preferred_target and _is_email_like(session_username):
        preferred_target = session_username
    company_mail = _company_email_preferences(selected_company_id)

    return Response(
        render_template(
            "admin_email.html",
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
            preferred_target=preferred_target,
            mail_status=_mail_delivery_status(),
            company_mail=company_mail,
            public_base_url=_public_base_url(),
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/email/settings", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_email_settings_save() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/email?error=Session+expired")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/email?error={requests.utils.quote(scope_error)}")
    if selected_company_id is None:
        return redirect("/admin/email?error=No+active+company+scope+is+selected")

    existing_profile = get_company_profile(int(selected_company_id))
    if not existing_profile:
        return redirect("/admin/email?error=Company+profile+is+not+available")

    profile_payload = dict(existing_profile)
    profile_payload.update(
        {
            "email_enabled": request.form.get("email_enabled", "0"),
            "email_from_name": request.form.get("email_from_name", ""),
            "email_reply_to": request.form.get("email_reply_to", ""),
            "daily_log_email_enabled": request.form.get("daily_log_email_enabled", "0"),
            "daily_log_email_recipients": request.form.get("daily_log_email_recipients", ""),
            "daily_log_email_time": request.form.get("daily_log_email_time", "01:00"),
        }
    )
    upsert_company_profile(int(selected_company_id), profile_payload)
    add_audit_log(
        int(actor_id),
        "update_company_email_settings",
        "companies",
        int(selected_company_id),
        json.dumps(
            {
                "email_enabled": 1 if str(request.form.get("email_enabled", "0")).strip() in {"1", "true", "yes", "on"} else 0,
                "email_from_name": str(request.form.get("email_from_name", "") or "").strip(),
                "email_reply_to": str(request.form.get("email_reply_to", "") or "").strip(),
                "daily_log_email_enabled": 1 if str(request.form.get("daily_log_email_enabled", "0")).strip() in {"1", "true", "yes", "on"} else 0,
                "daily_log_email_recipients": str(request.form.get("daily_log_email_recipients", "") or "").strip(),
                "daily_log_email_time": str(request.form.get("daily_log_email_time", "01:00") or "01:00").strip(),
            }
        ),
        company_id=int(selected_company_id),
    )
    return redirect("/admin/email?message=Company+email+settings+saved")

@app.route("/admin/email/test", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_email_test() -> Response:
    target_email = str(request.form.get("target_email") or "").strip()
    if not _is_email_like(target_email):
        return redirect("/admin/email?error=Enter+a+valid+recipient+email")

    selected_company_id = _effective_company_scope()

    public_url = _public_base_url()
    subject = "Dexter Assist email test"
    text_body = (
        "This is a test email from Dexter Assist.\n\n"
        f"Base URL: {public_url}\n"
        f"Triggered at: {datetime.now().isoformat(timespec='seconds')}\n"
    )
    html_body = (
        "<p>This is a test email from Dexter Assist.</p>"
        f"<p><strong>Base URL:</strong> {public_url}<br>"
        f"<strong>Triggered at:</strong> {datetime.now().isoformat(timespec='seconds')}</p>"
    )
    sent, message = send_email_message([target_email], subject, text_body, html_body, company_id=selected_company_id)
    key = "message" if sent else "error"
    return redirect(f"/admin/email?{key}={requests.utils.quote(message)}")

@app.route("/admin/company-profile")
@login_required
@role_required("Super Admin", "Manager")
def admin_company_profile_page() -> Response:
    selected_company_id = _effective_company_scope()
    if selected_company_id is None:
        return redirect("/admin/users?error=No+active+company+scope+is+selected")

    profile = get_company_profile(int(selected_company_id))
    if not profile:
        return redirect("/admin/users?error=Company+profile+is+not+available")

    is_super_admin = current_role_name() == "Super Admin"
    companies = list_companies(active_only=True) if is_super_admin else []
    return Response(
        render_template(
            "admin_company_profile.html",
            profile=profile,
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/company-profile", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_company_profile_save() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/company-profile?error=Session+expired")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/company-profile?error={requests.utils.quote(scope_error)}")
    if selected_company_id is None:
        return redirect("/admin/company-profile?error=No+active+company+scope+is+selected")

    existing_profile = get_company_profile(int(selected_company_id))
    if not existing_profile:
        return redirect("/admin/company-profile?error=Company+profile+is+not+available")

    logo_rel_path = str(existing_profile.get("logo_rel_path") or "")
    clear_logo = str(request.form.get("clear_logo", "0")).strip() == "1"
    uploaded_logo = request.files.get("logo_file")

    if clear_logo and logo_rel_path:
        existing_logo_path = _resolve_company_storage_path(int(selected_company_id), logo_rel_path)
        if existing_logo_path is not None and existing_logo_path.exists() and existing_logo_path.is_file():
            try:
                existing_logo_path.unlink()
            except Exception:
                pass
        logo_rel_path = ""

    if uploaded_logo and str(getattr(uploaded_logo, "filename", "") or "").strip():
        ok, err_message, saved_rel_path = _save_company_logo(int(selected_company_id), uploaded_logo)
        if not ok:
            return redirect(f"/admin/company-profile?error={requests.utils.quote(err_message)}")
        logo_rel_path = saved_rel_path

    profile_payload = {
        "contact_email": request.form.get("contact_email", ""),
        "contact_phone": request.form.get("contact_phone", ""),
        "website": request.form.get("website", ""),
        "address_line1": request.form.get("address_line1", ""),
        "address_line2": request.form.get("address_line2", ""),
        "city": request.form.get("city", ""),
        "state_region": request.form.get("state_region", ""),
        "postal_code": request.form.get("postal_code", ""),
        "country": request.form.get("country", ""),
        "tax_id": request.form.get("tax_id", ""),
        "notes": request.form.get("notes", ""),
        "logo_rel_path": logo_rel_path,
    }
    upsert_company_profile(int(selected_company_id), profile_payload)

    add_audit_log(
        int(actor_id),
        "update_company_profile",
        "companies",
        int(selected_company_id),
        json.dumps({"logo_updated": bool(logo_rel_path), "cleared_logo": clear_logo}),
        company_id=int(selected_company_id),
    )

    return redirect("/admin/company-profile?message=Company+profile+saved")

@app.route("/admin/company-profile/logo")
@login_required
@role_required("Super Admin", "Manager")
def admin_company_profile_logo() -> Response:
    selected_company_id = _effective_company_scope()
    if selected_company_id is None:
        return Response("Company scope unavailable", status=404)

    profile = get_company_profile(int(selected_company_id))
    if not profile:
        return Response("Company profile unavailable", status=404)

    logo_rel_path = str(profile.get("logo_rel_path") or "").strip()
    if not logo_rel_path:
        return Response("Logo not found", status=404)

    logo_path = _resolve_company_storage_path(int(selected_company_id), logo_rel_path)
    if logo_path is None or not logo_path.exists() or not logo_path.is_file():
        return Response("Logo not found", status=404)

    return send_file(logo_path, as_attachment=False, download_name=logo_path.name)

@app.route("/admin/users")
@login_required
@role_required("Super Admin", "Manager")
def admin_users_page() -> Response:
    is_super_admin = current_role_name() == "Super Admin"
    companies = list_companies(active_only=True) if is_super_admin else []
    selected_company_id = _effective_company_scope()
    if is_super_admin and selected_company_id is None and companies:
        selected_company_id = int(companies[0]["id"])
    available_locations = _list_restaurants_for_company_id(selected_company_id)

    return Response(
        render_template(
            "admin_users.html",
            users=list_users_with_roles(company_id=selected_company_id),
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
            available_locations=available_locations,
            mail_status=_mail_delivery_status(),
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/users/invite", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_invite() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    invite_email = str(request.form.get("email") or "").strip().lower()
    role_name = str(request.form.get("role_name") or "Employee").strip()
    if not _is_email_like(invite_email):
        return redirect("/admin/users?error=Enter+a+valid+email+address")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")

    temp_password = secrets.token_urlsafe(18)
    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=invite_email,
        password=temp_password,
        role_name=role_name,
        company_id=selected_company_id,
        assigned_restaurant_ids=request.form.getlist("restaurant_ids"),
    )
    if not ok:
        return redirect(f"/admin/users?error={requests.utils.quote(msg)}")

    conn = get_rbac_db_connection()
    try:
        row = conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1", (invite_email,)).fetchone()
        if not row:
            return redirect("/admin/users?error=User+created+but+invite+token+could+not+be+prepared")
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(hours=48)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE users SET password_reset_token = ?, password_reset_expires = ?, updated_at = datetime('now') WHERE id = ?",
            (token, expires, int(row["id"])),
        )
        conn.commit()
    finally:
        conn.close()

    setup_url = f"{_public_base_url()}/auth/reset-password/{token}"
    subject, text_body, html_body = _account_invite_email_payload(invite_email, role_name, setup_url)
    sent, send_message = send_email_message([invite_email], subject, text_body, html_body, company_id=selected_company_id)
    if sent:
        return redirect(f"/admin/users?message={requests.utils.quote(f'Invitation sent to {invite_email}.')}")
    return redirect(
        f"/admin/users?error={requests.utils.quote(f'User created, but invite email could not be sent. {send_message}')}"
    )

@app.route("/admin/users/<int:user_id>/resend-invite", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_resend_invite(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")

    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT
                u.id,
                u.username,
                u.is_active,
                COALESCE(r.name, 'Employee') AS role_name,
                u.company_id
            FROM users u
            LEFT JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        if not row:
            return redirect("/admin/users?error=User+not+found")

        target_company_id = int(row["company_id"]) if row["company_id"] is not None else None
        if current_role_name() == "Super Admin":
            scope_error = _ensure_target_in_super_admin_scope(target_company_id, "user")
            if scope_error:
                return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")
        elif target_company_id is not None and selected_company_id is not None and int(target_company_id) != int(selected_company_id):
            return redirect("/admin/users?error=You+can+only+resend+invites+for+the+selected+company")

        invite_email = str(row["username"] or "").strip().lower()
        if not _is_email_like(invite_email):
            return redirect("/admin/users?error=This+user+does+not+have+an+email+login+for+invites")

        if int(row["is_active"] or 0) != 1:
            return redirect("/admin/users?error=Activate+the+user+before+sending+an+invite")

        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(hours=48)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE users SET password_reset_token = ?, password_reset_expires = ?, updated_at = datetime('now') WHERE id = ?",
            (token, expires, int(user_id)),
        )
        conn.commit()
    finally:
        conn.close()

    role_name = str(row["role_name"] or "Employee").strip() or "Employee"
    setup_url = f"{_public_base_url()}/auth/reset-password/{token}"
    subject, text_body, html_body = _account_invite_email_payload(invite_email, role_name, setup_url)
    send_company_id = target_company_id if target_company_id is not None else selected_company_id
    sent, send_message = send_email_message([invite_email], subject, text_body, html_body, company_id=send_company_id)
    if sent:
        return redirect(f"/admin/users?message={requests.utils.quote(f'Invitation resent to {invite_email}.')}")
    return redirect(f"/admin/users?error={requests.utils.quote(f'Invite could not be sent. {send_message}')}")

@app.route("/admin/users/create", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")

    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=(request.form.get("username") or ""),
        password=(request.form.get("password") or ""),
        role_name=(request.form.get("role_name") or "Employee"),
        company_id=selected_company_id,
        assigned_restaurant_ids=request.form.getlist("restaurant_ids"),
    )
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")

@app.route("/admin/users/<int:user_id>/active", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_active(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")

    is_active = str(request.form.get("is_active", "1")).strip() == "1"
    ok, msg = set_user_active_state(actor_id, int(user_id), is_active)
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")

@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_role(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")

    role_name = str(request.form.get("role_name") or "Employee").strip()
    ok, msg = set_user_role_name(actor_id, int(user_id), role_name)
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")

@app.route("/admin/users/<int:user_id>/locations", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_locations(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return redirect(f"/admin/users?error={requests.utils.quote(scope_error)}")

    ok, msg = set_user_location_assignments(actor_id, int(user_id), request.form.getlist("restaurant_ids"))
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")

@app.route("/admin/tasks")
@login_required
@role_required("Super Admin", "Manager")
def admin_tasks_page() -> Response:
    is_super_admin = current_role_name() == "Super Admin"
    companies = list_companies(active_only=True) if is_super_admin else []
    selected_company_id = _effective_company_scope()
    if is_super_admin and selected_company_id is None and companies:
        selected_company_id = int(companies[0]["id"])

    status_filter = (request.args.get("status") or "").strip().lower() or None
    if status_filter not in {None, "pending", "in-progress", "completed"}:
        status_filter = None
    users = [u for u in list_users_with_roles(company_id=selected_company_id) if int(u.get("is_active", 0)) == 1]
    return Response(
        render_template(
            "admin_tasks.html",
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
            active_users=users,
            tasks=list_tasks(status_filter=status_filter, company_id=selected_company_id),
            status_filter=status_filter,
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/tasks/create", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_tasks_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/tasks?error=Session+expired")

    assigned_to_raw = (request.form.get("assigned_to") or "").strip()
    assigned_to = int(assigned_to_raw) if assigned_to_raw.isdigit() else None
    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/tasks?error={requests.utils.quote(scope_error)}")

    ok, msg = create_task_record(
        actor_user_id=actor_id,
        title=(request.form.get("title") or ""),
        description=(request.form.get("description") or ""),
        assigned_to=assigned_to,
        due_date=(request.form.get("due_date") or "").strip() or None,
        priority=(request.form.get("priority") or "normal"),
        company_id=selected_company_id,
    )
    key = "message" if ok else "error"
    status_filter = (request.args.get("status") or request.form.get("status") or "").strip().lower()
    status_qs = f"&status={status_filter}" if status_filter in {"pending", "in-progress", "completed"} else ""
    return redirect(f"/admin/tasks?{key}={requests.utils.quote(msg)}{status_qs}")

@app.route("/admin/audit-logs")
@login_required
@role_required("Super Admin", "Manager")
def admin_audit_logs_page() -> Response:
    is_super_admin = current_role_name() == "Super Admin"
    companies = list_companies(active_only=True) if is_super_admin else []
    selected_company_id = _effective_company_scope()
    if is_super_admin and selected_company_id is None and companies:
        selected_company_id = int(companies[0]["id"])
    return Response(
        render_template(
            "admin_audit.html",
            logs=list_audit_logs(company_id=selected_company_id, viewer_role=current_role_name()),
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
        )
    )

@app.route("/api/admin/users", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_users_list() -> Response:
    selected_company_id = _effective_company_scope()
    return jsonify({"ok": True, "users": list_users_with_roles(company_id=selected_company_id)})

@app.route("/api/admin/users", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_users_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    mutation_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return jsonify({"ok": False, "message": scope_error}), 403

    payload = request.get_json(silent=True) or {}
    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=str(payload.get("username") or ""),
        password=str(payload.get("password") or ""),
        role_name=str(payload.get("role_name") or "Employee"),
        company_id=mutation_company_id,
        assigned_restaurant_ids=payload.get("restaurant_ids") or payload.get("assigned_restaurant_ids"),
    )
    code = _api_status_from_outcome(ok, msg)
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/admin/users/<int:user_id>/role", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_users_role(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return jsonify({"ok": False, "message": scope_error}), 403

    payload = request.get_json(silent=True) or {}
    ok, msg = set_user_role_name(actor_id, int(user_id), str(payload.get("role_name") or ""))
    code = _api_status_from_outcome(ok, msg)
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/admin/users/<int:user_id>/active", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_users_active(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return jsonify({"ok": False, "message": scope_error}), 403

    payload = request.get_json(silent=True) or {}
    value = payload.get("is_active", True)
    is_active = bool(value)
    ok, msg = set_user_active_state(actor_id, int(user_id), is_active)
    code = _api_status_from_outcome(ok, msg)
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/admin/users/<int:user_id>/locations", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_users_locations(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return jsonify({"ok": False, "message": scope_error}), 403

    payload = request.get_json(silent=True) or {}
    ok, msg = set_user_location_assignments(
        actor_id,
        int(user_id),
        payload.get("restaurant_ids") or payload.get("assigned_restaurant_ids"),
    )
    code = _api_status_from_outcome(ok, msg)
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/admin/tasks", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tasks_list() -> Response:
    return jsonify({"ok": True, "tasks": list_tasks(company_id=_effective_company_scope())})

@app.route("/api/admin/tasks", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tasks_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    mutation_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return jsonify({"ok": False, "message": scope_error}), 403

    payload = request.get_json(silent=True) or {}
    assigned_to = payload.get("assigned_to")
    assigned_to_id = int(assigned_to) if str(assigned_to or "").isdigit() else None
    ok, msg = create_task_record(
        actor_user_id=actor_id,
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        assigned_to=assigned_to_id,
        due_date=str(payload.get("due_date") or "").strip() or None,
        priority=str(payload.get("priority") or "normal"),
        company_id=mutation_company_id,
    )
    code = _api_status_from_outcome(ok, msg)
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/admin/tasks/<int:task_id>/status", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tasks_status(task_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_task(int(task_id)), "task")
        if scope_error:
            return jsonify({"ok": False, "message": scope_error}), 403

    payload = request.get_json(silent=True) or {}
    ok, msg = update_task_status(actor_id, int(task_id), str(payload.get("status") or ""))
    code = _api_status_from_outcome(ok, msg)
    return jsonify({"ok": ok, "message": msg}), code

@app.route("/api/admin/audit-logs", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_audit_logs() -> Response:
    return jsonify({"ok": True, "audit_logs": list_audit_logs(company_id=_effective_company_scope(), viewer_role=current_role_name())})

@app.route("/api/admin/company-files", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_company_files() -> Response:
    selected_company_id = _effective_company_scope()
    if selected_company_id is None:
        return jsonify({"ok": False, "message": "No active company scope is selected"}), 403

    relative_dir = str(request.args.get("path") or "").strip()
    entries = _list_company_storage_entries(int(selected_company_id), relative_dir=relative_dir)
    if relative_dir and not entries:
        resolved = _resolve_company_storage_path(int(selected_company_id), relative_dir)
        if resolved is None:
            return jsonify({"ok": False, "message": "Forbidden path"}), 403

    return jsonify(
        {
            "ok": True,
            "company_id": int(selected_company_id),
            "path": relative_dir,
            "entries": entries,
        }
    )

@app.route("/api/admin/company-files/download", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_company_file_download() -> Response:
    selected_company_id = _effective_company_scope()
    if selected_company_id is None:
        return jsonify({"ok": False, "message": "No active company scope is selected"}), 403

    relative_path = str(request.args.get("path") or "").strip()
    if not relative_path:
        return jsonify({"ok": False, "message": "Path is required"}), 400

    resolved = _resolve_company_storage_path(int(selected_company_id), relative_path)
    if resolved is None:
        return jsonify({"ok": False, "message": "Forbidden path"}), 403
    if not resolved.exists() or not resolved.is_file():
        return jsonify({"ok": False, "message": "File not found"}), 404

    return send_file(resolved, as_attachment=True, download_name=resolved.name)

@app.route("/portal")
@login_required
def portal_home() -> str:
    fd = CONFIG.get("front_door", {})
    role_name = current_role_name()
    selected_company_id = _effective_company_scope(require_active=True)
    company_options: list[dict[str, Any]] = []
    if role_name == "Super Admin":
        company_options = list_companies(active_only=True)
    elif selected_company_id is not None:
        company = _get_company_by_id(int(selected_company_id), require_active=True)
        if company:
            company_options = [
                {
                    "id": int(company["id"]),
                    "name": str(company["name"]),
                    "slug": str(company["slug"]),
                    "is_active": int(company["is_active"]),
                }
            ]

    location_options = _effective_restaurant_options_for_scope(selected_company_id)
    selected_restaurant_id = _effective_selected_restaurant_id_for_scope(selected_company_id, ensure_default=True)
    selected_restaurant = None
    if selected_restaurant_id is not None:
        for option in location_options:
            if int(option["id"]) == int(selected_restaurant_id):
                selected_restaurant = option
                break

    return render_template(
        "portal_home.html",
        host=fd.get("host", "127.0.0.1"),
        port=fd.get("port", 5080),
        role_name=role_name,
        company_options=company_options,
        selected_company_id=selected_company_id,
        location_options=location_options,
        selected_restaurant_id=selected_restaurant_id,
        selected_restaurant=selected_restaurant,
        selected_company_name=str((session.get(SESSION_USER_KEY) or {}).get("company_name") or "").strip(),
        company_switched=(request.args.get("company_switched") or "").strip().lower() in {"1", "true", "yes"},
        location_switched=(request.args.get("location_switched") or "").strip().lower() in {"1", "true", "yes"},
    )

@app.route("/portal/<name>")
@login_required
def portal_app(name: str) -> Response:
    resolved_name = MANAGER.resolve_name(name)
    if not resolved_name:
        return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

    MANAGER.start(resolved_name)
    app_cfg = CONFIG["apps"][resolved_name]
    switched = (request.args.get("company_switched") or "").strip().lower() in {"1", "true", "yes"}
    location_switched = (request.args.get("location_switched") or "").strip().lower() in {"1", "true", "yes"}
    raw_url = "/app/managerapp/" if resolved_name == "managerapp" else f"/app/{resolved_name}/"
    show_shell_nav = resolved_name != "managerapp"
    selected_restaurant = _selected_restaurant_record_for_scope(_effective_company_scope(require_active=True))
    selected_company_name = str((session.get(SESSION_USER_KEY) or {}).get("company_name") or "").strip()
    current_location_name = str(
        (selected_restaurant or {}).get("label")
        or (selected_restaurant or {}).get("name")
        or app_cfg["display_name"]
    ).strip()
    switch_notice = ""
    if switched:
        separator = "&" if "?" in raw_url else "?"
        raw_url = f"{raw_url}{separator}company_switched=1&t={int(time.time())}"
        current_company_name = str((session.get(SESSION_USER_KEY) or {}).get("company_name") or "").strip()
        switch_notice = f"Switched to {current_company_name or 'the selected company'}. App reloaded to landing page."
    elif location_switched:
        separator = "&" if "?" in raw_url else "?"
        raw_url = f"{raw_url}{separator}location_switched=1&t={int(time.time())}"
        switch_notice = f"Switched to {current_location_name or 'the selected location'}. App reloaded to landing page."
    display_title = current_location_name if resolved_name == "managerapp" else app_cfg["display_name"]
    home_target = "/portal/managerapp" if resolved_name == "managerapp" else "/portal"
    return render_template(
        "portal_app.html",
        app_key=resolved_name,
        app_title=display_title,
        home_target=home_target,
        raw_url=raw_url,
        switch_notice=switch_notice,
        show_shell_nav=show_shell_nav,
        selected_company_name=selected_company_name,
        current_location_name=current_location_name,
    )

@app.route("/productmix")
@login_required
def portal_productmix_alias() -> Response:
    return redirect("/portal/productmix")

@app.route("/inventory")
@login_required
def portal_ic3_alias() -> Response:
    return redirect("/portal/ic3")

@app.route("/manager")
@login_required
def portal_manager_alias() -> Response:
    return redirect("/portal/managerapp")

@app.route("/api/health")
def api_health() -> Response:
    return jsonify({"ok": True})

@app.route("/api/status")
@login_required
def api_status() -> Response:
    return jsonify({"apps": MANAGER.status(), "preflight": MANAGER.preflight()})

@app.route("/api/admin/tenant-scope-audit", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tenant_scope_audit() -> Response:
    payload = _run_tenant_scope_audit(app)
    status_code = 200 if payload.get("ok") else 500
    return jsonify(payload), status_code

def _selected_company_name_for_scope() -> str:
    selected_company_id = _effective_company_scope(require_active=True)
    if selected_company_id is None:
        return ""
    selected_company = _get_company_by_id(int(selected_company_id), require_active=True)
    if not selected_company:
        return ""
    return str(selected_company["name"] or "").strip()

def _company_scoped_restaurant_ids_for_proxy() -> set[int] | None:
    pm_db_path = _productmix_db_path()
    if not pm_db_path.exists():
        return None

    selected_company_id = _effective_company_scope(require_active=True)
    if selected_company_id is None:
        return None

    scoped_ids = {int(item["id"]) for item in _effective_restaurant_options_for_scope(int(selected_company_id))}
    if not scoped_ids:
        return set()
    selected_restaurant_id = _effective_selected_restaurant_id_for_scope(int(selected_company_id), ensure_default=True)
    if selected_restaurant_id is not None:
        if int(selected_restaurant_id) in scoped_ids:
            return {int(selected_restaurant_id)}
        return set()
    return scoped_ids

def _normalize_proxy_location_id(raw_value: Any) -> int | None:
    text = str(raw_value or "").strip().lower()
    if not text:
        return None
    if text.startswith("pm_") and text[3:].isdigit():
        return int(text[3:])
    if text.isdigit():
        return int(text)
    return None

def _collect_proxy_requested_location_ids(path: str) -> set[int]:
    ids: set[int] = set()

    key_names = ("location_id", "restaurant_id")
    for key_name in key_names:
        for raw in request.args.getlist(key_name):
            normalized = _normalize_proxy_location_id(raw)
            if normalized is not None:
                ids.add(normalized)

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        content_type = (request.content_type or "").lower()
        if "application/json" in content_type:
            payload = request.get_json(silent=True)

            def _walk_json(value: Any) -> None:
                if isinstance(value, dict):
                    for key, inner in value.items():
                        if str(key).lower() in key_names:
                            normalized = _normalize_proxy_location_id(inner)
                            if normalized is not None:
                                ids.add(normalized)
                        _walk_json(inner)
                elif isinstance(value, list):
                    for inner in value:
                        _walk_json(inner)

            _walk_json(payload)

        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            for key_name in key_names:
                for raw in request.form.getlist(key_name):
                    normalized = _normalize_proxy_location_id(raw)
                    if normalized is not None:
                        ids.add(normalized)

    for matched in re.findall(r"(?:^|/)(?:restaurant/select|restaurant/update|restaurants)/(\d+)(?:$|/)", path or ""):
        normalized = _normalize_proxy_location_id(matched)
        if normalized is not None:
            ids.add(normalized)

    return ids

def _is_proxy_location_scope_violation(resolved_name: str, path: str) -> bool:
    if resolved_name not in {"productmix", "ic3", "managerapp", "manager"}:
        return False

    scoped_ids = _company_scoped_restaurant_ids_for_proxy()
    if scoped_ids is None:
        return False

    requested_ids = _collect_proxy_requested_location_ids(path)
    if not requested_ids:
        return False

    return any(requested_id not in scoped_ids for requested_id in requested_ids)

_TENANT_SCOPE_AUDIT_RULES: tuple[dict[str, Any], ...] = (
    {
        "endpoint": "api_admin_company_scope_switch",
        "route": "/api/admin/company-scope",
        "methods": {"PATCH"},
        "helper_names": ("_set_session_company_context", "_effective_selected_restaurant_id_for_scope"),
        "description": "Company scope switch must rebind selected location within tenant scope.",
    },
    {
        "endpoint": "api_admin_location_scope_switch",
        "route": "/api/admin/location-scope",
        "methods": {"PATCH"},
        "helper_names": ("_effective_company_scope", "_effective_restaurant_options_for_scope", "_set_session_selected_restaurant_context"),
        "description": "Location scope switch must validate location inside selected company.",
    },
    {
        "endpoint": "api_shared_restaurants",
        "route": "/api/shared/restaurants",
        "methods": {"GET"},
        "helper_names": ("_effective_company_scope", "_effective_selected_restaurant_id_for_scope"),
        "description": "Shared restaurant list must be filtered by company and selected location scope.",
    },
    {
        "endpoint": "api_admin_users_list",
        "route": "/api/admin/users",
        "methods": {"GET"},
        "helper_names": ("_effective_company_scope",),
        "description": "User listing must respect selected company scope.",
    },
    {
        "endpoint": "api_admin_users_create",
        "route": "/api/admin/users",
        "methods": {"POST"},
        "helper_names": ("_strict_company_scope_for_mutation",),
        "description": "User creation must require strict mutation company scope.",
    },
    {
        "endpoint": "api_admin_users_role",
        "route": "/api/admin/users/<int:user_id>/role",
        "methods": {"PATCH"},
        "helper_names": ("_ensure_target_in_super_admin_scope",),
        "description": "User role changes must reject cross-company mutations.",
    },
    {
        "endpoint": "api_admin_users_active",
        "route": "/api/admin/users/<int:user_id>/active",
        "methods": {"PATCH"},
        "helper_names": ("_ensure_target_in_super_admin_scope",),
        "description": "User activation changes must reject cross-company mutations.",
    },
    {
        "endpoint": "api_admin_users_locations",
        "route": "/api/admin/users/<int:user_id>/locations",
        "methods": {"PATCH"},
        "helper_names": ("_ensure_target_in_super_admin_scope",),
        "description": "User location assignments must reject cross-company mutations.",
    },
    {
        "endpoint": "api_admin_tasks_list",
        "route": "/api/admin/tasks",
        "methods": {"GET"},
        "helper_names": ("_effective_company_scope",),
        "description": "Task list must respect selected company scope.",
    },
    {
        "endpoint": "api_admin_tasks_create",
        "route": "/api/admin/tasks",
        "methods": {"POST"},
        "helper_names": ("_strict_company_scope_for_mutation",),
        "description": "Task creation must require strict mutation company scope.",
    },
    {
        "endpoint": "api_admin_tasks_status",
        "route": "/api/admin/tasks/<int:task_id>/status",
        "methods": {"PATCH"},
        "helper_names": ("_ensure_target_in_super_admin_scope",),
        "description": "Task status updates must reject cross-company mutations.",
    },
    {
        "endpoint": "api_admin_audit_logs",
        "route": "/api/admin/audit-logs",
        "methods": {"GET"},
        "helper_names": ("_effective_company_scope",),
        "description": "Audit log reads must stay inside selected company scope.",
    },
    {
        "endpoint": "api_admin_company_files",
        "route": "/api/admin/company-files",
        "methods": {"GET"},
        "helper_names": ("_effective_company_scope", "_list_company_storage_entries"),
        "description": "Company file listing must stay inside selected company storage.",
    },
    {
        "endpoint": "api_admin_company_file_download",
        "route": "/api/admin/company-files/download",
        "methods": {"GET"},
        "helper_names": ("_effective_company_scope", "_resolve_company_storage_path"),
        "description": "Company file downloads must resolve paths inside selected company storage.",
    },
)

def _run_tenant_scope_audit(flask_app: Flask | None = None) -> dict[str, Any]:
    target_app = flask_app or app
    route_index = {rule.endpoint: rule for rule in target_app.url_map.iter_rules()}
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    for spec in _TENANT_SCOPE_AUDIT_RULES:
        endpoint_name = str(spec["endpoint"])
        expected_route = str(spec["route"])
        expected_methods = set(spec.get("methods") or set())
        helper_names = tuple(str(item) for item in (spec.get("helper_names") or ()))

        route_rule = route_index.get(endpoint_name)
        view_func = target_app.view_functions.get(endpoint_name)
        route_found = route_rule is not None and route_rule.rule == expected_route
        methods_found = route_rule is not None and expected_methods.issubset(set(route_rule.methods or set()))

        source_text = ""
        source_error = ""
        if view_func is not None:
            try:
                source_text = inspect.getsource(inspect.unwrap(view_func))
            except Exception as exc:
                source_error = str(exc)

        missing_helpers = [helper_name for helper_name in helper_names if helper_name not in source_text]
        ok = bool(route_found and methods_found and not source_error and not missing_helpers)

        checks.append(
            {
                "endpoint": endpoint_name,
                "route": expected_route,
                "methods": sorted(expected_methods),
                "ok": ok,
                "description": str(spec.get("description") or ""),
                "missing_helpers": missing_helpers,
                "source_error": source_error,
                "route_found": route_found,
                "methods_found": methods_found,
            }
        )

        if not ok:
            warnings.append(
                f"{endpoint_name}: route_found={route_found} methods_found={methods_found} missing_helpers={missing_helpers or '[]'} source_error={source_error or 'none'}"
            )

    return {
        "ok": not warnings,
        "warning_count": len(warnings),
        "checks": checks,
        "warnings": warnings,
    }

@app.route("/api/shared/restaurants")
@login_required
def api_shared_restaurants() -> Response:
    pm_db_path = _productmix_db_path()
    if not pm_db_path.exists():
        return jsonify({"ok": False, "message": f"Shared restaurant DB not found: {pm_db_path}"}), 404

    selected_company_id = _effective_company_scope(require_active=True)
    selected_company_name = _selected_company_name_for_scope()
    assigned_ids = _effective_user_restaurant_ids_for_scope(selected_company_id)
    selected_restaurant_id = _effective_selected_restaurant_id_for_scope(selected_company_id, ensure_default=True)

    conn = sqlite3.connect(pm_db_path)
    conn.row_factory = sqlite3.Row
    try:
        if selected_company_name:
            rows = conn.execute(
                """
                SELECT id, name, location, city, state
                FROM restaurants
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                ORDER BY id ASC
                """,
                (selected_company_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, name, location, city, state
                FROM restaurants
                ORDER BY id ASC
                """
            ).fetchall()
    except sqlite3.Error as exc:
        return jsonify({"ok": False, "message": f"Failed reading shared restaurants: {exc}"}), 500
    finally:
        conn.close()

    restaurants: list[dict[str, Any]] = []
    for row in rows:
        restaurant_id = int(row["id"])
        if assigned_ids is not None and restaurant_id not in assigned_ids:
            continue
        if selected_restaurant_id is not None and restaurant_id != int(selected_restaurant_id):
            continue
        name = str(row["name"] or "").strip()
        location = str(row["location"] or "").strip()
        label = f"{name} - {location}" if location else name
        restaurants.append(
            {
                "id": restaurant_id,
                "name": name,
                "location": location,
                "city": str(row["city"] or "").strip(),
                "state": str(row["state"] or "").strip(),
                "label": label,
            }
        )

    return jsonify(
        {
            "ok": True,
            "restaurants": restaurants,
            "count": len(restaurants),
            "company_scope": {
                "id": int(selected_company_id) if selected_company_id is not None else None,
                "name": selected_company_name,
            },
        }
    )

@app.route("/api/dashboard")
@login_required
def api_dashboard() -> Response:
    open_tasks = 0
    try:
        conn = get_rbac_db_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE status IN ('pending', 'in-progress')"
        ).fetchone()
        conn.close()
        open_tasks = int(row["cnt"]) if row else 0
    except Exception:
        pass

    top_sellers: list[dict[str, Any]] = []
    try:
        productmix_cfg = CONFIG.get("apps", {}).get("productmix", {})
        productmix_cwd = str(productmix_cfg.get("cwd") or "ProductMixRestaurantDB").strip() or "ProductMixRestaurantDB"
        _pm_db_dir_env = os.environ.get("PM_DB_DIR")
        if _pm_db_dir_env:
            pm_db_path = Path(_pm_db_dir_env) / "product_mix.db"
        else:
            pm_db_path = ROOT / productmix_cwd / "product_mix.db"
        if pm_db_path.exists():
            pm_conn = sqlite3.connect(pm_db_path)
            pm_conn.row_factory = sqlite3.Row
            try:
                date_row = pm_conn.execute(
                    "SELECT MAX(report_start_date) AS latest FROM product_mix_items"
                ).fetchone()
                latest_date = date_row["latest"] if date_row else None
                if latest_date:
                    rows = pm_conn.execute(
                        """
                        SELECT item_name, SUM(qty_sold) AS total_sold
                        FROM product_mix_items
                        WHERE report_start_date = ?
                        GROUP BY item_name
                        ORDER BY total_sold DESC
                        LIMIT 5
                        """,
                        (latest_date,),
                    ).fetchall()
                    top_sellers = [
                        {"name": str(r["item_name"]), "qty": float(r["total_sold"] or 0)}
                        for r in rows
                    ]
            finally:
                pm_conn.close()
    except Exception:
        pass

    app_status = MANAGER.status()
    apps_running = sum(1 for s in app_status.values() if s.get("running") and s.get("healthy"))
    total_apps = len(app_status)
    return jsonify({
        "ok": True,
        "open_tasks": open_tasks,
        "top_sellers": top_sellers,
        "app_status": app_status,
        "apps_running": apps_running,
        "total_apps": total_apps,
    })

@app.route("/api/start-all", methods=["POST"])
@csrf.exempt
@login_required
def api_start_all() -> Response:
    result = MANAGER.start_all()
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

@app.route("/api/stop-all", methods=["POST"])
@csrf.exempt
@login_required
def api_stop_all() -> Response:
    return jsonify(MANAGER.stop_all())

@app.route("/api/apps/<name>/start", methods=["POST"])
@csrf.exempt
@login_required
def api_start(name: str) -> Response:
    result = MANAGER.start(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

@app.route("/api/apps/<name>/stop", methods=["POST"])
@csrf.exempt
@login_required
def api_stop(name: str) -> Response:
    result = MANAGER.stop(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

@app.route("/api/apps/<name>/restart", methods=["POST"])
@csrf.exempt
@login_required
def api_restart(name: str) -> Response:
    result = MANAGER.restart(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

def _proxy(name: str, path: str) -> Response:
    resolved_name = MANAGER.resolve_name(name)
    if not resolved_name:
        return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

    if _is_proxy_location_scope_violation(resolved_name, path):
        return jsonify({"ok": False, "message": "Location is outside selected company scope"}), 403

    status = MANAGER.status()[resolved_name]
    if not status["running"]:
        MANAGER.start(resolved_name)
        _app_host, _app_port = MANAGER._parse_host_port(MANAGER.get_base_url(resolved_name))
        for _ in range(20):
            time.sleep(0.5)
            if is_port_open(_app_host, _app_port):
                break

    upstream_base = MANAGER.get_base_url(resolved_name).rstrip("/") + "/"
    upstream_origin = urlparse(upstream_base)

    def rewrite_location_header(location: str) -> str:
        if not location:
            return location
        if location.startswith("/"):
            if location.startswith("/app/"):
                return location
            if location.startswith(f"/app/{resolved_name}/"):
                return location
            if location == "/":
                return f"/app/{resolved_name}/"
            return f"/app/{resolved_name}{location}"

        parsed = urlparse(location)
        if parsed.scheme and parsed.netloc and parsed.netloc == upstream_origin.netloc:
            proxied_path = parsed.path or "/"
            if proxied_path == "/":
                new_location = f"/app/{resolved_name}/"
            else:
                new_location = f"/app/{resolved_name}{proxied_path}"
            if parsed.query:
                new_location = f"{new_location}?{parsed.query}"
            if parsed.fragment:
                new_location = f"{new_location}#{parsed.fragment}"
            return new_location

        return location

    target = urljoin(upstream_base, path)
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8', errors='ignore')}"

    excluded_req_headers = {
        "host",
        "content-length",
        "connection",
        "accept-encoding",
    }
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in excluded_req_headers
    }
    scoped_company_id = _effective_company_scope(require_active=True)
    scoped_company_name = ""
    if scoped_company_id is not None:
        scoped_company = _get_company_by_id(int(scoped_company_id), require_active=True)
        if scoped_company:
            scoped_company_name = str(scoped_company["name"] or "").strip()
    if scoped_company_id is not None:
        forward_headers["X-Dexter-Company-Id"] = str(int(scoped_company_id))
    if scoped_company_name:
        forward_headers["X-Dexter-Company-Name"] = scoped_company_name

    scoped_restaurant = _selected_restaurant_record_for_scope(scoped_company_id)
    if scoped_restaurant:
        forward_headers["X-Dexter-Restaurant-Id"] = str(int(scoped_restaurant["id"]))
        forward_headers["X-Dexter-Restaurant-Name"] = str(scoped_restaurant.get("name") or "").strip()
        forward_headers["X-Dexter-Restaurant-Location"] = str(scoped_restaurant.get("location") or "").strip()

    if resolved_name in {"managerapp", "manager"}:
        dexter_user = session.get(SESSION_USER_KEY) or {}
        if dexter_user:
            forward_headers["X-Dexter-Auth"] = "1"
            forward_headers["X-Dexter-User"] = str(dexter_user.get("username", ""))
            forward_headers["X-Dexter-Email"] = str(dexter_user.get("email", ""))
            forward_headers["X-Dexter-Is-Admin"] = "1" if dexter_user.get("is_admin") else "0"

    content_type_lower = str(request.content_type or "").lower()
    is_multipart = "multipart/form-data" in content_type_lower
    is_form_encoded = "application/x-www-form-urlencoded" in content_type_lower

    def _form_pairs() -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for key in request.form:
            for value in request.form.getlist(key):
                pairs.append((str(key), str(value)))
        return pairs

    def _multipart_file_parts() -> list[tuple[str, tuple[str, bytes, str]]]:
        parts: list[tuple[str, tuple[str, bytes, str]]] = []
        for field_name in request.files:
            for uploaded in request.files.getlist(field_name):
                if uploaded is None:
                    continue
                try:
                    uploaded.stream.seek(0)
                except Exception:
                    pass
                payload = uploaded.read()
                parts.append(
                    (
                        str(field_name),
                        (
                            str(uploaded.filename or "upload.bin"),
                            payload,
                            str(uploaded.mimetype or "application/octet-stream"),
                        ),
                    )
                )
        return parts

    def _request_upstream() -> requests.Response:
        def _without_content_type(headers: dict[str, str]) -> dict[str, str]:
            return {k: v for k, v in headers.items() if k.lower() != "content-type"}

        if is_multipart:
            return requests.request(
                method=request.method,
                url=target,
                headers=_without_content_type(forward_headers),
                data=_form_pairs(),
                files=_multipart_file_parts(),
                cookies=request.cookies,
                allow_redirects=False,
                timeout=30,
            )

        if is_form_encoded:
            return requests.request(
                method=request.method,
                url=target,
                headers=_without_content_type(forward_headers),
                data=_form_pairs(),
                cookies=request.cookies,
                allow_redirects=False,
                timeout=30,
            )

        return requests.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30,
        )

    try:
        upstream = _request_upstream()
    except requests.RequestException as exc:
        try:
            MANAGER.restart(resolved_name)
            _app_host2, _app_port2 = MANAGER._parse_host_port(MANAGER.get_base_url(resolved_name))
            for _ in range(16):
                time.sleep(0.5)
                if is_port_open(_app_host2, _app_port2):
                    break
            upstream = _request_upstream()
        except requests.RequestException:
            return jsonify({"ok": False, "message": f"Upstream request failed: {exc}"}), 502

    excluded_resp_headers = {
        "content-encoding",
        "transfer-encoding",
        "connection",
    }

    content_type = upstream.headers.get("Content-Type", "")
    response_body = upstream.content
    
    if "text/html" in content_type.lower():
        try:
            _html_text = upstream.content.decode(upstream.encoding or "utf-8", errors="replace")
            _html_text = _html_text.replace(
                "const selectedRadio = document.querySelector('input[name=\"location\"][type=\"radio\"]:checked');\n    }\n        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {",
                "const selectedRadio = document.querySelector('input[name=\"location\"][type=\"radio\"]:checked');\n        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {",
            )
            _mobile_patch = (
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
                "<style id=\"__dexter_mobile_patch\">"
                "@media (max-width: 820px){"
                "html,body{height:auto!important;min-height:0!important;"
                "overflow:visible!important;overflow-x:hidden!important;"
                "-webkit-overflow-scrolling:auto!important;"
                "position:static!important;}"
                ".container,.wrap,.shell,.main,.tab-content,.tab-content.active,"
                ".viewer-pane,.page,.app-shell,.content,.dashboard{"
                "overflow:visible!important;height:auto!important;"
                "max-height:none!important;min-height:0!important;position:static!important;}"
                "table{display:block;overflow-x:auto;max-width:100%;}"
                "}"
                "</style>"
            )
            if "</head>" in _html_text.lower():
                _html_text = re.sub(
                    r"</head>",
                    _mobile_patch + "</head>",
                    _html_text,
                    count=1,
                    flags=re.IGNORECASE,
                )
            elif "<body" in _html_text.lower():
                _html_text = re.sub(
                    r"<body",
                    _mobile_patch + "<body",
                    _html_text,
                    count=1,
                    flags=re.IGNORECASE,
                )
            response_body = _html_text.encode("utf-8")
        except Exception:
            response_body = upstream.content
            
    if resolved_name in {"managerapp", "manager"} and "text/html" in content_type.lower():
        try:
            html = (response_body if isinstance(response_body, bytes) else upstream.content).decode(upstream.encoding or "utf-8", errors="replace")

            def _rewrite_attr(match: re.Match[str]) -> str:
                attr = match.group("attr")
                quoted_path = match.group("path")
                if quoted_path.startswith("/app/managerapp/"):
                    return f"{attr}{quoted_path}"
                if quoted_path == "/":
                    return f"{attr}/app/managerapp/"
                return f"{attr}/app/managerapp{quoted_path}"

            html = re.sub(
                r'(?P<attr>\b(?:href|src|action)\s*=\s*["\'])(?P<path>/[^"\']*)',
                _rewrite_attr,
                html,
                flags=re.IGNORECASE,
            )
            response_body = html.encode("utf-8")
        except Exception:
            response_body = upstream.content

    response_headers: list[tuple[str, str]] = []
    for (k, v) in upstream.headers.items():
        k_lower = k.lower()
        if k_lower in excluded_resp_headers:
            continue
        if k_lower == "content-length":
            continue
        if k_lower == "location":
            v = rewrite_location_header(v)
        response_headers.append((k, v))

    return Response(response_body, upstream.status_code, response_headers)

@app.route("/app/<name>/")
@login_required
def app_root(name: str) -> Response:
    return _proxy(name, "")

@app.route(
    "/app/<name>/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@csrf.exempt
def app_proxy(name: str, path: str) -> Response:
    return _proxy(name, path)

@app.route("/open/<name>")
@login_required
def open_app(name: str) -> Response:
    return redirect(f"/app/{name}/")

@app.route("/static/<path:path>")
@login_required
def contextual_static_proxy(path: str) -> Response:
    referer = request.headers.get("Referer", "")
    if "/app/managerapp/" in referer or "/portal/managerapp" in referer:
        return _proxy("managerapp", f"static/{path}")
    if "/app/ic3/" in referer or "/portal/ic3" in referer:
        return _proxy("ic3", f"static/{path}")
    return _proxy("productmix", f"static/{path}")

@app.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@csrf.exempt
def contextual_proxy(path: str) -> Response:
    reserved_prefixes = (
        "app/",
        "portal/",
        "open/",
        "admin",
        "productmix",
        "inventory",
        "manager",
        "static/",
    )
    if path.startswith(reserved_prefixes):
        return jsonify({"ok": False, "message": "Not found"}), 404

    referer = request.headers.get("Referer", "")
    productmix_prefixes = (
        "product-mix",
        "reports",
        "item/",
        "categories",
        "production-list",
        "restaurant-setup",
        "upload",
        "export",
        "auth/",
    )
    if path.startswith("api/"):
        if "/app/managerapp/" in referer or "/portal/managerapp" in referer:
            return _proxy("managerapp", path)
        if "/app/productmix/" in referer or "/portal/productmix" in referer:
            return _proxy("productmix", path)
        if "/app/ic3/" in referer or "/portal/ic3" in referer:
            return _proxy("ic3", path)

        if path.startswith(("api/products", "api/inventory", "api/invoices", "api/orders", "api/tools")):
            return _proxy("ic3", path)
        if path.startswith("api/restaurants"):
            return _proxy("productmix", path)
        return jsonify({"ok": False, "message": "Not found"}), 404

    if "/app/productmix/" in referer or path.startswith(productmix_prefixes):
        return _proxy("productmix", path)
    if "/app/ic3/" in referer:
        return _proxy("ic3", path)
    if "/app/managerapp/" in referer:
        return _proxy("managerapp", path)

    return jsonify({"ok": False, "message": "Not found"}), 404

if __name__ == "__main__":
    front = CONFIG.get("front_door", {})
    host = os.environ.get("DEXTER_HOST") or front.get("host", "127.0.0.1")
    port = int(os.environ.get("DEXTER_PORT") or front.get("port", 5080))
    use_ssl = os.environ.get("DEXTER_SSL", "0") == "1"
    scheme = "https" if use_ssl else "http"
    auto_open_browser = bool(front.get("auto_open_browser", True))
    open_path = str(front.get("open_path", "/")).strip() or "/"
    if not open_path.startswith("/"):
        open_path = f"/{open_path}"

    startup_result = MANAGER.start_all()
    if not startup_result.get("ok"):
        print("Dexter Assistant preflight warning:", startup_result)

    tenant_scope_audit = _run_tenant_scope_audit(app)
    if not tenant_scope_audit.get("ok"):
        print("Dexter Assistant tenant scope audit warning:", tenant_scope_audit.get("warnings", []), file=sys.stderr)

    MANAGER.start_watchdog()
    start_daily_log_email_scheduler()

    if auto_open_browser:
        startup_url = f"{scheme}://{host}:{port}{open_path}"
        threading.Timer(1.0, lambda: open_url_in_chrome(startup_url)).start()

    debug_mode = os.environ.get("PM_DEBUG", "0") == "1"
    ssl_context = "adhoc" if use_ssl else None
    if debug_mode:
        print(f"[dexter] Running in DEBUG mode on {scheme}://{host}:{port}", file=sys.stderr)
        app.run(host=host, port=port, debug=True, ssl_context=ssl_context)
    else:
        if use_ssl:
            print(f"[dexter] SSL enabled. Running Flask HTTPS server on {scheme}://{host}:{port}", file=sys.stderr)
            app.run(host=host, port=port, debug=False, ssl_context=ssl_context)
        else:
            try:
                from waitress import serve  # type: ignore[import]
                print(f"[dexter] Running via waitress on {host}:{port} (threads=8)", file=sys.stderr)
                serve(app, host=host, port=port, threads=8)
            except ImportError:
                print("[dexter] waitress not installed — falling back to Flask dev server.", file=sys.stderr)
                app.run(host=host, port=port, debug=False)