# --- Place at the very end of the file, after all other routes and logic ---
# Deployment: 2026-06-29 16:04

from __future__ import annotations

import atexit
import json
import inspect
import hashlib
import os
import re
import sqlite3
import shutil
import smtplib
import socket
import secrets
import subprocess
import sys
import ssl
import signal
import threading
import tempfile
import time
import webbrowser
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any
from email.message import EmailMessage
from email.utils import formataddr
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
CONFIG_PATH = ROOT / "dexter_assistant_config.json"
RUNTIME_LOG_DIR = ROOT / "runtime_logs"
FRONT_DOOR_FAVICON = ROOT / "favicon.svg"
BRANDING_LOGO_PATH = ROOT / "dexter_logo.png"
LEGACY_BRANDING_LOGO_PATH = ROOT.parent / "Restaurant Management" / "Manager App" / "static" / "img" / "Dexter.png"

_render_data_root = Path("/dexter-data")
_render_data_writable = False
_running_on_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_EXTERNAL_URL"))
if not _running_on_render and _render_data_root.exists():
    _running_on_render = True
if _render_data_root.exists():
    try:
        if os.access(_render_data_root, os.W_OK):
            _render_data_writable = True
            _default_auth_storage_root = _render_data_root / "auth"
        else:
            print(f"[dexter] /dexter-data exists but is not writable, using local storage", file=sys.stderr)
            _default_auth_storage_root = ROOT
    except OSError:
        _default_auth_storage_root = ROOT
else:
    _default_auth_storage_root = ROOT

AUTH_STORAGE_ROOT = Path(os.environ.get("DEXTER_AUTH_DATA_DIR") or str(_default_auth_storage_root))
print(f"[dexter] AUTH_STORAGE_ROOT set to: {AUTH_STORAGE_ROOT} (absolute: {AUTH_STORAGE_ROOT.resolve()})", file=sys.stderr)
try:
    AUTH_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[dexter] AUTH_STORAGE_ROOT directory created/verified", file=sys.stderr)
except OSError as e:
    print(f"[dexter] ERROR: Could not create AUTH_STORAGE_ROOT {AUTH_STORAGE_ROOT}: {e}", file=sys.stderr)
    if _running_on_render:
        raise RuntimeError(
            f"[dexter] Persistent auth storage is unavailable at {AUTH_STORAGE_ROOT}; "
            "refusing to fall back to non-persistent app paths on Render"
        ) from e
    print(f"[dexter] Falling back to ROOT: {ROOT}", file=sys.stderr)
    AUTH_STORAGE_ROOT = ROOT
    try:
        AUTH_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError as e2:
        print(f"[dexter] FATAL: Could not create fallback AUTH_STORAGE_ROOT: {e2}", file=sys.stderr)
    AUTH_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
AUTH_USERS_PATH = AUTH_STORAGE_ROOT / "dexter_assistant_users.json"
RBAC_DB_PATH = AUTH_STORAGE_ROOT / "dexter_assistant_rbac.db"

LEGACY_AUTH_USERS_PATH = ROOT / "dexter_assistant_users.json"
LEGACY_RBAC_DB_PATH = ROOT / "dexter_assistant_rbac.db"
COMPANY_STORAGE_ROOT = ROOT.parent / "company_data"
SESSION_USER_KEY = "dexter_user"
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

try:
    RBAC_BUSY_TIMEOUT_MS = int(os.environ.get("DEXTER_RBAC_BUSY_TIMEOUT_MS", "3000") or "3000")
except ValueError:
    RBAC_BUSY_TIMEOUT_MS = 3000

try:
    UPSTREAM_CONNECT_TIMEOUT_SEC = float(os.environ.get("DEXTER_UPSTREAM_CONNECT_TIMEOUT_SEC", "3") or "3")
except ValueError:
    UPSTREAM_CONNECT_TIMEOUT_SEC = 3.0

try:
    UPSTREAM_READ_TIMEOUT_SEC = float(os.environ.get("DEXTER_UPSTREAM_READ_TIMEOUT_SEC", "60") or "60")
except ValueError:
    UPSTREAM_READ_TIMEOUT_SEC = 60.0

try:
    APP_START_FAILURE_WINDOW_SEC = float(os.environ.get("DEXTER_APP_START_FAILURE_WINDOW_SEC", "60") or "60")
except ValueError:
    APP_START_FAILURE_WINDOW_SEC = 60.0

try:
    APP_START_FAILURE_THRESHOLD = int(os.environ.get("DEXTER_APP_START_FAILURE_THRESHOLD", "3") or "3")
except ValueError:
    APP_START_FAILURE_THRESHOLD = 3

try:
    APP_START_COOLDOWN_SEC = float(os.environ.get("DEXTER_APP_START_COOLDOWN_SEC", "45") or "45")
except ValueError:
    APP_START_COOLDOWN_SEC = 45.0

_DEXTER_SHUTDOWN_LOCK = threading.Lock()
_DEXTER_SHUTDOWN_STARTED = False
MAX_COMPANY_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_COMPANY_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_MGR_BACKUP_STATE_LOCK = threading.Lock()
_MGR_BACKUP_LAST_RUN: dict[str, Any] | None = None
_MGR_BACKUP_THREAD_STARTED = False
_RBAC_WAL_DISABLED = False
_EMERGENCY_BACKUP_PRUNE_ATTEMPTED = False

DEFAULT_NAS_BACKUP_ROOT = r"\\RAMIREZCLANNAS\personal_folder\DexterStorage"


def _emergency_prune_local_backups_for_space(max_keep: int = 0) -> None:
    global _EMERGENCY_BACKUP_PRUNE_ATTEMPTED
    if _EMERGENCY_BACKUP_PRUNE_ATTEMPTED:
        return
    _EMERGENCY_BACKUP_PRUNE_ATTEMPTED = True

    backup_tree = _render_data_root / "backups"

    try:
        if backup_tree.exists() and backup_tree.is_dir():
            shutil.rmtree(backup_tree, ignore_errors=True)
            print("[dexter] Emergency backup prune executed (cleared /dexter-data/backups)", file=sys.stderr)
        else:
            print("[dexter] Emergency backup prune skipped (backup tree not found)", file=sys.stderr)
    except OSError as prune_error:
        print(f"[dexter] Emergency backup prune skipped: {prune_error}", file=sys.stderr)


def _bootstrap_auth_storage_from_legacy() -> None:
    if AUTH_STORAGE_ROOT == ROOT:
        return

    if not RBAC_DB_PATH.exists() and LEGACY_RBAC_DB_PATH.exists():
        RBAC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_RBAC_DB_PATH, RBAC_DB_PATH)

    if not AUTH_USERS_PATH.exists() and LEGACY_AUTH_USERS_PATH.exists():
        AUTH_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_AUTH_USERS_PATH, AUTH_USERS_PATH)


def _load_persistent_front_door_secret_key() -> str:
    env_key = os.environ.get("DEXTER_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if env_key:
        return env_key

    secret_path = ROOT / ".dexter_secret"
    try:
        existing = secret_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass

    new_key = secrets.token_hex(32)
    try:
        secret_path.write_text(new_key, encoding="utf-8")
    except OSError:
        pass
    return new_key


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

CREATE TABLE IF NOT EXISTS company_email_settings (
    company_id INTEGER PRIMARY KEY,
    email_enabled INTEGER NOT NULL DEFAULT 1 CHECK (email_enabled IN (0, 1)),
    email_from_name TEXT,
    email_reply_to TEXT,
    daily_log_email_enabled INTEGER NOT NULL DEFAULT 0 CHECK (daily_log_email_enabled IN (0, 1)),
    daily_log_email_recipients TEXT,
    daily_log_email_time TEXT,
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

def _find_writable_db_path() -> Path:
    """Find a writable path for the RBAC database with fallbacks."""
    global RBAC_DB_PATH
    allow_ephemeral = _env_flag("DEXTER_ALLOW_EPHEMERAL_RBAC", default=False)
    if _running_on_render:
        _emergency_prune_local_backups_for_space()
    candidate_paths = [RBAC_DB_PATH]
    if _render_data_root.exists():
        manager_candidates = [
            _render_data_root / "managerapp" / "auth" / "dexter_assistant_rbac.db",
            _render_data_root / "managerapp" / "dexter_assistant_rbac.db",
        ]
        for manager_candidate in manager_candidates:
            if manager_candidate not in candidate_paths:
                candidate_paths.append(manager_candidate)
        render_fallback = _render_data_root / "dexter_assistant_rbac.db"
        if render_fallback not in candidate_paths:
            candidate_paths.append(render_fallback)
    if not _running_on_render:
        app_dir_fallback = ROOT / "dexter_assistant_rbac.db"
        if app_dir_fallback not in candidate_paths:
            candidate_paths.append(app_dir_fallback)
    if allow_ephemeral:
        candidate_paths.extend([
            Path("/tmp/dexter_assistant_rbac.db"),
            Path(tempfile.gettempdir()) / "dexter_assistant_rbac.db",
        ])
    
    for db_path in candidate_paths:
        try:
            # Try to create parent directory
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Try to open the database to verify write access.
            # Do not require WAL support here because some mounted disks only support DELETE journal mode.
            test_conn = sqlite3.connect(str(db_path.resolve()))
            test_conn.execute("CREATE TABLE IF NOT EXISTS __dexter_write_probe (id INTEGER PRIMARY KEY)")
            test_conn.commit()
            test_conn.close()

            RBAC_DB_PATH = db_path
            print(f"[get_rbac_db_connection] Using database path: {db_path.resolve()}", file=sys.stderr)
            return db_path
        except (OSError, sqlite3.OperationalError) as e:
            print(f"[get_rbac_db_connection] Path not writable ({db_path.resolve()}): {e}", file=sys.stderr)
            continue
    
    # If all paths fail, fail closed on Render to prevent silent data loss to ephemeral paths.
    if _running_on_render and not allow_ephemeral:
        raise RuntimeError(
            "[get_rbac_db_connection] FATAL: No writable persistent RBAC database path found on Render"
        )
    print(f"[get_rbac_db_connection] FATAL: No writable database path found. Using primary: {RBAC_DB_PATH.resolve()}", file=sys.stderr)
    return RBAC_DB_PATH

def get_rbac_db_connection() -> sqlite3.Connection:
    global _RBAC_WAL_DISABLED
    try:
        # Find a writable database path
        db_path = _find_writable_db_path()
        
        # Connect to database
        conn = sqlite3.connect(str(db_path.resolve()))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not _RBAC_WAL_DISABLED:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as wal_error:
                _RBAC_WAL_DISABLED = True
                print(
                    f"[get_rbac_db_connection] WAL unavailable ({wal_error}); falling back to DELETE journal mode",
                    file=sys.stderr,
                )
                conn.execute("PRAGMA journal_mode=DELETE")
        else:
            conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute(f"PRAGMA busy_timeout = {max(250, RBAC_BUSY_TIMEOUT_MS)}")
        return conn
    except sqlite3.OperationalError as e:
        error_msg = str(e)
        print(f"[get_rbac_db_connection] ERROR: Failed to connect to RBAC DB: {error_msg}", file=sys.stderr)
        print(f"[get_rbac_db_connection]   Primary path: {RBAC_DB_PATH.resolve()}", file=sys.stderr)
        print(f"[get_rbac_db_connection]   Primary writable: {os.access(RBAC_DB_PATH.parent, os.W_OK) if RBAC_DB_PATH.parent.exists() else 'N/A'}", file=sys.stderr)
        raise

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
    try:
        RBAC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[dexter] Warning: Could not create RBAC_DB_PATH parent directory {RBAC_DB_PATH.parent}: {e}", file=sys.stderr)
    
    try:
        conn = get_rbac_db_connection()
        try:
            conn.executescript(RBAC_SCHEMA_SQL)
            seed_default_roles(conn)
            conn.commit()
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
        error_msg = str(e)
        print(f"[dexter] ERROR: Failed to initialize RBAC database at {RBAC_DB_PATH}: {error_msg}", file=sys.stderr)
        if "unable to open database file" in error_msg:
            print(f"[dexter] Database path: {RBAC_DB_PATH}", file=sys.stderr)
            print(f"[dexter] Parent directory writable: {os.access(RBAC_DB_PATH.parent, os.W_OK)}", file=sys.stderr)
        raise

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_email_settings (
                company_id INTEGER PRIMARY KEY,
                email_enabled INTEGER NOT NULL DEFAULT 1 CHECK (email_enabled IN (0, 1)),
                email_from_name TEXT,
                email_reply_to TEXT,
                daily_log_email_enabled INTEGER NOT NULL DEFAULT 0 CHECK (daily_log_email_enabled IN (0, 1)),
                daily_log_email_recipients TEXT,
                daily_log_email_time TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
            """
        )

        if _is_migration_complete(conn, migration_key):
            return

        conn.execute(
            """
            INSERT INTO company_email_settings (company_id, updated_at)
            SELECT c.id, datetime('now')
            FROM companies c
            LEFT JOIN company_email_settings ces ON ces.company_id = c.id
            WHERE ces.company_id IS NULL
            """
        )

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

    try:
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
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[find_auth_user] Failed to query auth database: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None, None

def update_user_last_login(user_id: int) -> None:
    try:
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
    except Exception as e:
        print(f"[update_user_last_login] Error updating last login: {type(e).__name__}: {str(e)}", file=sys.stderr)

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
    try:
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
    except Exception as e:
        print(f"[register_failed_login_attempt] Error registering failed login: {type(e).__name__}: {str(e)}", file=sys.stderr)
        return 0, None

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
                   cp.contact_email, cp.contact_phone, cp.website,
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
                company_id, contact_email, contact_phone, website,
                address_line1, address_line2, city, state_region,
                postal_code, country, tax_id, notes, logo_rel_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(company_id) DO UPDATE SET
                contact_email = excluded.contact_email,
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

def _mail_config() -> dict[str, Any]:
    mail_cfg = CONFIG.get("mail", {})
    return dict(mail_cfg) if isinstance(mail_cfg, dict) else {}

def _default_company_email_settings() -> dict[str, Any]:
    mail_cfg = _mail_config()
    return {
        "email_enabled": bool(mail_cfg.get("enabled", True)),
        "email_from_name": str(mail_cfg.get("from_name") or "").strip(),
        "email_reply_to": str(mail_cfg.get("reply_to") or "").strip(),
        "daily_log_email_enabled": bool(mail_cfg.get("daily_log_email_enabled", False)),
        "daily_log_email_recipients": str(mail_cfg.get("daily_log_email_recipients") or "").strip(),
        "daily_log_email_time": str(mail_cfg.get("daily_log_email_time") or "01:00").strip(),
    }

def get_company_email_settings(company_id: int) -> dict[str, Any]:
    defaults = _default_company_email_settings()
    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT company_id, email_enabled, email_from_name, email_reply_to,
                   daily_log_email_enabled, daily_log_email_recipients, daily_log_email_time,
                   updated_at
            FROM company_email_settings
            WHERE company_id = ?
            LIMIT 1
            """,
            (int(company_id),),
        ).fetchone()
        if not row:
            return defaults
        return {
            "email_enabled": bool(int(row["email_enabled"])),
            "email_from_name": str(row["email_from_name"] or defaults["email_from_name"]),
            "email_reply_to": str(row["email_reply_to"] or defaults["email_reply_to"]),
            "daily_log_email_enabled": bool(int(row["daily_log_email_enabled"])),
            "daily_log_email_recipients": str(row["daily_log_email_recipients"] or defaults["daily_log_email_recipients"]),
            "daily_log_email_time": str(row["daily_log_email_time"] or defaults["daily_log_email_time"]),
            "updated_at": str(row["updated_at"] or ""),
        }
    finally:
        conn.close()

def upsert_company_email_settings(company_id: int, settings_data: dict[str, Any]) -> None:
    defaults = _default_company_email_settings()
    cleaned = {
        "email_enabled": 1 if str(settings_data.get("email_enabled", defaults["email_enabled"])).strip().lower() in {"1", "true", "yes", "on"} else 0,
        "email_from_name": str(settings_data.get("email_from_name") or defaults["email_from_name"]).strip(),
        "email_reply_to": str(settings_data.get("email_reply_to") or defaults["email_reply_to"]).strip(),
        "daily_log_email_enabled": 1 if str(settings_data.get("daily_log_email_enabled", defaults["daily_log_email_enabled"])).strip().lower() in {"1", "true", "yes", "on"} else 0,
        "daily_log_email_recipients": str(settings_data.get("daily_log_email_recipients") or defaults["daily_log_email_recipients"]).strip(),
        "daily_log_email_time": str(settings_data.get("daily_log_email_time") or defaults["daily_log_email_time"]).strip() or "01:00",
    }

    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO company_email_settings (
                company_id, email_enabled, email_from_name, email_reply_to,
                daily_log_email_enabled, daily_log_email_recipients, daily_log_email_time, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(company_id) DO UPDATE SET
                email_enabled = excluded.email_enabled,
                email_from_name = excluded.email_from_name,
                email_reply_to = excluded.email_reply_to,
                daily_log_email_enabled = excluded.daily_log_email_enabled,
                daily_log_email_recipients = excluded.daily_log_email_recipients,
                daily_log_email_time = excluded.daily_log_email_time,
                updated_at = datetime('now')
            """,
            (
                int(company_id),
                cleaned["email_enabled"],
                cleaned["email_from_name"],
                cleaned["email_reply_to"],
                cleaned["daily_log_email_enabled"],
                cleaned["daily_log_email_recipients"],
                cleaned["daily_log_email_time"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

def build_mail_status() -> dict[str, Any]:
    mail_cfg = _mail_config()
    smtp_host = str(mail_cfg.get("smtp_host") or "").strip()
    smtp_port = int(mail_cfg.get("smtp_port") or 0)
    username_env = str(mail_cfg.get("username_env") or "DEXTER_SMTP_USERNAME").strip() or "DEXTER_SMTP_USERNAME"
    password_env = str(mail_cfg.get("password_env") or "DEXTER_SMTP_PASSWORD").strip() or "DEXTER_SMTP_PASSWORD"
    smtp_username = str(os.environ.get(username_env) or mail_cfg.get("smtp_username") or "").strip()
    smtp_password = str(os.environ.get(password_env) or "").strip()
    from_email = str(mail_cfg.get("from_email") or smtp_username).strip()
    from_name = str(mail_cfg.get("from_name") or "").strip()
    reply_to = str(mail_cfg.get("reply_to") or from_email).strip()
    public_base_url = str(mail_cfg.get("public_base_url") or "").strip() or request.host_url.rstrip("/")
    use_ssl = bool(mail_cfg.get("use_ssl", False))
    use_starttls = bool(mail_cfg.get("use_starttls", False))

    problems: list[str] = []
    if not smtp_host:
        problems.append("SMTP host is not configured.")
    if not smtp_port:
        problems.append("SMTP port is not configured.")
    if not smtp_username:
        problems.append(f"SMTP username env var {username_env} is not set.")
    if not smtp_password:
        problems.append(f"SMTP password env var {password_env} is not set.")
    if not from_email:
        problems.append("From email is not configured.")
    if not (use_ssl or use_starttls):
        problems.append("SMTP encryption is not configured.")

    settings = {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "username": smtp_username,
        "from_email": from_email,
        "from_name": from_name,
        "reply_to": reply_to,
        "use_ssl": use_ssl,
        "use_starttls": use_starttls,
        "public_base_url": public_base_url,
        "username_env": username_env,
        "password_env": password_env,
    }
    return {
        "ready": len(problems) == 0,
        "problems": problems,
        "settings": settings,
    }

def _build_public_endpoint_url(endpoint: str, **values: Any) -> str:
    relative_path = url_for(endpoint, **values)
    public_base_url = str(_mail_config().get("public_base_url") or "").strip()
    if public_base_url:
        return urljoin(public_base_url.rstrip("/") + "/", relative_path.lstrip("/"))
    return url_for(endpoint, _external=True, **values)

def _redirect_admin_users(*, message: str | None = None, error: str | None = None) -> Response:
    target = url_for("admin_users_page")
    if message is not None:
        return redirect(f"{target}?message={requests.utils.quote(message)}")
    if error is not None:
        return redirect(f"{target}?error={requests.utils.quote(error)}")
    return redirect(target)

def _send_email_via_smtp(target_email: str, subject: str, body: str, reply_to: str | None = None) -> tuple[bool, str]:
    mail_status = build_mail_status()
    if not mail_status["ready"]:
        return False, "SMTP is not ready."

    settings = mail_status["settings"]
    smtp_host = str(settings["smtp_host"])
    smtp_port = int(settings["smtp_port"])
    smtp_username = str(settings["username"])
    smtp_password = str(os.environ.get(str(settings["password_env"]), "") or "")
    from_name = str(settings.get("from_name") or "")
    from_email = str(settings.get("from_email") or smtp_username)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name, from_email)) if from_name else from_email
    message["To"] = str(target_email).strip()
    if reply_to:
        message["Reply-To"] = str(reply_to).strip()
    message.set_content(body)

    context = ssl.create_default_context()
    try:
        if bool(settings.get("use_ssl")):
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15) as smtp:
                smtp.login(smtp_username, smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
                if bool(settings.get("use_starttls")):
                    smtp.starttls(context=context)
                smtp.login(smtp_username, smtp_password)
                smtp.send_message(message)
        return True, "Email sent."
    except Exception as exc:  # noqa: BLE001
        return False, f"Failed to send email: {exc}"

def _set_password_reset_token_for_user(user_id: int) -> tuple[bool, str, str | None]:
    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            "SELECT id, username FROM users WHERE id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if not row:
            return False, "User not found.", None

        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE users
            SET password_reset_token = ?,
                password_reset_expires = ?,
                is_active = 1,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (token, expires, int(user_id)),
        )
        conn.commit()
        reset_url = _build_public_endpoint_url("auth_reset_password", token=token)
        return True, str(row["username"]), reset_url
    finally:
        conn.close()

def _invite_email_body(company_name: str, username: str, reset_url: str, from_name: str) -> str:
    return (
        f"Hello {username},\n\n"
        f"{from_name or 'Dexter Ops'} has created your account for {company_name}.\n"
        f"Use the secure link below to set your password:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this invite, you can ignore this email.\n"
    )

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
        self._stdout_streams: dict[str, Any | None] = {
            name: None for name in config["apps"].keys()
        }
        self._runtime_base_urls: dict[str, str | None] = {
            name: None for name in config["apps"].keys()
        }
        self._start_failures: dict[str, list[float]] = {
            name: [] for name in config["apps"].keys()
        }
        self._start_cooldown_until: dict[str, float] = {
            name: 0.0 for name in config["apps"].keys()
        }
        RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _prune_start_failures(self, name: str, now_ts: float) -> list[float]:
        cutoff = now_ts - max(10.0, APP_START_FAILURE_WINDOW_SEC)
        kept = [ts for ts in self._start_failures.get(name, []) if ts >= cutoff]
        self._start_failures[name] = kept
        return kept

    def _record_start_failure(self, name: str, reason: str) -> None:
        now_ts = time.time()
        kept = self._prune_start_failures(name, now_ts)
        kept.append(now_ts)
        self._start_failures[name] = kept
        threshold = max(1, APP_START_FAILURE_THRESHOLD)
        if len(kept) >= threshold:
            cooldown = max(5.0, APP_START_COOLDOWN_SEC)
            self._start_cooldown_until[name] = now_ts + cooldown
            print(
                f"[dexter circuit] Opening start circuit for '{name}' after {len(kept)} failures: {reason}. Cooldown {int(cooldown)}s.",
                file=sys.stderr,
            )

    def _record_start_success(self, name: str) -> None:
        self._start_failures[name] = []
        self._start_cooldown_until[name] = 0.0

    def _start_allowed(self, name: str) -> tuple[bool, int]:
        now_ts = time.time()
        cooldown_until = float(self._start_cooldown_until.get(name, 0.0) or 0.0)
        if cooldown_until > now_ts:
            retry_after = int(max(1.0, cooldown_until - now_ts))
            return False, retry_after
        return True, 0

    def retry_after_seconds(self, name: str) -> int:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return 0
        with self._lock:
            _, retry_after = self._start_allowed(resolved_name)
            return retry_after

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

    def is_running(self, name: str) -> bool:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return False
        with self._lock:
            proc = self._procs.get(resolved_name)
            return bool(proc is not None and proc.poll() is None)

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

            start_allowed, retry_after = self._start_allowed(resolved_name)
            if not start_allowed:
                return {
                    "ok": False,
                    "message": f"{resolved_name} temporarily blocked after repeated startup failures",
                    "retry_after_sec": retry_after,
                }

            cwd = ROOT / app["cwd"]
            entry = cwd / app["entrypoint"]
            if not entry.exists():
                self._record_start_failure(resolved_name, f"missing entrypoint: {entry}")
                return {"ok": False, "message": f"Entrypoint not found: {entry}"}

            host, port = self._parse_host_port(app["base_url"])
            auto_port = bool(app.get("auto_port"))
            if not is_port_free(host, port):
                if auto_port:
                    port = find_free_port(host)
                else:
                    self._record_start_failure(resolved_name, f"port unavailable: {host}:{port}")
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
                if _render_data_root.exists() and _render_data_writable:
                    mgr_root = _render_data_root / "managerapp"
                    try:
                        mgr_root.mkdir(parents=True, exist_ok=True)
                    except OSError:
                        pass
                    env.setdefault("MGR_DB_PATH", str(mgr_root / "manager_app.db"))
                    env.setdefault("MGR_COMPANY_DATA_DIR", str(mgr_root / "company_data"))
                    env.setdefault("MGR_PERSISTENT_ROOT", str(_render_data_root))
                    env.setdefault("MGR_REQUIRE_PERSISTENT_STORAGE", "1")
                    env.setdefault("MGR_STORAGE_STRICT", "1")
                    env.setdefault("MGR_ALLOW_EPHEMERAL_DB", "0")
                else:
                    if _running_on_render:
                        self._record_start_failure(
                            resolved_name,
                            "render persistent storage unavailable for managerapp",
                        )
                        return {
                            "ok": False,
                            "message": "Render persistent storage unavailable; refusing to start managerapp to prevent data loss",
                        }
                    # Critical: manager data MUST persist. Fall back to app directory, not temp.
                    # Do NOT use /tmp for manager data (ephemeral on Render).
                    app_dir_fallback = ROOT / "Dexter Assistant" / "Manager App"
                    try:
                        app_dir_fallback.mkdir(parents=True, exist_ok=True)
                    except OSError:
                        pass
                    env.setdefault("MGR_DB_PATH", str(app_dir_fallback / "manager_app.db"))
                    env.setdefault("MGR_COMPANY_DATA_DIR", str(app_dir_fallback / "company_data"))
                    env.setdefault("MGR_REQUIRE_PERSISTENT_STORAGE", "0")
                    env.setdefault("MGR_STORAGE_STRICT", "0")
                    env.setdefault("MGR_ALLOW_EPHEMERAL_DB", "0")
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
            self._stdout_streams[resolved_name] = stdout_stream
            self._runtime_base_urls[resolved_name] = runtime_base_url

            # Guard against fast-crash startup loops by briefly validating process liveness.
            startup_deadline = time.time() + 6.0
            while time.time() < startup_deadline:
                if proc.poll() is not None:
                    self._procs[resolved_name] = None
                    stream = self._stdout_streams.get(resolved_name)
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            pass
                    self._stdout_streams[resolved_name] = None
                    self._runtime_base_urls[resolved_name] = None
                    log_tail = self._tail_log(resolved_name, max_lines=50)
                    self._record_start_failure(resolved_name, f"exited during startup rc={proc.returncode}")
                    return {
                        "ok": False,
                        "message": f"{resolved_name} exited during startup (rc={proc.returncode})",
                        "log_tail": log_tail,
                    }
                if is_port_open(host, port):
                    self._record_start_success(resolved_name)
                    break
                time.sleep(0.25)

            return {"ok": True, "message": f"Started {resolved_name}", "pid": proc.pid, "base_url": runtime_base_url}

    def stop(self, name: str) -> dict[str, Any]:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return {"ok": False, "message": f"Unknown app: {name}"}

        with self._lock:
            proc = self._procs.get(resolved_name)
            if proc is None or proc.poll() is not None:
                self._procs[resolved_name] = None
                stream = self._stdout_streams.get(resolved_name)
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                self._stdout_streams[resolved_name] = None
                self._runtime_base_urls[resolved_name] = None
                return {"ok": True, "message": f"{resolved_name} already stopped"}

            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self._procs[resolved_name] = None
            stream = self._stdout_streams.get(resolved_name)
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            self._stdout_streams[resolved_name] = None
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
_secret = _load_persistent_front_door_secret_key()
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


def _stop_child_apps_for_shutdown() -> None:
    global _DEXTER_SHUTDOWN_STARTED
    with _DEXTER_SHUTDOWN_LOCK:
        if _DEXTER_SHUTDOWN_STARTED:
            return
        _DEXTER_SHUTDOWN_STARTED = True
    try:
        print("[dexter] Shutdown initiated. Stopping managed child apps...", file=sys.stderr)
        MANAGER.stop_all()
    except Exception as exc:
        print(f"[dexter] Shutdown warning: could not stop managed apps cleanly: {exc}", file=sys.stderr)


def _dexter_signal_handler(signum: int, _frame: Any) -> None:
    _stop_child_apps_for_shutdown()
    raise SystemExit(0)


atexit.register(_stop_child_apps_for_shutdown)
for _sig in (signal.SIGTERM, signal.SIGINT):
    try:
        signal.signal(_sig, _dexter_signal_handler)
    except Exception:
        pass

# ----- Auto-sync git scheduler for database persistence -----
try:
    from auto_sync_git import create_auto_sync_scheduler
    _autosync_interval = int(os.environ.get("DEXTER_AUTOSYNC_INTERVAL_MINUTES", "30"))
    _autosync_enabled = _env_flag("DEXTER_AUTOSYNC_ENABLED", default=True)
    if _autosync_enabled:
        _autosync_scheduler = create_auto_sync_scheduler(app, ROOT.parent, interval_minutes=_autosync_interval)
        if _autosync_scheduler:
            print(f"[dexter] Auto-sync git scheduler enabled (interval: {_autosync_interval} minutes)", file=sys.stderr)
        else:
            print("[dexter] Auto-sync scheduler not available (APScheduler not installed)", file=sys.stderr)
    else:
        print("[dexter] Auto-sync git scheduler disabled via DEXTER_AUTOSYNC_ENABLED=0", file=sys.stderr)
except ImportError as e:
    print(f"[dexter] Warning: Could not import auto_sync_git module: {e}", file=sys.stderr)
except Exception as e:
    print(f"[dexter] Warning: Failed to initialize auto-sync scheduler: {e}", file=sys.stderr)


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
    '<div class="dx-version-badge" aria-hidden="true">2026 Dexter Assist v0.9</div>'
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

try:
    _bootstrap_auth_storage_from_legacy()
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
except Exception as e:
    error_msg = f"{type(e).__name__}: {str(e)}"
    print(f"[dexter] FATAL: Database initialization failed: {error_msg}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    print(f"[dexter] Attempting to continue with degraded functionality...", file=sys.stderr)

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
    try:
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
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        print(f"[auth_login] Exception: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "message": error_msg}), 500

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
                    reset_url = _build_public_endpoint_url("auth_reset_password", token=token)
                else:
                    error = "If that username exists, a reset link has been generated. Ask an admin."
            finally:
                conn.close()

    return Response(
        render_template(
            "forgot_password.html",
            error=error,
            reset_url=reset_url,
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
    def _send_no_store_logo(path: Path, *, download_name: str | None = None) -> Response:
        response = send_file(
            path,
            as_attachment=False,
            download_name=download_name,
            max_age=0,
            conditional=False,
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Vary"] = "Cookie"
        return response

    def _company_logo_fallback_response() -> Response:
        if BRANDING_LOGO_PATH.exists():
            return _send_no_store_logo(BRANDING_LOGO_PATH)
        if LEGACY_BRANDING_LOGO_PATH.exists():
            return _send_no_store_logo(LEGACY_BRANDING_LOGO_PATH)
        if FRONT_DOOR_FAVICON.exists():
            return _send_no_store_logo(FRONT_DOOR_FAVICON)
        return jsonify({"ok": False, "message": "Not found"}), 404

    selected_company_id = _effective_company_scope(require_active=True)
    if selected_company_id is None:
        return _company_logo_fallback_response()

    profile = get_company_profile(int(selected_company_id))
    logo_rel_path = str((profile or {}).get("logo_rel_path") or "").strip()
    if not logo_rel_path:
        return _company_logo_fallback_response()

    logo_path = _resolve_company_storage_path(int(selected_company_id), logo_rel_path)
    if logo_path is None or not logo_path.exists() or not logo_path.is_file():
        return _company_logo_fallback_response()

    return _send_no_store_logo(logo_path, download_name=logo_path.name)

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

@app.route("/admin/email", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def admin_email_page() -> Response:
    is_super_admin = current_role_name() == "Super Admin"
    companies = list_companies(active_only=True) if is_super_admin else []
    selected_company_id = _effective_company_scope()
    if is_super_admin and selected_company_id is None and companies:
        selected_company_id = int(companies[0]["id"])

    company_mail = get_company_email_settings(int(selected_company_id)) if selected_company_id is not None else _default_company_email_settings()
    mail_status = build_mail_status()
    public_base_url = str(mail_status["settings"].get("public_base_url") or request.host_url.rstrip("/"))

    return Response(
        render_template(
            "admin_email.html",
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
            company_mail=company_mail,
            mail_status=mail_status,
            public_base_url=public_base_url,
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/email/settings", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_email_settings_save() -> Response:
    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return redirect(f"/admin/email?error={requests.utils.quote(scope_error)}")
    if selected_company_id is None:
        return redirect("/admin/email?error=No+active+company+scope+is+selected")

    upsert_company_email_settings(
        int(selected_company_id),
        {
            "email_enabled": request.form.get("email_enabled"),
            "email_from_name": request.form.get("email_from_name"),
            "email_reply_to": request.form.get("email_reply_to"),
            "daily_log_email_enabled": request.form.get("daily_log_email_enabled"),
            "daily_log_email_recipients": request.form.get("daily_log_email_recipients"),
            "daily_log_email_time": request.form.get("daily_log_email_time"),
        },
    )
    return redirect("/admin/email?message=Email+settings+saved")

@app.route("/admin/email/test", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_email_test_send() -> Response:
    selected_company_id = _effective_company_scope()
    if selected_company_id is None:
        return redirect("/admin/email?error=No+active+company+scope+is+selected")

    target_email = str(request.form.get("target_email") or "").strip()
    if not target_email or "@" not in target_email:
        return redirect("/admin/email?error=Enter+a+valid+target+email")

    company_mail = get_company_email_settings(int(selected_company_id))
    mail_status = build_mail_status()
    settings = mail_status["settings"]
    company_name = _selected_company_name_for_scope() or "Dexter Ops"
    subject = f"Test email from {company_name}"
    body = (
        f"This is a test email from {company_name}.\n\n"
        f"SMTP host: {settings['smtp_host']}\n"
        f"Company reply-to: {company_mail.get('email_reply_to') or settings['reply_to']}\n"
        f"Public base URL: {settings['public_base_url']}\n"
    )
    ok, msg = _send_email_via_smtp(target_email, subject, body, reply_to=str(company_mail.get("email_reply_to") or settings["reply_to"]))
    key = "message" if ok else "error"
    return redirect(f"/admin/email?{key}={requests.utils.quote(msg)}")

def _effective_company_scope(require_active: bool = True) -> int | None:
    try:
        role_name = current_role_name()
        if role_name != "Super Admin":
            return current_user_company_id()

        user_company_id = current_user_company_id()

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
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        print(f"[_effective_company_scope] Exception: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
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
    mail_status = build_mail_status()

    return Response(
        render_template(
            "admin_users.html",
            users=list_users_with_roles(company_id=selected_company_id),
            is_super_admin=is_super_admin,
            companies=companies,
            selected_company_id=selected_company_id,
            available_locations=available_locations,
            mail_status=mail_status,
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )

@app.route("/admin/users/create", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return _redirect_admin_users(error="Session expired")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return _redirect_admin_users(error=scope_error)

    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=(request.form.get("username") or ""),
        password=(request.form.get("password") or ""),
        role_name=(request.form.get("role_name") or "Employee"),
        company_id=selected_company_id,
        assigned_restaurant_ids=request.form.getlist("restaurant_ids"),
    )
    key = "message" if ok else "error"
    return _redirect_admin_users(**{key: msg})

@app.route("/admin/users/invite", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_invite() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return _redirect_admin_users(error="Session expired")

    email = str(request.form.get("email") or "").strip()
    if not email or "@" not in email:
        return _redirect_admin_users(error="Enter a valid invite email")

    role_name = str(request.form.get("role_name") or "Employee").strip()
    if role_name not in {"Super Admin", "Manager", "Employee"}:
        return _redirect_admin_users(error="Invalid role name")

    selected_company_id, scope_error = _strict_company_scope_for_mutation()
    if scope_error:
        return _redirect_admin_users(error=scope_error)

    if role_name == "Super Admin":
        selected_company_id = None

    temp_password = secrets.token_urlsafe(16)
    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=email,
        password=temp_password,
        role_name=role_name,
        company_id=selected_company_id,
        assigned_restaurant_ids=request.form.getlist("restaurant_ids"),
    )
    if not ok:
        return _redirect_admin_users(error=msg)

    conn = get_rbac_db_connection()
    try:
        row = conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1", (email,)).fetchone()
        if not row:
            return _redirect_admin_users(error="Invite created but user could not be reloaded")
        user_id = int(row["id"])
    finally:
        conn.close()

    ok_token, username, reset_url = _set_password_reset_token_for_user(user_id)
    if not ok_token or not reset_url:
        return _redirect_admin_users(error="Invite created but reset link could not be generated")

    mail_status = build_mail_status()
    company_name = _selected_company_name_for_scope() or "Dexter Ops"
    subject = f"Your {company_name} account invitation"
    body = _invite_email_body(company_name, username, reset_url, str(mail_status["settings"].get("from_name") or "Dexter Ops"))
    if mail_status["ready"]:
        send_ok, send_msg = _send_email_via_smtp(email, subject, body, reply_to=str(mail_status["settings"].get("reply_to") or email))
        if send_ok:
            return _redirect_admin_users(message="Invite sent")
        return _redirect_admin_users(error=send_msg)

    return _redirect_admin_users(message=f"Invite link ready: {reset_url}")

@app.route("/admin/users/<int:user_id>/active", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_active(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return _redirect_admin_users(error="Session expired")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return _redirect_admin_users(error=scope_error)

    is_active = str(request.form.get("is_active", "1")).strip() == "1"
    ok, msg = set_user_active_state(actor_id, int(user_id), is_active)
    key = "message" if ok else "error"
    return _redirect_admin_users(**{key: msg})

@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_role(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return _redirect_admin_users(error="Session expired")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return _redirect_admin_users(error=scope_error)

    role_name = str(request.form.get("role_name") or "Employee").strip()
    ok, msg = set_user_role_name(actor_id, int(user_id), role_name)
    key = "message" if ok else "error"
    return _redirect_admin_users(**{key: msg})

@app.route("/admin/users/<int:user_id>/locations", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_locations(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return _redirect_admin_users(error="Session expired")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return _redirect_admin_users(error=scope_error)

    ok, msg = set_user_location_assignments(actor_id, int(user_id), request.form.getlist("restaurant_ids"))
    key = "message" if ok else "error"
    return _redirect_admin_users(**{key: msg})

@app.route("/admin/users/<int:user_id>/resend-invite", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_users_resend_invite(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return _redirect_admin_users(error="Session expired")

    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.company_id, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return _redirect_admin_users(error="User not found")

    if current_role_name() == "Super Admin":
        scope_error = _ensure_target_in_super_admin_scope(_company_id_for_user(int(user_id)), "user")
        if scope_error:
            return _redirect_admin_users(error=scope_error)

    username = str(row["username"] or "").strip()
    if "@" not in username:
        return _redirect_admin_users(error="This user does not use an email username")

    ok_token, _, reset_url = _set_password_reset_token_for_user(int(user_id))
    if not ok_token or not reset_url:
        return _redirect_admin_users(error="Could not generate invite link")

    mail_status = build_mail_status()
    company_name = _selected_company_name_for_scope() or "Dexter Ops"
    subject = f"Your {company_name} account invitation"
    body = _invite_email_body(company_name, username, reset_url, str(mail_status["settings"].get("from_name") or "Dexter Ops"))
    if mail_status["ready"]:
        send_ok, send_msg = _send_email_via_smtp(username, subject, body, reply_to=str(mail_status["settings"].get("reply_to") or username))
        if send_ok:
            return _redirect_admin_users(message="Invite resent")
        return _redirect_admin_users(error=send_msg)

    return _redirect_admin_users(message=f"Invite link ready: {reset_url}")

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
        portal_root_url="/portal",
        admin_root_url="/admin",
        manager_portal_url="/portal/managerapp",
        ic3_portal_url="/portal/ic3",
        productmix_portal_url="/portal/productmix",
        admin_users_url="/admin/users",
        admin_tasks_url="/admin/tasks",
        admin_email_url="/admin/email",
        admin_audit_logs_url="/admin/audit-logs",
        admin_company_profile_url="/admin/company-profile",
        admin_companies_url="/admin/companies",
        admin_company_health_url="/admin/company-health",
        company_scope_action_url="/admin/company-scope",
        location_scope_action_url="/admin/location-scope",
        role_name=role_name,
        company_options=company_options,
        selected_company_id=selected_company_id,
        location_options=location_options,
        selected_restaurant_id=selected_restaurant_id,
        selected_restaurant=selected_restaurant,
        selected_company_name=_selected_company_name_for_scope(),
        company_switched=(request.args.get("company_switched") or "").strip().lower() in {"1", "true", "yes"},
        location_switched=(request.args.get("location_switched") or "").strip().lower() in {"1", "true", "yes"},
    )

@app.route("/portal/<name>")
@login_required
def portal_app(name: str) -> Response:
    try:
        resolved_name = MANAGER.resolve_name(name)
        if not resolved_name:
            return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

        start_result = MANAGER.start(resolved_name)
        if not start_result.get("ok"):
            error_msg = start_result.get("message", "Failed to start app")
            retry_after = int(start_result.get("retry_after_sec") or MANAGER.retry_after_seconds(resolved_name) or 0)
            print(f"[portal_app] Failed to start {resolved_name}: {error_msg}", file=sys.stderr)
            payload = {"ok": False, "message": error_msg}
            log_tail = str(start_result.get("log_tail") or "").strip()
            if log_tail:
                payload["startup_log_tail"] = log_tail
            if retry_after > 0:
                payload["retry_after_sec"] = retry_after
            response = jsonify(payload)
            response.status_code = 503
            if retry_after > 0:
                response.headers["Retry-After"] = str(retry_after)
            return response

        app_cfg = CONFIG["apps"][resolved_name]
        switched = (request.args.get("company_switched") or "").strip().lower() in {"1", "true", "yes"}
        location_switched = (request.args.get("location_switched") or "").strip().lower() in {"1", "true", "yes"}
        raw_url = "/app/managerapp/" if resolved_name == "managerapp" else f"/app/{resolved_name}/"
        show_shell_nav = resolved_name != "managerapp"
        selected_restaurant = _selected_restaurant_record_for_scope(_effective_company_scope(require_active=True))
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
            selected_company_name=_selected_company_name_for_scope(),
            current_location_name=current_location_name,
        )
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        print(f"[portal_app] Exception in portal_app route: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"ok": False, "message": error_msg}), 500

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


def _is_subpath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _storage_health_snapshot() -> dict[str, Any]:
    root = _render_data_root
    snapshot: dict[str, Any] = {
        "persistent_root": str(root),
        "persistent_root_exists": root.exists(),
    }

    if root.exists():
        usage = shutil.disk_usage(root)
        total = int(usage.total)
        used = int(usage.used)
        free = int(usage.free)
        used_pct = round((used / total) * 100, 2) if total else 0.0
        snapshot["disk"] = {
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "used_pct": used_pct,
            "status": "critical" if used_pct >= 95 else ("warning" if used_pct >= 85 else "ok"),
        }

    manager_root = root / "managerapp"
    manager_db = manager_root / "manager_app.db"
    manager_company_data = manager_root / "company_data"
    snapshot["managerapp"] = {
        "root": str(manager_root),
        "db_path": str(manager_db),
        "company_data_path": str(manager_company_data),
        "root_exists": manager_root.exists(),
        "db_exists": manager_db.exists(),
        "company_data_exists": manager_company_data.exists(),
        "db_in_persistent_root": _is_subpath(manager_db, root) if root.exists() else False,
        "company_data_in_persistent_root": _is_subpath(manager_company_data, root) if root.exists() else False,
    }

    snapshot["backup"] = _manager_backup_status_payload()

    snapshot["ok"] = bool(
        root.exists()
        and snapshot["managerapp"]["db_in_persistent_root"]
        and snapshot["managerapp"]["company_data_in_persistent_root"]
        and snapshot["backup"].get("ok", False)
    )
    return snapshot

@app.route("/api/health")
def api_health() -> Response:
    return jsonify({"ok": True, "storage": _storage_health_snapshot()})


@app.route("/api/admin/storage-health", methods=["GET"])
@login_required
@role_required("Super Admin")
def api_admin_storage_health() -> Response:
    payload = _storage_health_snapshot()
    status = 200 if payload.get("ok") else 503
    return jsonify(payload), status

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


def _manager_db_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_path = str(os.environ.get("MGR_DB_PATH") or "").strip()
    if env_path:
        candidates.append(Path(env_path))

    try:
        paths = _manager_backup_paths()
        db_path = paths.get("db_path")
        if isinstance(db_path, Path):
            candidates.append(db_path)
    except Exception:
        pass

    candidates.append(ROOT / "Manager App" / "manager_app.db")

    seen: set[str] = set()
    normalized: list[Path] = []
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(path)
    return normalized


def _parse_inventory_default_groups_payload(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        payload = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            payload = {}
        else:
            try:
                payload = json.loads(text)
            except Exception:
                payload = {}
    else:
        payload = {}

    company_rows = payload.get("company") if isinstance(payload, dict) else []
    location_rows = payload.get("location_overrides") if isinstance(payload, dict) else {}
    defaults_map = payload.get("default_group_by_location") if isinstance(payload, dict) else {}

    if not isinstance(company_rows, list):
        company_rows = []
    if not isinstance(location_rows, dict):
        location_rows = {}
    if not isinstance(defaults_map, dict):
        defaults_map = {}

    def _normalize_group_rows(rows: Any) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            group_id = str(row.get("id") or "").strip()
            group_name = str(row.get("name") or "").strip()
            if not group_id:
                group_id = f"grp_{uuid.uuid4().hex[:10]}"
            if not group_name:
                continue
            raw_item_keys = row.get("item_keys")
            if isinstance(raw_item_keys, str):
                raw_item_keys = [part.strip() for part in raw_item_keys.split(",") if part.strip()]
            if not isinstance(raw_item_keys, list):
                raw_item_keys = []

            canonical_keys: list[str] = []
            seen_keys: set[str] = set()
            for value in raw_item_keys:
                key = str(value or "").strip()
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                canonical_keys.append(key)

            normalized.append({"id": group_id, "name": group_name, "item_keys": canonical_keys})
        return normalized

    normalized_company = _normalize_group_rows(company_rows)
    normalized_location: dict[str, list[dict[str, Any]]] = {}
    for location_id, rows in location_rows.items():
        loc_key = str(location_id or "").strip()
        if not loc_key:
            continue
        normalized_rows = _normalize_group_rows(rows)
        if normalized_rows:
            normalized_location[loc_key] = normalized_rows

    normalized_defaults: dict[str, str] = {}
    for key, value in defaults_map.items():
        map_key = str(key or "").strip()
        map_value = str(value or "").strip()
        if map_key and map_value:
            normalized_defaults[map_key] = map_value

    return {
        "company": normalized_company,
        "location_overrides": normalized_location,
        "default_group_by_location": normalized_defaults,
    }


def _parse_inventory_group_saved_lists_payload(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        payload = raw_value
    elif isinstance(raw_value, dict):
        candidate = raw_value.get("lists")
        payload = candidate if isinstance(candidate, list) else []
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            payload = []
        else:
            try:
                decoded = json.loads(text)
            except Exception:
                decoded = []
            if isinstance(decoded, list):
                payload = decoded
            elif isinstance(decoded, dict) and isinstance(decoded.get("lists"), list):
                payload = decoded.get("lists")
            else:
                payload = []
    else:
        payload = []

    normalized: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        list_id = str(entry.get("id") or "").strip() or f"list_{uuid.uuid4().hex[:10]}"
        list_name = str(entry.get("name") or "").strip()
        if not list_name:
            continue
        config = _parse_inventory_default_groups_payload(entry.get("config"))
        normalized.append({"id": list_id, "name": list_name, "config": config})
    return normalized


def _load_inventory_default_groups_for_company(company_name: str) -> dict[str, Any]:
    context = _load_inventory_settings_context_for_company(company_name)
    config = context.get("config")
    if isinstance(config, dict):
        return config
    return _parse_inventory_default_groups_payload({})


def _inventory_location_key_candidates(selected_restaurant: dict[str, Any] | None) -> list[str]:
    candidates: list[str] = []
    if selected_restaurant:
        location_id = int(selected_restaurant.get("id") or 0)
        if location_id > 0:
            candidates.append(f"pm_{location_id}")
            candidates.append(str(location_id))
        location_name = str(selected_restaurant.get("location") or "").strip()
        if location_name:
            candidates.append(location_name)
    return candidates


def _normalize_product_id_list(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = [part.strip() for part in values.split(",")]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _merge_catch_all_order(previous_order: list[str], current_order: list[str]) -> list[str]:
    previous = _normalize_product_id_list(previous_order)
    current = _normalize_product_id_list(current_order)
    if not previous:
        return current

    current_set = set(current)
    merged: list[str] = []
    merged_set: set[str] = set()

    for product_id in previous:
        if product_id not in current_set or product_id in merged_set:
            continue
        merged_set.add(product_id)
        merged.append(product_id)

    for product_id in current:
        if product_id in merged_set:
            continue
        merged_set.add(product_id)
        merged.append(product_id)

    return merged


def _persist_inventory_settings_record(db_path: Path, company_id: str, settings_obj: dict[str, Any]) -> tuple[bool, str]:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE companies
            SET settings = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(settings_obj), datetime.now().isoformat(), company_id),
        )
        conn.commit()
        return True, ""
    except sqlite3.Error as exc:
        return False, str(exc)
    finally:
        conn.close()


def _load_inventory_settings_context_for_company(company_name: str) -> dict[str, Any]:
    normalized_company_name = str(company_name or "").strip()
    if not normalized_company_name:
        return {
            "db_path": None,
            "company_id": "",
            "settings": {},
            "config": _parse_inventory_default_groups_payload({}),
            "saved_lists": [],
            "active_list_by_location": {},
            "catch_all_by_location": {},
        }

    for db_path in _manager_db_candidates():
        if not db_path.exists():
            continue
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT id, settings
                FROM companies
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (normalized_company_name,),
            ).fetchone()
        except sqlite3.Error:
            row = None
        finally:
            conn.close()

        if not row:
            continue

        raw_settings = row["settings"]
        settings_obj: dict[str, Any]
        if isinstance(raw_settings, dict):
            settings_obj = raw_settings
        elif isinstance(raw_settings, str):
            text = raw_settings.strip()
            if not text:
                settings_obj = {}
            else:
                try:
                    decoded = json.loads(text)
                    settings_obj = decoded if isinstance(decoded, dict) else {}
                except Exception:
                    settings_obj = {}
        else:
            settings_obj = {}

        config = _parse_inventory_default_groups_payload(settings_obj.get("inventory_default_groups"))
        saved_lists = _parse_inventory_group_saved_lists_payload(settings_obj.get("inventory_group_saved_lists"))
        if not config.get("company"):
            if saved_lists:
                first_config = _parse_inventory_default_groups_payload((saved_lists[0] or {}).get("config"))
                if first_config.get("company") or first_config.get("location_overrides"):
                    config = first_config

        active_map_raw = settings_obj.get("inventory_active_list_by_location")
        active_map: dict[str, str] = {}
        if isinstance(active_map_raw, dict):
            for key, value in active_map_raw.items():
                map_key = str(key or "").strip()
                map_value = str(value or "").strip()
                if map_key and map_value:
                    active_map[map_key] = map_value

        catch_all_raw = settings_obj.get("inventory_catch_all_by_location")
        catch_all_map: dict[str, list[str]] = {}
        if isinstance(catch_all_raw, dict):
            for key, value in catch_all_raw.items():
                map_key = str(key or "").strip()
                if not map_key:
                    continue
                map_value = _normalize_product_id_list(value)
                if map_value:
                    catch_all_map[map_key] = map_value

        return {
            "db_path": db_path,
            "company_id": str(row["id"] or "").strip(),
            "settings": settings_obj,
            "config": config,
            "saved_lists": saved_lists,
            "active_list_by_location": active_map,
            "catch_all_by_location": catch_all_map,
        }

    return {
        "db_path": None,
        "company_id": "",
        "settings": {},
        "config": _parse_inventory_default_groups_payload({}),
        "saved_lists": [],
        "active_list_by_location": {},
        "catch_all_by_location": {},
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


@app.route("/api/shared/inventory-default-groups")
@login_required
def api_shared_inventory_default_groups() -> Response:
    selected_company_id = _effective_company_scope(require_active=True)
    selected_company_name = _selected_company_name_for_scope()
    selected_restaurant = _selected_restaurant_record_for_scope(selected_company_id)

    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    config = settings_context.get("config") if isinstance(settings_context, dict) else {}
    if not isinstance(config, dict):
        config = _parse_inventory_default_groups_payload({})
    saved_lists = settings_context.get("saved_lists") if isinstance(settings_context, dict) else []
    if not isinstance(saved_lists, list):
        saved_lists = []

    location_override_rows: list[dict[str, Any]] = []
    location_key_candidates = _inventory_location_key_candidates(selected_restaurant)

    overrides = config.get("location_overrides") if isinstance(config, dict) else {}
    if isinstance(overrides, dict):
        for key in location_key_candidates:
            rows = overrides.get(key)
            if isinstance(rows, list):
                location_override_rows = rows
                break

    company_rows = config.get("company") if isinstance(config, dict) else []
    if not isinstance(company_rows, list):
        company_rows = []

    groups = location_override_rows if location_override_rows else company_rows
    defaults_map = config.get("default_group_by_location") if isinstance(config, dict) else {}
    if not isinstance(defaults_map, dict):
        defaults_map = {}

    default_group_id = ""
    for key in location_key_candidates + ["*"]:
        candidate = str(defaults_map.get(key) or "").strip()
        if candidate:
            default_group_id = candidate
            break

    if default_group_id and not any(str((row or {}).get("id") or "").strip() == default_group_id for row in groups if isinstance(row, dict)):
        default_group_id = ""

    if not default_group_id and len(groups) == 1:
        default_group_id = str((groups[0] or {}).get("id") or "").strip()

    lists_payload: list[dict[str, Any]] = []
    seen_list_ids: set[str] = set()
    for item in saved_lists:
        if not isinstance(item, dict):
            continue
        list_id = str(item.get("id") or "").strip()
        list_name = str(item.get("name") or "").strip()
        if not list_id or not list_name or list_id in seen_list_ids:
            continue
        seen_list_ids.add(list_id)
        list_config = item.get("config") if isinstance(item.get("config"), dict) else _parse_inventory_default_groups_payload(item.get("config"))
        list_groups = list_config.get("company") if isinstance(list_config, dict) else []
        if not isinstance(list_groups, list):
            list_groups = []
        lists_payload.append(
            {
                "id": list_id,
                "name": list_name,
                "group_count": len(list_groups),
                "config": list_config,
            }
        )

    active_map = settings_context.get("active_list_by_location") if isinstance(settings_context, dict) else {}
    if not isinstance(active_map, dict):
        active_map = {}
    active_list_id = ""
    for key in location_key_candidates + ["*"]:
        candidate = str(active_map.get(key) or "").strip()
        if candidate:
            active_list_id = candidate
            break

    catch_all_by_location = settings_context.get("catch_all_by_location") if isinstance(settings_context, dict) else {}
    if not isinstance(catch_all_by_location, dict):
        catch_all_by_location = {}
    catch_all_item_keys: list[str] = []
    for key in location_key_candidates + ["*"]:
        candidate = catch_all_by_location.get(key)
        if isinstance(candidate, list) and candidate:
            catch_all_item_keys = _normalize_product_id_list(candidate)
            break

    response_payload = {
        "ok": bool(groups),
        "groups": groups,
        "default_group_id": default_group_id,
        "inventory_lists": lists_payload,
        "active_list_id": active_list_id,
        "catch_all_item_keys": catch_all_item_keys,
        "company_scope": {
            "id": int(selected_company_id) if selected_company_id is not None else None,
            "name": selected_company_name,
        },
        "location_scope": {
            "id": int(selected_restaurant["id"]) if selected_restaurant and selected_restaurant.get("id") else None,
            "location": str((selected_restaurant or {}).get("location") or ""),
            "key_candidates": location_key_candidates,
        },
        "message": "Inventory default groups loaded" if groups else "No shared inventory default groups configured",
    }

    return jsonify(response_payload)


@app.route("/api/shared/inventory-default-groups/active-list", methods=["GET", "POST"])
@csrf.exempt
@login_required
def api_shared_inventory_default_groups_active_list() -> Response:
    if request.method == "GET":
        requested_list_id = str(request.args.get("list_id") or "").strip()
    else:
        payload = request.get_json(silent=True) or {}
        requested_list_id = str((payload or {}).get("list_id") or "").strip()

    selected_company_id = _effective_company_scope(require_active=True)
    selected_company_name = _selected_company_name_for_scope()
    selected_restaurant = _selected_restaurant_record_for_scope(selected_company_id)

    location_key_candidates = _inventory_location_key_candidates(selected_restaurant)

    target_key = location_key_candidates[0] if location_key_candidates else "*"

    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    db_path = settings_context.get("db_path") if isinstance(settings_context, dict) else None
    company_id = str(settings_context.get("company_id") or "") if isinstance(settings_context, dict) else ""
    settings_obj = settings_context.get("settings") if isinstance(settings_context, dict) else {}

    if not isinstance(settings_obj, dict):
        settings_obj = {}
    if not db_path or not company_id:
        return jsonify({"ok": False, "message": "Unable to locate manager settings record for selected company"}), 404

    active_map_raw = settings_obj.get("inventory_active_list_by_location")
    active_map: dict[str, str] = {}
    if isinstance(active_map_raw, dict):
        for key, value in active_map_raw.items():
            map_key = str(key or "").strip()
            map_value = str(value or "").strip()
            if map_key and map_value:
                active_map[map_key] = map_value

    if requested_list_id:
        active_map[target_key] = requested_list_id
    else:
        active_map.pop(target_key, None)

    settings_obj["inventory_active_list_by_location"] = active_map

    ok, error_message = _persist_inventory_settings_record(db_path, company_id, settings_obj)
    if not ok:
        return jsonify({"ok": False, "message": f"Failed to persist active inventory list: {error_message}"}), 500

    return jsonify(
        {
            "ok": True,
            "active_list_id": str(active_map.get(target_key) or ""),
            "location_key": target_key,
            "company_scope": {
                "id": int(selected_company_id) if selected_company_id is not None else None,
                "name": selected_company_name,
            },
            "message": "Active inventory list updated",
        }
    )


@app.route("/api/shared/inventory-default-groups/catch-all-sync", methods=["POST"])
@csrf.exempt
@login_required
def api_shared_inventory_default_groups_catch_all_sync() -> Response:
    payload = request.get_json(silent=True) or {}
    current_product_ids = _normalize_product_id_list((payload or {}).get("product_ids"))

    selected_company_id = _effective_company_scope(require_active=True)
    selected_company_name = _selected_company_name_for_scope()
    selected_restaurant = _selected_restaurant_record_for_scope(selected_company_id)
    location_key_candidates = _inventory_location_key_candidates(selected_restaurant)
    target_key = location_key_candidates[0] if location_key_candidates else "*"

    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    db_path = settings_context.get("db_path") if isinstance(settings_context, dict) else None
    company_id = str(settings_context.get("company_id") or "") if isinstance(settings_context, dict) else ""
    settings_obj = settings_context.get("settings") if isinstance(settings_context, dict) else {}
    catch_all_by_location = settings_context.get("catch_all_by_location") if isinstance(settings_context, dict) else {}

    if not isinstance(settings_obj, dict):
        settings_obj = {}
    if not isinstance(catch_all_by_location, dict):
        catch_all_by_location = {}
    if not db_path or not company_id:
        return jsonify({"ok": False, "message": "Unable to locate manager settings record for selected company"}), 404

    previous_order: list[str] = []
    for key in location_key_candidates + ["*"]:
        candidate = catch_all_by_location.get(key)
        if isinstance(candidate, list) and candidate:
            previous_order = _normalize_product_id_list(candidate)
            break

    merged_order = _merge_catch_all_order(previous_order, current_product_ids)
    catch_all_by_location[target_key] = merged_order
    settings_obj["inventory_catch_all_by_location"] = catch_all_by_location

    ok, error_message = _persist_inventory_settings_record(db_path, company_id, settings_obj)
    if not ok:
        return jsonify({"ok": False, "message": f"Failed to persist Catch All list: {error_message}"}), 500

    return jsonify(
        {
            "ok": True,
            "location_key": target_key,
            "count": len(merged_order),
            "message": "Catch All order synced",
        }
    )


@app.route("/api/shared/inventory-default-groups/list-create", methods=["POST"])
@csrf.exempt
@login_required
def api_shared_inventory_list_create() -> Response:
    payload = request.get_json(silent=True) or {}
    list_name = str((payload or {}).get("name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "message": "List name is required"}), 400
    if list_name.lower() == "catch all":
        return jsonify({"ok": False, "message": "Catch All is reserved"}), 400

    selected_company_name = _selected_company_name_for_scope()
    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    db_path = settings_context.get("db_path") if isinstance(settings_context, dict) else None
    company_id = str(settings_context.get("company_id") or "") if isinstance(settings_context, dict) else ""
    settings_obj = settings_context.get("settings") if isinstance(settings_context, dict) else {}
    if not isinstance(settings_obj, dict):
        settings_obj = {}
    if not db_path or not company_id:
        return jsonify({"ok": False, "message": "Unable to locate manager settings record for selected company"}), 404

    config = _parse_inventory_default_groups_payload(settings_obj.get("inventory_default_groups"))
    company_groups = config.get("company") if isinstance(config.get("company"), list) else []

    normalized_name = list_name.casefold()
    for group in company_groups:
        existing_name = str((group or {}).get("name") or "").strip()
        if existing_name and existing_name.casefold() == normalized_name:
            return jsonify({"ok": False, "message": "A list with that name already exists"}), 409

    new_group_id = f"grp_{uuid.uuid4().hex[:10]}"
    company_groups.append({"id": new_group_id, "name": list_name, "item_keys": []})
    config["company"] = company_groups
    settings_obj["inventory_default_groups"] = config

    ok, error_message = _persist_inventory_settings_record(db_path, company_id, settings_obj)
    if not ok:
        return jsonify({"ok": False, "message": f"Failed to create list: {error_message}"}), 500

    return jsonify({"ok": True, "id": new_group_id, "name": list_name, "message": "List created"})


@app.route("/api/shared/inventory-default-groups/list-rename", methods=["POST"])
@csrf.exempt
@login_required
def api_shared_inventory_list_rename() -> Response:
    payload = request.get_json(silent=True) or {}
    list_id = str((payload or {}).get("list_id") or "").strip()
    list_name = str((payload or {}).get("name") or "").strip()
    if not list_id or not list_name:
        return jsonify({"ok": False, "message": "list_id and name are required"}), 400
    if list_id == "catch_all":
        return jsonify({"ok": False, "message": "Catch All cannot be renamed"}), 400

    selected_company_name = _selected_company_name_for_scope()
    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    db_path = settings_context.get("db_path") if isinstance(settings_context, dict) else None
    company_id = str(settings_context.get("company_id") or "") if isinstance(settings_context, dict) else ""
    settings_obj = settings_context.get("settings") if isinstance(settings_context, dict) else {}
    if not isinstance(settings_obj, dict):
        settings_obj = {}
    if not db_path or not company_id:
        return jsonify({"ok": False, "message": "Unable to locate manager settings record for selected company"}), 404

    config = _parse_inventory_default_groups_payload(settings_obj.get("inventory_default_groups"))
    company_groups = config.get("company") if isinstance(config.get("company"), list) else []

    found = False
    for group in company_groups:
        if str((group or {}).get("id") or "").strip() == list_id:
            group["name"] = list_name
            found = True
            break
    if not found:
        return jsonify({"ok": False, "message": "List not found"}), 404

    config["company"] = company_groups
    settings_obj["inventory_default_groups"] = config
    ok, error_message = _persist_inventory_settings_record(db_path, company_id, settings_obj)
    if not ok:
        return jsonify({"ok": False, "message": f"Failed to rename list: {error_message}"}), 500

    return jsonify({"ok": True, "message": "List renamed"})


@app.route("/api/shared/inventory-default-groups/list-delete", methods=["POST"])
@csrf.exempt
@login_required
def api_shared_inventory_list_delete() -> Response:
    payload = request.get_json(silent=True) or {}
    list_id = str((payload or {}).get("list_id") or "").strip()
    if not list_id:
        return jsonify({"ok": False, "message": "list_id is required"}), 400
    if list_id == "catch_all":
        return jsonify({"ok": False, "message": "Catch All cannot be deleted"}), 400

    selected_company_name = _selected_company_name_for_scope()
    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    db_path = settings_context.get("db_path") if isinstance(settings_context, dict) else None
    company_id = str(settings_context.get("company_id") or "") if isinstance(settings_context, dict) else ""
    settings_obj = settings_context.get("settings") if isinstance(settings_context, dict) else {}
    if not isinstance(settings_obj, dict):
        settings_obj = {}
    if not db_path or not company_id:
        return jsonify({"ok": False, "message": "Unable to locate manager settings record for selected company"}), 404

    config = _parse_inventory_default_groups_payload(settings_obj.get("inventory_default_groups"))
    company_groups = config.get("company") if isinstance(config.get("company"), list) else []
    next_groups = [group for group in company_groups if str((group or {}).get("id") or "").strip() != list_id]
    if len(next_groups) == len(company_groups):
        return jsonify({"ok": False, "message": "List not found"}), 404
    config["company"] = next_groups

    defaults_map = config.get("default_group_by_location") if isinstance(config.get("default_group_by_location"), dict) else {}
    cleaned_defaults: dict[str, str] = {}
    for key, value in defaults_map.items():
        map_key = str(key or "").strip()
        map_value = str(value or "").strip()
        if map_key and map_value and map_value != list_id:
            cleaned_defaults[map_key] = map_value
    config["default_group_by_location"] = cleaned_defaults
    settings_obj["inventory_default_groups"] = config

    active_map_raw = settings_obj.get("inventory_active_list_by_location")
    if isinstance(active_map_raw, dict):
        settings_obj["inventory_active_list_by_location"] = {
            str(key or "").strip(): str(value or "").strip()
            for key, value in active_map_raw.items()
            if str(key or "").strip() and str(value or "").strip() and str(value or "").strip() != list_id
        }

    ok, error_message = _persist_inventory_settings_record(db_path, company_id, settings_obj)
    if not ok:
        return jsonify({"ok": False, "message": f"Failed to delete list: {error_message}"}), 500

    return jsonify({"ok": True, "message": "List deleted"})


@app.route("/api/shared/inventory-default-groups/list-items", methods=["POST"])
@csrf.exempt
@login_required
def api_shared_inventory_list_items() -> Response:
    payload = request.get_json(silent=True) or {}
    list_id = str((payload or {}).get("list_id") or "").strip()
    item_keys = _normalize_product_id_list((payload or {}).get("item_keys"))
    if not list_id:
        return jsonify({"ok": False, "message": "list_id is required"}), 400
    if list_id == "catch_all":
        return jsonify({"ok": False, "message": "Catch All is system-managed"}), 400

    selected_company_name = _selected_company_name_for_scope()
    settings_context = _load_inventory_settings_context_for_company(selected_company_name)
    db_path = settings_context.get("db_path") if isinstance(settings_context, dict) else None
    company_id = str(settings_context.get("company_id") or "") if isinstance(settings_context, dict) else ""
    settings_obj = settings_context.get("settings") if isinstance(settings_context, dict) else {}
    if not isinstance(settings_obj, dict):
        settings_obj = {}
    if not db_path or not company_id:
        return jsonify({"ok": False, "message": "Unable to locate manager settings record for selected company"}), 404

    config = _parse_inventory_default_groups_payload(settings_obj.get("inventory_default_groups"))
    company_groups = config.get("company") if isinstance(config.get("company"), list) else []

    found = False
    for group in company_groups:
        if str((group or {}).get("id") or "").strip() == list_id:
            group["item_keys"] = item_keys
            found = True
            break
    if not found:
        return jsonify({"ok": False, "message": "List not found"}), 404

    config["company"] = company_groups
    settings_obj["inventory_default_groups"] = config
    ok, error_message = _persist_inventory_settings_record(db_path, company_id, settings_obj)
    if not ok:
        return jsonify({"ok": False, "message": f"Failed to save list items: {error_message}"}), 500

    return jsonify({"ok": True, "count": len(item_keys), "message": "List items saved"})

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
@role_required("Super Admin", "Manager")
def api_start_all() -> Response:
    result = MANAGER.start_all()
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

@app.route("/api/stop-all", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_stop_all() -> Response:
    return jsonify(MANAGER.stop_all())

@app.route("/api/apps/<name>/start", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_start(name: str) -> Response:
    result = MANAGER.start(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

@app.route("/api/apps/<name>/stop", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_stop(name: str) -> Response:
    result = MANAGER.stop(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code

@app.route("/api/apps/<name>/restart", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
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

    if not MANAGER.is_running(resolved_name):
        start_result = MANAGER.start(resolved_name)
        if not start_result.get("ok"):
            error_msg = str(start_result.get("message") or "Upstream app failed to start")
            retry_after = int(start_result.get("retry_after_sec") or MANAGER.retry_after_seconds(resolved_name) or 0)
            print(f"[_proxy] Failed to start {resolved_name}: {error_msg}", file=sys.stderr)
            payload = {
                "ok": False,
                "message": f"{CONFIG['apps'][resolved_name]['display_name']} is temporarily unavailable. Please retry in a moment.",
            }
            log_tail = str(start_result.get("log_tail") or "").strip()
            if log_tail:
                payload["startup_log_tail"] = log_tail
            if retry_after > 0:
                payload["retry_after_sec"] = retry_after
            response = jsonify(payload)
            response.status_code = 503
            if retry_after > 0:
                response.headers["Retry-After"] = str(retry_after)
            return response
        _app_host, _app_port = MANAGER._parse_host_port(MANAGER.get_base_url(resolved_name))
        app_ready = False
        for attempt in range(8):
            if is_port_open(_app_host, _app_port):
                app_ready = True
                break
            time.sleep(min(2.0, 0.2 * (2 ** attempt)))
        if not app_ready:
            response = jsonify({
                "ok": False,
                "message": f"{CONFIG['apps'][resolved_name]['display_name']} is starting up. Please retry in a moment.",
                "retry_after_sec": 5,
            })
            response.status_code = 503
            response.headers["Retry-After"] = "5"
            return response

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
                timeout=(UPSTREAM_CONNECT_TIMEOUT_SEC, UPSTREAM_READ_TIMEOUT_SEC),
            )

        if is_form_encoded:
            return requests.request(
                method=request.method,
                url=target,
                headers=_without_content_type(forward_headers),
                data=_form_pairs(),
                cookies=request.cookies,
                allow_redirects=False,
                timeout=(UPSTREAM_CONNECT_TIMEOUT_SEC, UPSTREAM_READ_TIMEOUT_SEC),
            )

        return requests.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=(UPSTREAM_CONNECT_TIMEOUT_SEC, UPSTREAM_READ_TIMEOUT_SEC),
        )

    try:
        upstream = _request_upstream()
    except requests.RequestException as exc:
        try:
            restart_result = MANAGER.restart(resolved_name)
            if not restart_result.get("ok"):
                retry_after = int(restart_result.get("retry_after_sec") or MANAGER.retry_after_seconds(resolved_name) or 0)
                payload = {
                    "ok": False,
                    "message": f"{CONFIG['apps'][resolved_name]['display_name']} is temporarily unavailable. Please retry in a moment.",
                }
                log_tail = str(restart_result.get("log_tail") or "").strip()
                if log_tail:
                    payload["startup_log_tail"] = log_tail
                if retry_after > 0:
                    payload["retry_after_sec"] = retry_after
                response = jsonify(payload)
                response.status_code = 503
                if retry_after > 0:
                    response.headers["Retry-After"] = str(retry_after)
                return response
            _app_host2, _app_port2 = MANAGER._parse_host_port(MANAGER.get_base_url(resolved_name))
            for attempt in range(8):
                time.sleep(min(2.0, 0.2 * (2 ** attempt)))
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

# ----- Auto-sync API endpoints -----
@app.route("/api/admin/autosync/status", methods=["GET"])
@login_required
def autosync_status():
    """Get auto-sync status and configuration"""
    try:
        autosync_enabled = _env_flag("DEXTER_AUTOSYNC_ENABLED", default=True)
        autosync_interval = int(os.environ.get("DEXTER_AUTOSYNC_INTERVAL_MINUTES", "30"))
        
        return jsonify({
            "ok": True,
            "autosync_enabled": autosync_enabled,
            "autosync_interval_minutes": autosync_interval,
            "tracked_folders": [
                "ProductMixRestaurantDB/",
                "daily_logs/",
                "inventory_data/",
                "Dexter Assist 6-3-26/Dexter Assistant/Inventory Control 3/data/"
            ]
        })
    except Exception as e:
        print(f"[dexter autosync] Failed to get autosync status: {e}", file=sys.stderr)
        return jsonify({"ok": False, "message": str(e)}), 500

@app.route("/api/admin/autosync/sync-now", methods=["POST"])
@login_required
def autosync_sync_now():
    """Manually trigger an immediate git sync"""
    try:
        from auto_sync_git import GitAutoSync
        syncer = GitAutoSync(ROOT.parent)
        result = syncer.sync_database_files()
        
        return jsonify({
            "ok": result.get("success", False),
            "message": result.get("message", ""),
            "synced_at": result.get("synced_at", ""),
            "files_changed": result.get("files_changed", [])
        })
    except ImportError:
        return jsonify({
            "ok": False,
            "message": "Auto-sync module not available"
        }), 503
    except Exception as e:
        print(f"[dexter autosync] Manual sync failed: {e}", file=sys.stderr)
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/admin/backups/managerapp/status", methods=["GET"])
@login_required
@role_required("Super Admin")
def manager_backup_status() -> Response:
    payload = _manager_backup_status_payload()
    status = 200 if payload.get("ok") else 503
    return jsonify(payload), status


@app.route("/api/admin/backups/managerapp/run", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin")
def manager_backup_run_now() -> Response:
    payload = _run_manager_backup("manual")
    status = 200 if payload.get("ok") else 500
    return jsonify(payload), status


def _copy_file_with_backup(src: Path, dst: Path, backup_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": str(src),
        "destination": str(dst),
        "copied": False,
        "backed_up": False,
    }
    if not src.exists() or not src.is_file():
        result["error"] = "Source file missing"
        return result

    # Render can mount paths such that a "source" path and target path are the same inode.
    if dst.exists():
        try:
            if src.samefile(dst):
                result["copied"] = True
                result["skipped"] = "Source and destination are identical"
                result["bytes"] = int(dst.stat().st_size)
                return result
        except OSError:
            pass

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.is_file():
        rel = str(dst).lstrip("/\\").replace(":", "_")
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, backup_path)
        result["backed_up"] = True
        result["backup_path"] = str(backup_path)

    shutil.copy2(src, dst)
    result["copied"] = True
    result["bytes"] = int(dst.stat().st_size)
    return result


def _manager_backup_config() -> dict[str, Any]:
    keep_snapshots = max(1, int(os.environ.get("DEXTER_MGR_BACKUP_KEEP_SNAPSHOTS", "672")))
    enabled = _env_flag("DEXTER_MGR_BACKUP_ENABLED", default=True)
    nas_enabled = _env_flag("DEXTER_NAS_BACKUP_ENABLED", default=(os.name == "nt"))
    nas_required = _env_flag("DEXTER_NAS_BACKUP_REQUIRED", default=False)
    nas_root = str((os.environ.get("DEXTER_NAS_BACKUP_ROOT") or DEFAULT_NAS_BACKUP_ROOT).strip())
    critical_schedule_raw = os.environ.get("DEXTER_MGR_CRITICAL_BACKUP_TIMES", "00:00,00:30,01:00,01:30,02:00,02:30,03:00,03:30,04:00,04:30,05:00,05:30,06:00,06:30,07:00,07:30,08:00,08:30,09:00,09:30,10:00,10:30,11:00,11:30,12:00,12:30,13:00,13:30,14:00,14:30,15:00,15:30,16:00,16:30,17:00,17:30,18:00,18:30,19:00,19:30,20:00,20:30,21:00,21:30,22:00,22:30,23:00,23:30")
    daily_full_backup_time = os.environ.get("DEXTER_MGR_FULL_BACKUP_TIME", "23:45").strip() or "23:45"
    critical_schedule_times: list[str] = []
    for part in critical_schedule_raw.split(","):
        value = part.strip()
        if value and re.fullmatch(r"\d{2}:\d{2}", value):
            critical_schedule_times.append(value)
    return {
        "enabled": enabled,
        "keep_snapshots": keep_snapshots,
        "nas_enabled": nas_enabled,
        "nas_required": nas_required,
        "nas_root": nas_root,
        "critical_schedule_times": critical_schedule_times or ["00:00", "00:30"],
        "full_backup_time": daily_full_backup_time if re.fullmatch(r"\d{2}:\d{2}", daily_full_backup_time) else "23:45",
    }


def _manager_backup_paths() -> dict[str, Path]:
    persistent_root = _render_data_root if _render_data_root.exists() else ROOT
    manager_root = persistent_root / "managerapp"
    nas_root_raw = (os.environ.get("DEXTER_NAS_BACKUP_ROOT") or DEFAULT_NAS_BACKUP_ROOT).strip()
    return {
        "persistent_root": persistent_root,
        "manager_root": manager_root,
        "db_path": manager_root / "manager_app.db",
        "company_data_path": manager_root / "company_data",
        "backup_root": persistent_root / "backups" / "managerapp",
        "auth_users_path": AUTH_USERS_PATH,
        "rbac_db_path": RBAC_DB_PATH,
        "ic3_data_path": Path(os.environ.get("IC3_DATA_DIR") or (ROOT / "Inventory Control 3" / "data")),
        "productmix_root": Path(os.environ.get("PM_DB_DIR") or (ROOT / "ProductMixRestaurantDB")),
        "inventory_data_root": ROOT / "inventory_data",
        "daily_logs_root": ROOT / "daily_logs",
        "uploads_root": ROOT / "uploads",
        "order_invoices_root": ROOT / "OrderInvoices",
        "reports_root": ROOT / "reports",
        "nas_backup_root": Path(nas_root_raw),
    }


def _hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _update_manager_backup_state(payload: dict[str, Any]) -> None:
    global _MGR_BACKUP_LAST_RUN
    with _MGR_BACKUP_STATE_LOCK:
        _MGR_BACKUP_LAST_RUN = payload


def _manager_backup_status_payload() -> dict[str, Any]:
    cfg = _manager_backup_config()
    with _MGR_BACKUP_STATE_LOCK:
        last_run = dict(_MGR_BACKUP_LAST_RUN) if _MGR_BACKUP_LAST_RUN else None

    payload: dict[str, Any] = {
        "ok": bool(cfg["enabled"]),
        "config": cfg,
        "paths": {k: str(v) for k, v in _manager_backup_paths().items()},
        "last_run": last_run,
    }

    if not cfg["enabled"]:
        payload["ok"] = False
        payload["message"] = "Manager backup scheduler disabled"
        return payload

    if last_run is None:
        payload["ok"] = False
        payload["message"] = "No backup has run yet"
        return payload

    if not last_run.get("ok"):
        payload["ok"] = False
        payload["message"] = str(last_run.get("message") or "Last backup failed")
        return payload

    try:
        finished_at = datetime.fromisoformat(str(last_run.get("finished_at", "")))
        age_seconds = int((datetime.utcnow() - finished_at).total_seconds())
    except Exception:
        age_seconds = -1

    payload["last_backup_age_seconds"] = age_seconds
    stale_threshold = int(cfg["interval_minutes"]) * 60 * 2
    if age_seconds < 0 or age_seconds > stale_threshold:
        payload["ok"] = False
        payload["message"] = "Last backup is stale"
    else:
        payload["message"] = "Backup status healthy"

    return payload


def _collect_snapshot_operations(snapshot_dir: Path, paths: dict[str, Path], mode: str) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []

    def copy_file(src: Path, dst_name: str, label: str) -> None:
        op: dict[str, Any] = {"type": label, "source": str(src), "copied": False}
        if src.exists() and src.is_file():
            dst = snapshot_dir / dst_name
            shutil.copy2(src, dst)
            op.update({"copied": True, "bytes": int(dst.stat().st_size), "sha256": _hash_file_sha256(dst)})
        else:
            op["warning"] = f"{label} missing"
        operations.append(op)

    def copy_dir(src: Path, dst_name: str, label: str) -> None:
        op: dict[str, Any] = {"type": label, "source": str(src), "copied": False}
        if src.exists() and src.is_dir():
            dst = snapshot_dir / dst_name
            shutil.copytree(src, dst, dirs_exist_ok=True)
            op.update({"copied": True, "file_count": int(sum(1 for p in dst.rglob("*") if p.is_file()))})
        else:
            op["warning"] = f"{label} missing"
        operations.append(op)

    copy_file(paths["db_path"], "manager_app.db", "manager_db")
    copy_dir(paths["company_data_path"], "company_data", "company_data")
    copy_file(paths["auth_users_path"], "dexter_assistant_users.json", "auth_users")
    copy_file(paths["rbac_db_path"], "dexter_assistant_rbac.db", "rbac_db")
    copy_dir(paths["ic3_data_path"], "ic3_data", "ic3_data")

    if mode == "full":
        copy_dir(paths["productmix_root"], "ProductMixRestaurantDB", "productmix_root")
        copy_dir(paths["inventory_data_root"], "inventory_data", "inventory_data")
        copy_dir(paths["daily_logs_root"], "daily_logs", "daily_logs")
        copy_dir(paths["uploads_root"], "uploads", "uploads")
        copy_dir(paths["order_invoices_root"], "OrderInvoices", "order_invoices")
        copy_dir(paths["reports_root"], "reports", "reports")

    return operations


def _run_manager_backup(trigger: str, mode: str = "critical") -> dict[str, Any]:
    started_at = datetime.utcnow()
    cfg = _manager_backup_config()
    paths = _manager_backup_paths()
    backup_root = paths["backup_root"]

    result: dict[str, Any] = {
        "ok": False,
        "trigger": trigger,
        "started_at": started_at.isoformat(),
        "finished_at": started_at.isoformat(),
        "snapshot_dir": "",
        "mode": mode,
        "operations": [],
        "message": "",
        "pruned": [],
        "nas_sync": {"enabled": False, "copied": False, "path": "", "error": ""},
        "nas_pruned": [],
    }

    try:
        if not cfg["enabled"] and trigger != "manual":
            result["message"] = "Backups disabled"
            result["ok"] = True
            return result

        persistent_root = paths["persistent_root"]
        if not persistent_root.exists():
            raise RuntimeError(f"Persistent data root missing: {persistent_root}")

        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        snapshot_dir = backup_root / f"{mode}_snapshot_{stamp}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        result["snapshot_dir"] = str(snapshot_dir)
        result["operations"].extend(_collect_snapshot_operations(snapshot_dir, paths, mode))

        manifest = {
            "created_at": datetime.utcnow().isoformat(),
            "trigger": trigger,
            "config": cfg,
            "paths": {k: str(v) for k, v in paths.items()},
            "operations": result["operations"],
        }
        manifest_path = snapshot_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Optional NAS replication for off-host resilience.
        cfg_nas_enabled = bool(cfg.get("nas_enabled"))
        cfg_nas_required = bool(cfg.get("nas_required"))
        if cfg_nas_enabled:
            result["nas_sync"]["enabled"] = True
            nas_root = paths["nas_backup_root"] / "managerapp"
            nas_target = nas_root / snapshot_dir.name
            result["nas_sync"]["path"] = str(nas_target)
            try:
                nas_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(snapshot_dir, nas_target, dirs_exist_ok=True)
                result["nas_sync"]["copied"] = True
                cutoff = datetime.utcnow().timestamp() - (15 * 24 * 60 * 60)
                for old_snapshot in sorted([p for p in nas_root.glob("snapshot_*") if p.is_dir()], key=lambda p: p.name):
                    try:
                        if old_snapshot.stat().st_mtime < cutoff:
                            shutil.rmtree(old_snapshot, ignore_errors=True)
                            result["nas_pruned"].append(str(old_snapshot))
                    except OSError:
                        continue
            except Exception as nas_exc:
                result["nas_sync"]["error"] = str(nas_exc)
                if cfg_nas_required:
                    raise RuntimeError(f"NAS backup required but failed: {nas_exc}")

        snapshots = sorted(
            [p for p in backup_root.glob("snapshot_*") if p.is_dir()],
            key=lambda p: p.name,
        )
        keep = int(cfg["keep_snapshots"])
        if len(snapshots) > keep:
            for old in snapshots[: len(snapshots) - keep]:
                shutil.rmtree(old, ignore_errors=True)
                result["pruned"].append(str(old))

        result["ok"] = True
        result["message"] = "Backup completed"
        return result
    except Exception as exc:
        result["ok"] = False
        result["message"] = str(exc)
        return result
    finally:
        result["finished_at"] = datetime.utcnow().isoformat()
        _update_manager_backup_state(result)


def _start_manager_backup_scheduler() -> None:
    global _MGR_BACKUP_THREAD_STARTED
    cfg = _manager_backup_config()
    if not cfg["enabled"]:
        print("[dexter backup] Manager backup scheduler disabled", file=sys.stderr)
        return

    if _MGR_BACKUP_THREAD_STARTED:
        return

    def _loop() -> None:
        # Run one backup shortly after startup to create an initial restore point.
        try:
            _run_manager_backup("startup-critical", mode="critical")
        except Exception as exc:
            print(f"[dexter backup] Startup backup failed: {exc}", file=sys.stderr)

        last_critical_run_slot: str | None = None
        last_full_run_date: str | None = None
        while True:
            cfg_loop = _manager_backup_config()
            schedule_times = list(cfg_loop.get("critical_schedule_times") or ["00:00", "00:30"])
            now = datetime.now()
            todays_slots = [
                now.replace(hour=int(slot.split(":")[0]), minute=int(slot.split(":")[1]), second=0, microsecond=0)
                for slot in schedule_times
            ]
            next_run = min((slot for slot in todays_slots if slot > now), default=None)
            if next_run is None:
                next_run = (now + timedelta(days=1)).replace(
                    hour=int(schedule_times[0].split(":")[0]),
                    minute=int(schedule_times[0].split(":")[1]),
                    second=0,
                    microsecond=0,
                )

            wait_seconds = max(60, int((next_run - now).total_seconds()))
            time.sleep(wait_seconds)

            run_now = datetime.now().replace(second=0, microsecond=0)
            today_key = run_now.strftime("%Y-%m-%d")
            full_backup_time = cfg_loop.get("full_backup_time") or "23:45"
            full_target = run_now.replace(hour=int(str(full_backup_time).split(":")[0]), minute=int(str(full_backup_time).split(":")[1]))
            if abs((run_now - full_target).total_seconds()) <= 120 and last_full_run_date != today_key:
                try:
                    _run_manager_backup(f"scheduled-full-{today_key}", mode="full")
                    last_full_run_date = today_key
                except Exception as exc:
                    print(f"[dexter backup] Scheduled full backup failed: {exc}", file=sys.stderr)

            for slot in schedule_times:
                target = run_now.replace(hour=int(slot.split(":")[0]), minute=int(slot.split(":")[1]))
                if abs((run_now - target).total_seconds()) <= 120:
                    last_result = _MGR_BACKUP_LAST_RUN
                    if last_critical_run_slot == slot and last_result and last_result.get("trigger") == f"scheduled-critical-{slot}":
                        continue
                    try:
                        _run_manager_backup(f"scheduled-critical-{slot}", mode="critical")
                        last_critical_run_slot = slot
                    except Exception as exc:
                        print(f"[dexter backup] Scheduled backup failed ({slot}): {exc}", file=sys.stderr)
                    break

    t = threading.Thread(target=_loop, name="dexter-manager-backup", daemon=True)
    t.start()
    _MGR_BACKUP_THREAD_STARTED = True
    print(
        f"[dexter backup] Manager backup scheduler started (critical: {', '.join(cfg['critical_schedule_times'])}, full: {cfg['full_backup_time']}, keep: {cfg['keep_snapshots']})",
        file=sys.stderr,
    )


try:
    _start_manager_backup_scheduler()
except Exception as e:
    print(f"[dexter backup] Warning: Failed to initialize manager backup scheduler: {e}", file=sys.stderr)


@app.route("/api/admin/migrate-local-data", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin")
def api_admin_migrate_local_data() -> Response:
    try:
        ic3_data_dir = Path(os.environ.get("IC3_DATA_DIR") or (ROOT / "Inventory Control 3" / "data"))
        pm_db_dir = Path(os.environ.get("PM_DB_DIR") or (ROOT / "ProductMixRestaurantDB"))

        src_ic3_data_dir = ROOT / "Inventory Control 3" / "data"
        src_pm_db = ROOT / "ProductMixRestaurantDB" / "product_mix.db"

        dst_pm_db = pm_db_dir / "product_mix.db"

        backup_base = Path("/dexter-data/backups") if Path("/dexter-data").exists() else (ROOT / "migration_backups")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = backup_base / f"manual_migration_{stamp}"
        backup_root.mkdir(parents=True, exist_ok=True)

        source_files = [
            (src_ic3_data_dir / "inventory_database.json", ic3_data_dir / "inventory_database.json"),
            (src_ic3_data_dir / "orders_database.json", ic3_data_dir / "orders_database.json"),
            (src_ic3_data_dir / "invoice_import_log.json", ic3_data_dir / "invoice_import_log.json"),
            (src_ic3_data_dir / "order_price_log.json", ic3_data_dir / "order_price_log.json"),
            (src_pm_db, dst_pm_db),
        ]

        operations: list[dict[str, Any]] = []
        for src, dst in source_files:
            operations.append(_copy_file_with_backup(src, dst, backup_root))

        copied_count = sum(1 for op in operations if op.get("copied"))
        failed = [op for op in operations if not op.get("copied")]
        ok = len(failed) == 0

        return jsonify(
            {
                "ok": ok,
                "message": "Migration completed" if ok else "Migration completed with missing sources",
                "copied_count": copied_count,
                "failed_count": len(failed),
                "backup_root": str(backup_root),
                "operations": operations,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "message": f"Migration failed: {exc}"}), 500

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