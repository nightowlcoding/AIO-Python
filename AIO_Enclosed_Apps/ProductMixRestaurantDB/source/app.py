from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, has_request_context, session, g, flash
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pandas as pd
import math
import io
import csv
import json
import sqlite3
import re
import os
import time
import uuid
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pathlib import Path
from datetime import datetime
from jinja2 import TemplateNotFound

APP_DIR = Path(__file__).resolve().parent
LOCAL_TEMPLATE_DIR = APP_DIR / "templates"
WORKSPACE_TEMPLATE_DIR = APP_DIR.parent / "templates"

if (LOCAL_TEMPLATE_DIR / "index.html").exists():
    TEMPLATE_DIR = LOCAL_TEMPLATE_DIR
elif (WORKSPACE_TEMPLATE_DIR / "index.html").exists():
    TEMPLATE_DIR = WORKSPACE_TEMPLATE_DIR
else:
    TEMPLATE_DIR = LOCAL_TEMPLATE_DIR

app = Flask(__name__, template_folder=str(TEMPLATE_DIR))

app.config["SECRET_KEY"] = os.environ.get("PM_SECRET_KEY", "dev-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("PM_SECURE_COOKIE", "0") == "1"
_upload_limit_raw = str(os.environ.get("PM_MAX_UPLOAD_BYTES", "0") or "0").strip()
try:
    UPLOAD_MAX_BYTES = int(_upload_limit_raw)
except ValueError:
    UPLOAD_MAX_BYTES = 0

# 0 (default) means no Flask request-body cap. Set PM_MAX_UPLOAD_BYTES to enforce one.
app.config["MAX_CONTENT_LENGTH"] = UPLOAD_MAX_BYTES if UPLOAD_MAX_BYTES > 0 else None
FORMULA_MODE = os.environ.get("PM_FORMULA_MODE", "1") == "1"

if FORMULA_MODE:
    # Temporary bypass so formula/debug work can proceed without auth gates.
    def login_required(func):
        return func

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri=os.environ.get("PM_RATE_LIMIT_STORAGE", "memory://"),
)

DB_PATH = Path(__file__).parent / "product_mix.db"
ALLOWED_UPLOAD_EXTS = {".xlsx", ".xls"}
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",
}


def _clean_text(value, max_len):
    text = (value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def _normalize_item_key(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _parse_float_bounded(raw_value, label, min_val, max_val, allow_empty=False):
    raw = (raw_value or "").strip()
    if raw == "":
        if allow_empty:
            return None, None
        return min_val, None

    try:
        value = float(raw)
    except ValueError:
        return None, f"{label} must be a valid number."

    if value < min_val or value > max_val:
        return None, f"{label} must be between {min_val} and {max_val}."
    return value, None


def _validate_restaurant_payload(source):
    payload = {
        "name": _clean_text(source.get("name"), 100),
        "location": _clean_text(source.get("location"), 120),
        "address": _clean_text(source.get("address"), 200),
        "city": _clean_text(source.get("city"), 80),
        "state": _clean_text(source.get("state"), 30),
        "zip_code": _clean_text(source.get("zip_code"), 15),
        "phone": _clean_text(source.get("phone"), 25),
    }

    if not payload["name"]:
        return None, "Restaurant name is required"

    if payload["phone"] and not re.match(r"^[0-9+()\-\s]{7,25}$", payload["phone"]):
        return None, "Phone format is invalid"

    if payload["zip_code"] and not re.match(r"^[A-Za-z0-9\-\s]{3,15}$", payload["zip_code"]):
        return None, "Zip code format is invalid"

    return payload, None


def _restaurant_change_set(existing_row, incoming_payload):
    changes = {}
    tracked_fields = ["name", "location", "address", "city", "state", "zip_code", "phone"]
    for field in tracked_fields:
        previous = existing_row[field]
        updated = incoming_payload[field]
        if previous != updated:
            changes[field] = {
                "from": previous,
                "to": updated,
            }
    return changes


def _format_audit_changes(changes_json):
    try:
        parsed = json.loads(changes_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return "Invalid change payload"

    parts = []
    for field, values in parsed.items():
        before = values.get("from") if isinstance(values, dict) else None
        after = values.get("to") if isinstance(values, dict) else None
        parts.append(f"{field}: {before or ''} -> {after or ''}")

    return "; ".join(parts) if parts else "No field changes"


def _validate_category_payload(source):
    name = _clean_text(source.get("name"), 100)
    if not name:
        return None, "Category name is required"

    case_quantity_val, case_error = _parse_float_bounded(
        source.get("case_quantity", "0"),
        "Case quantity",
        0,
        100000,
    )
    if case_error:
        return None, case_error

    oz_per_piece_val, oz_error = _parse_float_bounded(
        source.get("oz_per_piece", ""),
        "Oz per piece",
        0,
        1000,
        allow_empty=True,
    )
    if oz_error:
        return None, oz_error

    is_weight_based = 1 if source.get("is_weight_based") == "on" else 0

    return {
        "name": name,
        "case_quantity": case_quantity_val,
        "oz_per_piece": oz_per_piece_val,
        "is_weight_based": is_weight_based,
    }, None


def _get_or_create_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = uuid.uuid4().hex
        session["csrf_token"] = token
    return token


def _is_csrf_valid(candidate_token):
    if not candidate_token:
        return False
    expected = session.get("csrf_token")
    return bool(expected) and expected == candidate_token


def _is_api_request():
    return request.path.startswith("/api/") or request.path in {"/upload", "/export"}


def _wants_json_response():
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    if best == "application/json":
        return request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]
    return False


def _error_response(message, status_code, code):
    request_id = getattr(g, "request_id", None)

    if _is_api_request():
        payload = {
            "error": message,
            "code": code,
        }
        if request_id:
            payload["request_id"] = request_id
        return jsonify(payload), status_code

    try:
        return render_template(
            "error.html",
            error_title=code.replace("_", " ").title(),
            error_message=message,
            status_code=status_code,
        ), status_code
    except TemplateNotFound:
        html = (
            "<!doctype html><html><head><meta charset='utf-8'><title>Error</title></head>"
            "<body><h1>Application Error</h1>"
            f"<p>{message}</p><p>Status: {status_code}</p></body></html>"
        )
        return html, status_code


@app.context_processor
def inject_csrf_token():
    payload = {
        "csrf_token": _get_or_create_csrf_token(),
        "location_switch_options": [],
        "location_switch_active_id": None,
    }

    if FORMULA_MODE:
        payload["location_switch_options"] = _get_accessible_restaurant_switch_options()
        active = get_active_restaurant()
        payload["location_switch_active_id"] = int(active["id"]) if active else None
    elif has_request_context() and current_user.is_authenticated:
        payload["location_switch_options"] = _get_accessible_restaurant_switch_options()
        payload["location_switch_active_id"] = int(current_user.restaurant_id) if current_user.restaurant_id else None

    return payload


@app.before_request
def before_request_security_and_timing():
    g.request_started_at = time.time()
    g.request_id = uuid.uuid4().hex[:12]

    if request.method == "POST" and not FORMULA_MODE:
        csrf_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not _is_csrf_valid(csrf_token):
            if request.path.startswith("/api/") or request.path in {"/upload", "/export"}:
                return _error_response("Invalid CSRF token", 400, "invalid_csrf")

            if request.path == "/auth/login":
                return render_template("login.html", error="Session expired. Please try again."), 400

            if request.path == "/auth/register":
                return render_template("register.html", error="Session expired. Please try again."), 400

            return _error_response("Session expired. Please retry your action.", 400, "invalid_csrf")

    return None


@app.after_request
def after_request_logging(response):
    request_id = getattr(g, "request_id", uuid.uuid4().hex[:12])
    response.headers["X-Request-ID"] = request_id

    started = getattr(g, "request_started_at", None)
    elapsed_ms = 0.0
    if started is not None:
        elapsed_ms = (time.time() - started) * 1000

    user_id = None
    if has_request_context() and current_user.is_authenticated:
        user_id = current_user.id

    app.logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f user_id=%s",
        request_id,
        request.method,
        request.path,
        response.status_code,
        elapsed_ms,
        user_id,
    )
    return response


class User(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.email = row["email"]
        self.full_name = row["full_name"] or ""
        self.restaurant_id = row["restaurant_id"]
        self.is_admin = bool(row["is_admin"])


def _is_admin_user():
    if FORMULA_MODE:
        return True
    return current_user.is_authenticated and bool(current_user.is_admin)


def _current_restaurant_id():
    if not current_user.is_authenticated:
        return None
    return current_user.restaurant_id


def _link_user_to_restaurant(conn, user_id, restaurant_id):
    conn.execute(
        """
        INSERT OR IGNORE INTO user_restaurants (user_id, restaurant_id)
        VALUES (?, ?)
        """,
        (int(user_id), int(restaurant_id)),
    )


def _has_access_to_restaurant_id(restaurant_id):
    if FORMULA_MODE:
        return True
    if not current_user.is_authenticated:
        return False
    if _is_admin_user():
        return True
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT 1
        FROM user_restaurants
        WHERE user_id = ? AND restaurant_id = ?
        LIMIT 1
        """,
        (int(current_user.id), int(restaurant_id)),
    ).fetchone()
    conn.close()
    return row is not None


def _get_accessible_restaurant_switch_options():
    if FORMULA_MODE:
        conn = get_db_connection()
        rows = conn.execute("SELECT id, name, location FROM restaurants ORDER BY id ASC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    if not has_request_context() or not current_user.is_authenticated:
        return []

    conn = get_db_connection()
    if _is_admin_user():
        rows = conn.execute("SELECT id, name, location FROM restaurants ORDER BY id ASC").fetchall()
    else:
        rows = conn.execute(
            """
            SELECT r.id, r.name, r.location
            FROM restaurants r
            JOIN user_restaurants ur ON ur.restaurant_id = r.id
            WHERE ur.user_id = ?
            ORDER BY r.id ASC
            """,
            (int(current_user.id),),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_accessible_restaurant_ids():
    if FORMULA_MODE:
        conn = get_db_connection()
        rows = conn.execute("SELECT id FROM restaurants ORDER BY id ASC").fetchall()
        conn.close()
        return [int(row["id"]) for row in rows]

    if not has_request_context() or not current_user.is_authenticated:
        return []

    conn = get_db_connection()
    if _is_admin_user():
        rows = conn.execute("SELECT id FROM restaurants ORDER BY id ASC").fetchall()
    else:
        rows = conn.execute(
            """
            SELECT restaurant_id AS id
            FROM user_restaurants
            WHERE user_id = ?
            ORDER BY restaurant_id ASC
            """,
            (int(current_user.id),),
        ).fetchall()
    conn.close()
    return [int(row["id"]) for row in rows]


def _restaurant_sync_group_key(restaurant_name):
    normalized = _clean_text(restaurant_name, 120).lower()
    if " - " in normalized:
        return normalized.split(" - ", 1)[0].strip()
    return normalized


def _get_sync_group_restaurants(base_restaurant=None):
    if not base_restaurant:
        return []

    base_id = int(base_restaurant["id"])
    base_key = _restaurant_sync_group_key(base_restaurant.get("name"))
    if not base_key:
        return [dict(base_restaurant)]

    if has_request_context() and current_user.is_authenticated:
        restaurant_ids = _get_accessible_restaurant_ids() or [base_id]
    else:
        restaurant_ids = [base_id]

    placeholders = ",".join("?" for _ in restaurant_ids)
    conn = get_db_connection()
    rows = conn.execute(
        f"""
        SELECT id, name, location, city, state
        FROM restaurants
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        restaurant_ids,
    ).fetchall()
    conn.close()

    matching_rows = [
        dict(row)
        for row in rows
        if _restaurant_sync_group_key(row["name"]) == base_key
    ]
    if matching_rows:
        return matching_rows
    return [dict(base_restaurant)]


def _get_sync_group_restaurant_ids(base_restaurant=None):
    return [int(row["id"]) for row in _get_sync_group_restaurants(base_restaurant)]


def _get_selected_sync_restaurant_ids(base_restaurant=None, selected_ids=None):
    if not base_restaurant:
        return []

    base_id = int(base_restaurant["id"])
    default_ids = _get_sync_group_restaurant_ids(base_restaurant) or [base_id]

    if has_request_context() and current_user.is_authenticated:
        allowed_ids = set(_get_accessible_restaurant_ids() or [base_id])
    else:
        allowed_ids = {base_id}

    normalized = []
    seen = set()
    for raw in selected_ids or []:
        text = str(raw or "").strip()
        if not text.isdigit():
            continue
        restaurant_id = int(text)
        if restaurant_id not in allowed_ids or restaurant_id in seen:
            continue
        normalized.append(restaurant_id)
        seen.add(restaurant_id)

    if not normalized:
        return default_ids

    if base_id not in seen:
        normalized.insert(0, base_id)
    return normalized


def _sync_business_reference_data(conn, base_restaurant=None):
    restaurant_ids = _get_sync_group_restaurant_ids(base_restaurant)
    if len(restaurant_ids) < 2:
        return

    placeholders = ",".join("?" for _ in restaurant_ids)
    master_rows = conn.execute(
        f"SELECT restaurant_id, item_name FROM master_items WHERE restaurant_id IN ({placeholders}) ORDER BY id ASC",
        restaurant_ids,
    ).fetchall()

    master_names = []
    seen_master_names = set()
    for row in master_rows:
        item_name = str(row["item_name"])
        if item_name in seen_master_names:
            continue
        seen_master_names.add(item_name)
        master_names.append(item_name)

    for restaurant_id in restaurant_ids:
        for item_name in master_names:
            _upsert_master_item(conn, restaurant_id, item_name)

    production_rows = conn.execute(
        f"""
        SELECT p.restaurant_id, p.item_name, p.count_mode, COALESCE(m.item_name, p.item_name) AS master_item_name
        FROM production_items p
        LEFT JOIN master_items m ON m.id = p.master_item_id
        WHERE p.restaurant_id IN ({placeholders})
        ORDER BY p.id ASC
        """,
        restaurant_ids,
    ).fetchall()

    production_defs = []
    seen_production_names = set()
    for row in production_rows:
        item_name = str(row["item_name"])
        if item_name in seen_production_names:
            continue
        seen_production_names.add(item_name)
        production_defs.append(
            {
                "item_name": item_name,
                "count_mode": str(row["count_mode"] or "unit"),
                "master_item_name": str(row["master_item_name"] or item_name),
            }
        )

    for restaurant_id in restaurant_ids:
        for definition in production_defs:
            master_item = _upsert_master_item(conn, restaurant_id, definition["master_item_name"])
            _upsert_production_item(
                conn,
                restaurant_id,
                definition["item_name"],
                master_item["id"] if master_item else None,
                definition["count_mode"],
            )


def get_user_by_id(user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, email, full_name, restaurant_id, is_admin FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return User(row)


def get_user_auth_row_by_email(email):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, email, password_hash, full_name, restaurant_id, is_admin FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    conn.close()
    return row


def create_user(email, password, full_name=""):
    password_hash = generate_password_hash(password)
    conn = get_db_connection()
    cur = conn.execute(
        """
        INSERT INTO users (email, password_hash, full_name)
        VALUES (?, ?, ?)
        """,
        (email, password_hash, full_name.strip()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


@login_manager.unauthorized_handler
def unauthorized_handler():
    if request.path.startswith("/api/") or request.path in {"/upload", "/export"}:
        return jsonify({"error": "Authentication required"}), 401
    return redirect(url_for("login", next=request.path))

# ─── Category Definitions ────────────────────────────────────────────────────
CATEGORIES = {
    "Chicken Wings": {
        "items": {
            "Side Kick Wings 5 Piece": 5,
            "6pc Wings w Fries": 6,
            "10pc Wings w Fries": 10,
            "16pc  Wings": 16,
            "SideKick of Wings": 5,
            "8 Wings & 8 O-Rings": 8,
            "10 Wings": 10,
            "15 Wings": 15,
            "20 Wings": 20,
        },
        "case_quantity": 250,
    },
    "Beef Cutlets": {
        "items": {
            "Steak Finger Basket": 1,
            "Chicken Fried Steak": 1,
        },
        "case_quantity": 28,
    },
    "Chicken Boneless": {
        "items": {
            "6pc Boneless": 6,
            "12pc Boneless": 12,
            "Chicken Strip Basket (4)": 4,
            "Grilled Chicken Tater": 4,
            "Crispy Chicken Tater": 4,
            "Boneless Wing Tater": 4,
            "Chicken & Mushroom": 4,
            "Grilled Chicken Salad": 4,
            "Crispy Chicken Salad": 4,
            "Chicken Tacos": 4,
            "3PC Chicken Strips w Fries": 3,
            "6 Boneless Wings & Fries": 6,
            "Crispy Chicken Baked Potato": 4,
            "Grilled Chicken SALAD": 4,
            "Kid's Boneless": 4,
            "Kids Chicken Strip (3)": 3,
        },
        "case_quantity": 40,
        "is_weight_based": True,
        "oz_per_piece": 1.3,
    },
    "Chicken Breast 6oz": {
        "items": {
            "Chicken Fried Chicken": 1,
            "Grilled Chicken Sandwich": 1,
            "Crispy Chicken Sandwich": 1,
            "Spicy Buffalo Chicken Sandwich": 1,
            "Deluxe Chicken Sandwich": 1,
            "Add Extra Chicken": 1,
        },
        "case_quantity": 53,
    },
    "Burger Patties": {
        "items": {
            "Big House Burger": 1,
            "Double Burger": 2,
            "Triple Burger": 3,
            "Bigun' (4)": 4,
            "Burger A La Mexicana": 2,
            "Chili Cheese Burger": 1,
            "Green Chili Burger": 1,
            "Fire Burger": 2,
            "Brunch Burger": 2,
            "Deluxe Burger": 1,
            "Single Burger w Fries": 1,
            "Burger A La Mexicana -- Single": 1,
            "Chili Cheese Burger -- Single": 1,
            "Green Chili Burger -- Single": 1,
            "Fire Burger -- Single": 1,
            "Brunch Burger -- Single": 1,
            "Patty Melt": 1,
            "Hamburger Patty Solo": 1,
            "Taco Salad": 2,
            "Beef Tacos": 1,
            "Cheddar Jala Hamburger Steak": 2,
            "Mushroom Swiss Hamburger Steak": 2,
            "Jalapeno Cheddar HBS Lunch": 1.5,
            "Kid's Burger": 0.5,
        },
        "case_quantity": 40,
        "is_weight_based": True,
        "oz_per_piece": 5.28,
    },
    "Ribeye Roll": {
        "items": {
            "Ribeye Tater": 1,
            "Ribeye Salad": 1,
            "Ribeye Sandwich": 1,
            "Side of RIbeye": 1,
        },
        "case_quantity": 70,
        "is_weight_based": True,
        "oz_per_piece": 8,
    },
    "Shrimp 41-50 (Small)": {
        "items": {
            "Grilled Shrimp Tater": 16,
            "Seafood Po'boy": 6,
            "Shrimp Tacos (4)": 16,
            "Buffalo Fried Shrimp Tater": 16,
            "Grilled Shrimp Salad": 16,
            "Extra Small Shrimp": 16,
            "Shrimp Po' Boy": 16,
        },
        "case_quantity": 460,
    },
    "Shrimp 16-20 (Large)": {
        "items": {
            "Fish (1) & Shrimp (5) Platter": 5,
            "Shrimp Platter (10)": 10,
            "Extra Jumbo Shrimp Each": 1,
            "(6)Fried Shrimp Platter Lunch": 6,
        },
        "case_quantity": 180,
    },
    "Catfish": {
        "items": {
            "Catfish Platter (2)": 2,
            "Fish (1) & Shrimp (5) Platter": 1,
            "Fish Sandwich": 1,
            "Seafood Po'boy": 1,
            "Fish Tacos (4)": 1,
        },
        "case_quantity": 48,
    },
    "Philly Beef": {
        "items": {
            "Philly Cheese Tater": 2,
            "BBQ Philly Steak Tater": 2,
            "Texas Philly Sandwich": 2,
            "Deluxe Philly Sandwich": 2,
        },
        "case_quantity": 40,
    },
    "40ct Baked Potatoes": {
        "items": {
            "Cheddar Bacon Wedges": 1,
            "Classic Baked Tater": 1,
            "Grilled Chicken Tater": 1,
            "Crispy Chicken Tater": 1,
            "Buffalo Fried Shrimp Tater": 1,
            "Grilled Shrimp Tater": 1,
            "Veggie Delight Tater": 1,
            "BBQ Philly Steak Tater": 1,
            "Chicken & Mushroom Tater": 1,
            "Deluxe Baked Tater": 1,
            "Crispy Chicken Baked Potato": 1,
        },
        "case_quantity": 40,
    },
    "Hot Dogs": {
        "items": {
            "Hot Dog Kids w/ fries": 1,
            "Single Hot Dog Meal": 1,
            "Double Hot Dog Meal": 1,
        },
        "case_quantity": 50,
    },
}


PRODUCTION_ITEM_TEMPLATE = [
    "Burger Patty",
    "Boneless Strips",
    "Chicken Strips",
    "Fish Tacos",
    "Fish Fillet",
    "CFS",
    "CFC",
    "GrilledChickenBreast",
    "Grilled Chicken Strips",
    "Bone in Wings",
    "Boneless Wings",
    "Crispy Chicken Nuggets",
    "Baby Shrimp Orders",
    "Large Shrimp",
    "Fries",
    "Tots",
    "Onion Ring Side",
    "SWT Potato Fries",
    "Steak Strips",
    "Phili Beef",
    "Ribeye Strips",
    "Corn Dogs",
    "Hot Dogs",
]


def _create_indexes(cursor):
    """Create single-column performance indexes."""
    indexes = [
        ("idx_product_categories_restaurant_id", "product_categories", "restaurant_id"),
        ("idx_product_mix_uploads_restaurant_id", "product_mix_uploads", "restaurant_id"),
        ("idx_product_mix_items_upload_id", "product_mix_items", "upload_id"),
        ("idx_product_mix_items_restaurant_id", "product_mix_items", "restaurant_id"),
        ("idx_product_categories_name", "product_categories", "name"),
        ("idx_product_mix_items_category_name", "product_mix_items", "category_name"),
        ("idx_product_mix_items_item_name", "product_mix_items", "item_name"),
        ("idx_product_mix_uploads_start_date", "product_mix_uploads", "report_start_date"),
        ("idx_product_mix_uploads_end_date", "product_mix_uploads", "report_end_date"),
        ("idx_product_mix_items_start_date", "product_mix_items", "report_start_date"),
        ("idx_product_mix_items_end_date", "product_mix_items", "report_end_date"),
        ("idx_product_mix_source_items_upload_id", "product_mix_source_items", "upload_id"),
        ("idx_product_mix_source_items_restaurant_id", "product_mix_source_items", "restaurant_id"),
        ("idx_product_mix_source_items_name", "product_mix_source_items", "source_item_name"),
        ("idx_product_mix_source_items_start_date", "product_mix_source_items", "report_start_date"),
        ("idx_product_mix_source_items_end_date", "product_mix_source_items", "report_end_date"),
        ("idx_product_item_category_overrides_restaurant", "product_item_category_overrides", "restaurant_id"),
        ("idx_product_item_category_overrides_item", "product_item_category_overrides", "item_name"),
        ("idx_product_item_production_mappings_restaurant", "product_item_production_mappings", "restaurant_id"),
        ("idx_product_item_production_mappings_source", "product_item_production_mappings", "source_item_name"),
        ("idx_production_items_restaurant", "production_items", "restaurant_id"),
        ("idx_production_items_name", "production_items", "item_name"),
    ]
    for idx_name, table, column in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
        except Exception:
            pass


def _create_composite_indexes(cursor):
    """Create composite indexes for multi-column queries."""
    composites = [
        ("idx_pmu_restaurant_date", "product_mix_uploads", "restaurant_id, report_start_date"),
        ("idx_pmi_restaurant_category", "product_mix_items", "restaurant_id, category_name"),
        ("idx_pmsi_restaurant_name", "product_mix_source_items", "restaurant_id, source_item_name"),
        ("idx_pmsi_restaurant_date", "product_mix_source_items", "restaurant_id, report_start_date"),
        ("idx_pipm_restaurant_source", "product_item_production_mappings", "restaurant_id, source_item_name"),
        ("idx_pi_restaurant_name", "production_items", "restaurant_id, item_name"),
    ]
    for idx_name, table, columns in composites:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
        except Exception:
            pass


def _ensure_same_day_uploads_allowed(cursor):
    """Migrate legacy schemas that enforced one upload per day."""
    target_cols = ["restaurant_id", "report_start_date", "report_end_date"]

    table_sql_row = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'product_mix_uploads'"
    ).fetchone()
    table_sql = (table_sql_row[0] or "") if table_sql_row else ""
    normalized_sql = re.sub(r"\s+", "", table_sql.lower())

    has_legacy_unique_constraint = "unique(restaurant_id,report_start_date,report_end_date)" in normalized_sql
    if has_legacy_unique_constraint:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_mix_uploads_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                report_start_date TEXT,
                report_end_date TEXT,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO product_mix_uploads_new (id, restaurant_id, filename, report_start_date, report_end_date, uploaded_at)
            SELECT id, restaurant_id, filename, report_start_date, report_end_date, uploaded_at
            FROM product_mix_uploads
            """
        )
        cursor.execute("DROP TABLE product_mix_uploads")
        cursor.execute("ALTER TABLE product_mix_uploads_new RENAME TO product_mix_uploads")
        cursor.execute("PRAGMA foreign_keys=ON")

    index_rows = cursor.execute("PRAGMA index_list('product_mix_uploads')").fetchall()
    for row in index_rows:
        index_name = row[1]
        is_unique = bool(row[2])
        origin = row[3] if len(row) > 3 else ""

        if not is_unique or origin != "c":
            continue

        index_info = cursor.execute(f"PRAGMA index_info('{index_name}')").fetchall()
        columns = [info[2] for info in sorted(index_info, key=lambda x: x[0])]
        if columns == target_cols:
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            restaurant_id INTEGER,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_restaurants (
            user_id INTEGER NOT NULL,
            restaurant_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, restaurant_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_mix_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            report_start_date TEXT,
            report_end_date TEXT,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            case_quantity REAL NOT NULL DEFAULT 0,
            is_weight_based INTEGER NOT NULL DEFAULT 0,
            oz_per_piece REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(restaurant_id, name),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_mix_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            restaurant_id INTEGER NOT NULL,
            category_name TEXT NOT NULL,
            item_name TEXT NOT NULL,
            qty_sold REAL NOT NULL DEFAULT 0,
            multiplier REAL NOT NULL DEFAULT 1,
            total REAL NOT NULL DEFAULT 0,
            is_weight_based INTEGER NOT NULL DEFAULT 0,
            report_start_date TEXT,
            report_end_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (upload_id) REFERENCES product_mix_uploads(id),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS production_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            master_item_id INTEGER,
            count_mode TEXT NOT NULL DEFAULT 'unit',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(restaurant_id, item_name),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
            FOREIGN KEY (master_item_id) REFERENCES master_items(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS master_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(restaurant_id, item_name),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    production_item_cols = [r[1] for r in cursor.execute("PRAGMA table_info(production_items)").fetchall()]
    if "master_item_id" not in production_item_cols:
        cursor.execute("ALTER TABLE production_items ADD COLUMN master_item_id INTEGER")
    if "count_mode" not in production_item_cols:
        cursor.execute("ALTER TABLE production_items ADD COLUMN count_mode TEXT NOT NULL DEFAULT 'unit'")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_item_category_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            category_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(restaurant_id, item_name),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_item_production_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            source_item_name TEXT NOT NULL,
            production_category_name TEXT,
            production_item_name TEXT NOT NULL,
            units_per_order REAL NOT NULL DEFAULT 1,
            item_dollars_per_order REAL NOT NULL DEFAULT 0,
            void_dollars_per_order REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS location_edit_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            edited_by_user_id INTEGER NOT NULL,
            request_id TEXT,
            changes_json TEXT NOT NULL,
            edited_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
            FOREIGN KEY (edited_by_user_id) REFERENCES users(id)
        )
        """
    )

    # All Levels per-item tables
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS all_levels_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(restaurant_id, item_name),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS all_levels_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            upload_id INTEGER NOT NULL,
            restaurant_id INTEGER NOT NULL,
            report_start_date TEXT,
            report_end_date TEXT,
            col_b REAL,
            col_c REAL,
            col_i REAL,
            col_j REAL,
            col_l REAL,
            col_n REAL,
            col_o REAL,
            col_p REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(item_id, upload_id),
            FOREIGN KEY (item_id) REFERENCES all_levels_items(id),
            FOREIGN KEY (upload_id) REFERENCES product_mix_uploads(id),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS all_levels_column_headers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            col_letter TEXT NOT NULL,
            header_name TEXT NOT NULL,
            UNIQUE(restaurant_id, col_letter),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )
        """
    )

    _ensure_same_day_uploads_allowed(cursor)

    # Backfill legacy user.restaurant_id to the user_restaurants mapping table.
    cursor.execute(
        """
        INSERT OR IGNORE INTO user_restaurants (user_id, restaurant_id)
        SELECT id, restaurant_id
        FROM users
        WHERE restaurant_id IS NOT NULL
        """
    )

    _create_indexes(cursor)
    _create_composite_indexes(cursor)

    conn.commit()
    conn.close()


def set_active_restaurant(restaurant_id):
    if (not FORMULA_MODE) and has_request_context() and current_user.is_authenticated:
        if not _has_access_to_restaurant_id(restaurant_id):
            raise PermissionError("User cannot access this restaurant")

        conn = get_db_connection()
        conn.execute("UPDATE users SET restaurant_id = ? WHERE id = ?", (restaurant_id, int(current_user.id)))
        conn.commit()
        conn.close()
        current_user.restaurant_id = restaurant_id
        return

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('active_restaurant_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(restaurant_id),),
    )
    conn.commit()
    conn.close()


def get_active_restaurant():
    if (not FORMULA_MODE) and has_request_context() and current_user.is_authenticated:
        if not current_user.restaurant_id:
            return None
        if not _has_access_to_restaurant_id(current_user.restaurant_id):
            return None
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM restaurants WHERE id = ?", (current_user.restaurant_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    conn = get_db_connection()
    setting = conn.execute("SELECT value FROM app_settings WHERE key = 'active_restaurant_id'").fetchone()

    active = None
    if setting:
        value = str(setting["value"])
        if value.isdigit():
            row = conn.execute("SELECT * FROM restaurants WHERE id = ?", (int(value),)).fetchone()
            if row:
                active = dict(row)

    if not active:
        fallback = conn.execute("SELECT * FROM restaurants ORDER BY id ASC LIMIT 1").fetchone()
        if fallback:
            active = dict(fallback)

    conn.close()
    return active


def parse_dates_from_filename(filename):
    stem = Path(filename).stem
    found_dates = []
    seen = set()

    def _append_if_valid(start_idx, raw_date, formats):
        for fmt in formats:
            try:
                parsed = datetime.strptime(raw_date, fmt).date().isoformat()
                if parsed not in seen:
                    found_dates.append((start_idx, parsed))
                    seen.add(parsed)
                return
            except ValueError:
                continue

    for match in re.finditer(r"(?<!\d)(\d{4})[-_\.](\d{2})[-_\.](\d{2})(?!\d)", stem):
        raw = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        _append_if_valid(match.start(), raw, ["%Y-%m-%d"])

    for match in re.finditer(r"(?<!\d)(\d{2})[-_\.](\d{2})[-_\.](\d{4})(?!\d)", stem):
        raw = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        _append_if_valid(match.start(), raw, ["%m-%d-%Y"])

    for match in re.finditer(r"(?<!\d)(\d{8})(?!\d)", stem):
        raw = match.group(1)
        _append_if_valid(match.start(), raw, ["%Y%m%d", "%m%d%Y"])

    if not found_dates:
        return None, None

    found_dates.sort(key=lambda x: x[0])
    dates = [d for _, d in found_dates]
    if len(dates) == 1:
        return dates[0], dates[0]
    return dates[0], dates[1]


def _find_existing_upload_for_restaurant_day(conn, restaurant_id, day_iso):
    if not day_iso:
        return None

    return conn.execute(
        """
        SELECT id, filename, report_start_date, report_end_date, uploaded_at
        FROM product_mix_uploads
        WHERE restaurant_id = ?
          AND (
                COALESCE(report_start_date, report_end_date, '') = ?
             OR COALESCE(report_end_date, report_start_date, '') = ?
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(restaurant_id), str(day_iso), str(day_iso)),
    ).fetchone()


def _process_uploaded_product_mix_file(file_storage, restaurant):
    if file_storage.mimetype not in ALLOWED_UPLOAD_MIME_TYPES:
        return None, {"error": f"{file_storage.filename}: Invalid file type"}, 400

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None, {"error": "Filename is invalid"}, 400

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        return None, {"error": f"{filename}: Only .xlsx / .xls files are allowed"}, 400

    try:
        df = read_product_mix_excel(file_storage)
    except Exception as e:
        return None, {"error": f"Could not read Excel file '{filename}': {str(e)}"}, 400

    start_date, end_date = parse_dates_from_filename(filename)

    try:
        source_item_col, source_qty_col = resolve_item_qty_columns(df)
        source_totals = {}
        for idx, raw_item in enumerate(source_item_col):
            item_name = str(raw_item).strip() if pd.notna(raw_item) else ""
            if not item_name or item_name.lower() in {"nan", "none"}:
                continue
            qty_sold = _safe_float(source_qty_col.iloc[idx])
            source_totals[item_name] = source_totals.get(item_name, 0.0) + qty_sold
    except Exception:
        source_totals = {}

    try:
        all_results = {}
        for cat_name, cat_data in CATEGORIES.items():
            all_results[cat_name] = process_category(df, cat_name, cat_data)

        conn = get_db_connection()
        cur = conn.execute(
            """
            INSERT INTO product_mix_uploads (restaurant_id, filename, report_start_date, report_end_date)
            VALUES (?, ?, ?, ?)
            """,
            (restaurant["id"], filename, start_date, end_date),
        )
        upload_id = cur.lastrowid

        for cat_name, cat_payload in all_results.items():
            is_weight_based = 1 if cat_payload["summary"].get("type") == "weight" else 0
            for row in cat_payload.get("all_items", []):
                conn.execute(
                    """
                    INSERT INTO product_mix_items
                    (upload_id, restaurant_id, category_name, item_name, qty_sold, multiplier, total, is_weight_based, report_start_date, report_end_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        upload_id,
                        restaurant["id"],
                        cat_name,
                        row["item_name"],
                        float(row["qty_sold"]),
                        float(row["multiplier"]),
                        float(row["total"]),
                        is_weight_based,
                        start_date,
                        end_date,
                    ),
                )

        for source_item_name, qty_sold in source_totals.items():
            conn.execute(
                """
                INSERT INTO product_mix_source_items
                (upload_id, restaurant_id, source_item_name, qty_sold, report_start_date, report_end_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    restaurant["id"],
                    source_item_name,
                    float(qty_sold),
                    start_date,
                    end_date,
                ),
            )

        conn.commit()
        conn.close()
    except Exception as e:
        return None, {"error": f"Failed while processing '{filename}': {str(e)}"}, 500

    return {
        "data": all_results,
        "upload": {
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "filename": filename,
            "report_start_date": start_date,
            "report_end_date": end_date,
        },
    }, None, None


def _switch_active_restaurant_or_error(restaurant_id):
    conn = get_db_connection()
    exists = conn.execute("SELECT id FROM restaurants WHERE id = ?", (restaurant_id,)).fetchone()
    conn.close()
    if not exists:
        return "Restaurant+not+found"

    if not _has_access_to_restaurant_id(restaurant_id):
        return "You+cannot+switch+to+that+location"

    try:
        set_active_restaurant(restaurant_id)
    except PermissionError:
        return "You+cannot+switch+to+that+location"

    return None


def _get_next_restaurant_id(current_restaurant_id):
    options = _get_accessible_restaurant_switch_options()
    if not options:
        return None

    option_ids = [int(option["id"]) for option in options]
    if current_restaurant_id in option_ids:
        current_index = option_ids.index(int(current_restaurant_id))
        return option_ids[(current_index + 1) % len(option_ids)]
    return option_ids[0]


def _normalize_report_date_filter(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _format_numeric_for_response(value):
    numeric = float(value or 0)
    if numeric == int(numeric):
        return int(numeric)
    return round(numeric, 2)


def _parse_limited_positive_int(raw_value, default_value, min_value=1, max_value=1000):
    raw = (raw_value or "").strip()
    if not raw.isdigit():
        return default_value
    return max(min_value, min(int(raw), max_value))


def _build_configured_product_catalog():
    catalog = {}
    for category_name, category_data in CATEGORIES.items():
        for item_name, multiplier in category_data.get("items", {}).items():
            catalog[(category_name, item_name)] = {
                "category_name": category_name,
                "item_name": item_name,
                "configured_multiplier": float(multiplier),
                "is_configured": True,
            }
    return catalog


def _build_template_item_metadata_lookup():
    lookup = {}
    for category_name, category_data in CATEGORIES.items():
        for item_name, multiplier in category_data.get("items", {}).items():
            lookup[item_name] = {
                "category_name": category_name,
                "configured_multiplier": float(multiplier),
                "is_configured": True,
            }
    return lookup


def _get_item_category_overrides(conn, restaurant_id):
    rows = conn.execute(
        """
        SELECT item_name, category_name
        FROM product_item_category_overrides
        WHERE restaurant_id = ?
        """,
        (int(restaurant_id),),
    ).fetchall()
    return {row["item_name"]: row["category_name"] for row in rows}


def _get_product_mix_item_order_lookup(conn, restaurant_ids):
    if not restaurant_ids:
        return {}

    placeholders = ",".join("?" for _ in restaurant_ids)
    rows = conn.execute(
        f"""
        SELECT item_name, MIN(id) AS first_seen_id
        FROM all_levels_items
        WHERE restaurant_id IN ({placeholders})
        GROUP BY item_name
        ORDER BY MIN(id) ASC
        """,
        restaurant_ids,
    ).fetchall()
    return {str(row["item_name"]): int(row["first_seen_id"]) for row in rows if row["item_name"] is not None}


def _get_master_items(conn, restaurant_id):
    restaurant_row = conn.execute(
        "SELECT id, name, location, city, state FROM restaurants WHERE id = ? LIMIT 1",
        (int(restaurant_id),),
    ).fetchone()
    sync_group_ids = _get_sync_group_restaurant_ids(dict(restaurant_row)) if restaurant_row else [int(restaurant_id)]
    order_lookup = _get_product_mix_item_order_lookup(conn, sync_group_ids)

    rows = conn.execute(
        """
        SELECT id, item_name
        FROM master_items
        WHERE restaurant_id = ?
        ORDER BY id ASC
        """,
        (int(restaurant_id),),
    ).fetchall()
    items = [{"id": int(row["id"]), "item_name": str(row["item_name"])} for row in rows]
    items.sort(
        key=lambda row: (
            int(order_lookup.get(row["item_name"], 10 ** 9)),
            str(row["item_name"]).lower(),
        )
    )
    return items


def _upsert_master_item(conn, restaurant_id, item_name):
    cleaned_name = _clean_text(item_name, 180)
    if not cleaned_name:
        return None

    conn.execute(
        """
        INSERT INTO master_items (restaurant_id, item_name)
        VALUES (?, ?)
        ON CONFLICT(restaurant_id, item_name) DO NOTHING
        """,
        (int(restaurant_id), cleaned_name),
    )
    row = conn.execute(
        """
        SELECT id, item_name
        FROM master_items
        WHERE restaurant_id = ? AND item_name = ?
        LIMIT 1
        """,
        (int(restaurant_id), cleaned_name),
    ).fetchone()
    if not row:
        return None
    return {"id": int(row["id"]), "item_name": str(row["item_name"])}


def _get_production_items(conn, restaurant_id):
    restaurant_row = conn.execute(
        "SELECT id, name, location, city, state FROM restaurants WHERE id = ? LIMIT 1",
        (int(restaurant_id),),
    ).fetchone()
    sync_group_ids = _get_sync_group_restaurant_ids(dict(restaurant_row)) if restaurant_row else [int(restaurant_id)]
    order_lookup = _get_product_mix_item_order_lookup(conn, sync_group_ids)
    mapping_rows = conn.execute(
        """
        SELECT production_item_name, source_item_name
        FROM product_item_production_mappings
        WHERE restaurant_id = ?
        ORDER BY id ASC
        """,
        (int(restaurant_id),),
    ).fetchall()
    production_order_lookup = {}
    for mapping_row in mapping_rows:
        production_item_name = str(mapping_row["production_item_name"] or "")
        source_item_name = str(mapping_row["source_item_name"] or "")
        if not production_item_name or source_item_name not in order_lookup:
            continue
        current_value = production_order_lookup.get(production_item_name)
        candidate_value = int(order_lookup[source_item_name])
        if current_value is None or candidate_value < current_value:
            production_order_lookup[production_item_name] = candidate_value

    rows = conn.execute(
        """
        SELECT p.id, p.item_name, p.master_item_id, p.count_mode, m.item_name AS master_item_name
        FROM production_items p
        LEFT JOIN master_items m ON m.id = p.master_item_id
        WHERE p.restaurant_id = ?
        ORDER BY p.id ASC
        """,
        (int(restaurant_id),),
    ).fetchall()
    items = [
        {
            "id": int(row["id"]),
            "item_name": str(row["item_name"]),
            "master_item_id": int(row["master_item_id"]) if row["master_item_id"] is not None else None,
            "master_item_name": str(row["master_item_name"] or ""),
            "count_mode": str(row["count_mode"] or "unit"),
        }
        for row in rows
    ]
    items.sort(
        key=lambda row: (
            int(production_order_lookup.get(row["item_name"], order_lookup.get(row["item_name"], 10 ** 9))),
            str(row["item_name"]).lower(),
        )
    )
    return items


def _upsert_production_item(conn, restaurant_id, item_name, master_item_id=None, count_mode="unit"):
    cleaned_name = _clean_text(item_name, 180)
    if not cleaned_name:
        return None

    normalized_count_mode = "weight" if str(count_mode or "").strip().lower() == "weight" else "unit"

    normalized_master_item_id = None
    if master_item_id is not None:
        try:
            normalized_master_item_id = int(master_item_id)
        except (TypeError, ValueError):
            normalized_master_item_id = None

    conn.execute(
        """
        INSERT INTO production_items (restaurant_id, item_name, master_item_id, count_mode)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(restaurant_id, item_name)
        DO UPDATE SET
            master_item_id = COALESCE(production_items.master_item_id, excluded.master_item_id),
            count_mode = COALESCE(production_items.count_mode, excluded.count_mode)
        """,
        (int(restaurant_id), cleaned_name, normalized_master_item_id, normalized_count_mode),
    )
    row = conn.execute(
        """
        SELECT p.id, p.item_name, p.master_item_id, p.count_mode, m.item_name AS master_item_name
        FROM production_items p
        LEFT JOIN master_items m ON m.id = p.master_item_id
        WHERE p.restaurant_id = ? AND p.item_name = ?
        LIMIT 1
        """,
        (int(restaurant_id), cleaned_name),
    ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "item_name": str(row["item_name"]),
        "master_item_id": int(row["master_item_id"]) if row["master_item_id"] is not None else None,
        "master_item_name": str(row["master_item_name"] or ""),
        "count_mode": str(row["count_mode"] or "unit"),
    }


def _get_item_production_mappings(conn, restaurant_id):
    rows = conn.execute(
        """
        SELECT id, source_item_name, production_category_name, production_item_name,
               units_per_order, item_dollars_per_order, void_dollars_per_order
        FROM product_item_production_mappings
        WHERE restaurant_id = ?
        ORDER BY id ASC
        """,
        (int(restaurant_id),),
    ).fetchall()
    result = {}
    for row in rows:
        source_key = _normalize_item_key(row["source_item_name"])
        result.setdefault(source_key, []).append(dict(row))
    return result


def _get_item_production_mappings_for_restaurants(conn, restaurant_ids):
    ids = [int(v) for v in (restaurant_ids or []) if str(v).isdigit()]
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT id, source_item_name, production_category_name, production_item_name,
               units_per_order, item_dollars_per_order, void_dollars_per_order
        FROM product_item_production_mappings
        WHERE restaurant_id IN ({placeholders})
        ORDER BY id ASC
        """,
        ids,
    ).fetchall()
    result = {}
    for row in rows:
        source_key = _normalize_item_key(row["source_item_name"])
        result.setdefault(source_key, []).append(dict(row))
    return result


def _get_production_mapping_rows(conn, restaurant_id):
    restaurant_row = conn.execute(
        "SELECT id, name, location, city, state FROM restaurants WHERE id = ? LIMIT 1",
        (int(restaurant_id),),
    ).fetchone()
    sync_group_ids = _get_sync_group_restaurant_ids(dict(restaurant_row)) if restaurant_row else [int(restaurant_id)]
    source_order_lookup = _get_product_mix_item_order_lookup(conn, sync_group_ids)
    production_lookup = {
        row["item_name"]: row
        for row in _get_production_items(conn, restaurant_id)
    }
    mapping_lookup = _get_item_production_mappings(conn, restaurant_id)
    rows = []
    for _source_key, mappings in mapping_lookup.items():
        for mapping in mappings:
            production = production_lookup.get(mapping["production_item_name"], {})
            rows.append(
                {
                    "id": int(mapping["id"]),
                    "source_item_name": str(mapping.get("source_item_name") or ""),
                    "production_item_name": mapping["production_item_name"],
                    "master_item_name": production.get("master_item_name") or mapping["production_item_name"],
                    "count_mode": production.get("count_mode") or "unit",
                    "units_per_order": _format_numeric_for_response(mapping["units_per_order"]),
                }
            )

    rows.sort(
        key=lambda row: (
            int(source_order_lookup.get(row["source_item_name"], source_order_lookup.get(_normalize_item_key(row["source_item_name"]), 10 ** 9))),
            str(row["production_item_name"]).lower(),
            int(row["id"]),
        )
    )
    return rows


def _resolve_report_restaurant(location_id_raw, fallback_restaurant=None):
    active_restaurant = fallback_restaurant or get_active_restaurant()
    raw = (location_id_raw or "").strip()

    if not raw:
        return active_restaurant
    if not raw.isdigit():
        return active_restaurant

    restaurant_id = int(raw)
    if not _has_access_to_restaurant_id(restaurant_id):
        return active_restaurant

    conn = get_db_connection()
    row = conn.execute("SELECT * FROM restaurants WHERE id = ?", (restaurant_id,)).fetchone()
    conn.close()
    return dict(row) if row else active_restaurant


def _get_uncategorized_source_items(restaurant=None, start_date=None, end_date=None, search_text="", limit=100):
    rows = _get_source_item_history_rows(restaurant=restaurant, limit=5000)
    filtered = [row for row in rows if not row.get("mapped_to")]

    normalized_start = _normalize_report_date_filter(start_date) if start_date else None
    normalized_end = _normalize_report_date_filter(end_date) if end_date else None
    normalized_search = _clean_text(search_text, 120).lower()

    if normalized_start:
        filtered = [
            row
            for row in filtered
            if not row.get("last_report_end") or str(row.get("last_report_end")) >= normalized_start
        ]

    if normalized_end:
        filtered = [
            row
            for row in filtered
            if not row.get("first_report_start") or str(row.get("first_report_start")) <= normalized_end
        ]

    if normalized_search:
        filtered = [
            row
            for row in filtered
            if normalized_search in str(row.get("item_name", "")).lower()
        ]

    return filtered[: int(limit)]


def _get_source_item_history_rows(restaurant=None, limit=500, restaurant_ids=None):
    if not restaurant:
        return []

    source_restaurant_ids = [
        int(v)
        for v in (restaurant_ids or [])
        if str(v).isdigit()
    ]
    if not source_restaurant_ids:
        source_restaurant_ids = _get_sync_group_restaurant_ids(restaurant) or [int(restaurant["id"])]

    placeholders = ",".join("?" for _ in source_restaurant_ids)
    conn = get_db_connection()
    mapping_lookup = _get_item_production_mappings_for_restaurants(conn, source_restaurant_ids)
    rows = conn.execute(
        f"""
        SELECT i.item_name,
             MIN(i.id) AS first_seen_item_id,
               COUNT(DISTINCT i.restaurant_id) AS location_count,
               COUNT(DISTINCT r.upload_id) AS upload_count,
               MIN(r.report_start_date) AS first_report_start,
               MAX(r.report_end_date) AS last_report_end,
               MAX(u.uploaded_at) AS latest_uploaded_at,
               COALESCE(SUM(r.col_i), 0) AS total_qty_sold
        FROM all_levels_items i
        LEFT JOIN all_levels_records r ON r.item_id = i.id
        LEFT JOIN product_mix_uploads u ON u.id = r.upload_id
        WHERE i.restaurant_id IN ({placeholders})
        GROUP BY i.item_name
        ORDER BY MIN(i.id) ASC, LOWER(i.item_name) ASC
        LIMIT ?
        """,
        (*source_restaurant_ids, int(limit)),
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        mappings = mapping_lookup.get(_normalize_item_key(row["item_name"]), [])
        mapped_to = ", ".join(
            sorted(
                {
                    str(mapping.get("production_item_name") or "").strip()
                    for mapping in mappings
                    if str(mapping.get("production_item_name") or "").strip()
                }
            )
        )
        total_qty_sold = float(row["total_qty_sold"] or 0)
        result.append(
            {
                "item_name": str(row["item_name"] or ""),
                "first_seen_item_id": int(row["first_seen_item_id"] or 0),
                "location_count": int(row["location_count"] or 0),
                "upload_count": int(row["upload_count"] or 0),
                "first_report_start": row["first_report_start"],
                "last_report_end": row["last_report_end"],
                "latest_uploaded_at": row["latest_uploaded_at"],
                "total_qty_sold": _format_numeric_for_response(total_qty_sold),
                "mapped_to": mapped_to,
                "is_mapped": bool(mapped_to),
            }
        )
    return result


def _extract_mapping_entries_from_form(form):
    selected_names = form.getlist("production_item_name")
    quick_add_names = form.getlist("new_production_item_name")
    quantity_values = form.getlist("units_per_order")
    item_dollars_values = form.getlist("item_dollars_per_order")
    void_dollars_values = form.getlist("void_dollars_per_order")

    max_len = max(
        len(selected_names),
        len(quick_add_names),
        len(quantity_values),
        len(item_dollars_values),
        len(void_dollars_values),
        1,
    )

    entries = []
    for index in range(max_len):
        selected_name = _clean_text(selected_names[index] if index < len(selected_names) else "", 180)
        quick_add_name = _clean_text(quick_add_names[index] if index < len(quick_add_names) else "", 180)
        target_name = quick_add_name or selected_name

        quantity_raw = str(quantity_values[index] if index < len(quantity_values) else "1").strip()
        item_dollars_raw = str(item_dollars_values[index] if index < len(item_dollars_values) else "0").strip()
        void_dollars_raw = str(void_dollars_values[index] if index < len(void_dollars_values) else "0").strip()

        if not target_name and not quantity_raw and not item_dollars_raw and not void_dollars_raw:
            continue
        if not target_name:
            return None, "Each mapping row needs a production item or quick add name"

        try:
            units_per_order = float(quantity_raw or "1")
            item_dollars_per_order = float(item_dollars_raw or "0")
            void_dollars_per_order = float(void_dollars_raw or "0")
        except ValueError:
            return None, "Units and dollar fields must be numeric"

        if units_per_order <= 0:
            return None, "Each quantity must be greater than 0"

        entries.append(
            {
                "production_item_name": target_name,
                "is_new": bool(quick_add_name),
                "units_per_order": units_per_order,
                "item_dollars_per_order": item_dollars_per_order,
                "void_dollars_per_order": void_dollars_per_order,
            }
        )

    if not entries:
        return None, "Add at least one production item mapping"

    return entries, None


def _build_restaurant_product_catalog(conn, restaurant_id):
    fallback = list(_build_configured_product_catalog().values())
    for idx, entry in enumerate(fallback, start=1):
        entry["order_index"] = idx
    return fallback


def _get_product_purchase_log(restaurant=None, start_date=None, end_date=None, search_text="", include_zero_rows=True):
    if not restaurant:
        return [], {"total_qty_sold": 0, "total_units": 0, "item_dollars": 0, "void_dollars": 0, "products": 0}

    conn = get_db_connection()
    where_clauses = ["restaurant_id = ?"]
    params = [restaurant["id"]]

    if start_date:
        where_clauses.append("COALESCE(report_end_date, report_start_date, '') >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("COALESCE(report_start_date, report_end_date, '') <= ?")
        params.append(end_date)

    cleaned_search = _clean_text(search_text, 120)
    if cleaned_search:
        like_value = f"%{cleaned_search}%"
        where_clauses.append("(category_name LIKE ? OR item_name LIKE ?)")
        params.extend([like_value, like_value])

    where_sql = " AND ".join(where_clauses)
    template_rows = conn.execute(
        f"""
        SELECT category_name, item_name,
               SUM(qty_sold) AS total_qty_sold,
               SUM(total) AS total_units,
               COUNT(DISTINCT upload_id) AS upload_count,
               MIN(report_start_date) AS first_report_start,
               MAX(report_end_date) AS last_report_end
        FROM product_mix_items
        WHERE {where_sql}
        GROUP BY category_name, item_name
        ORDER BY category_name ASC, item_name ASC
        """,
        params,
    ).fetchall()

    product_catalog = _build_restaurant_product_catalog(conn, restaurant["id"]) if include_zero_rows else []
    conn.close()

    aggregated = {}
    for row in template_rows:
        key = (row["category_name"], row["item_name"])
        aggregated[key] = {
            "category_name": row["category_name"],
            "item_name": row["item_name"],
            "total_qty_sold": _format_numeric_for_response(row["total_qty_sold"]),
            "total_units": _format_numeric_for_response(row["total_units"]),
            "item_dollars": 0,
            "void_dollars": 0,
            "upload_count": int(row["upload_count"] or 0),
            "first_report_start": row["first_report_start"],
            "last_report_end": row["last_report_end"],
            "configured_multiplier": None,
            "is_configured": False,
        }

    product_rows = []
    if include_zero_rows:
        for product in product_catalog:
            key = (product["category_name"], product["item_name"])
            if key in aggregated:
                entry = aggregated.pop(key)
                if product["configured_multiplier"] is not None:
                    entry["configured_multiplier"] = _format_numeric_for_response(product["configured_multiplier"])
                entry["is_configured"] = bool(product["is_configured"])
                entry["order_index"] = int(product.get("order_index") or 0)
                product_rows.append(entry)
            else:
                product_rows.append(
                    {
                        "category_name": product["category_name"],
                        "item_name": product["item_name"],
                        "total_qty_sold": 0,
                        "total_units": 0,
                        "item_dollars": 0,
                        "void_dollars": 0,
                        "upload_count": 0,
                        "first_report_start": None,
                        "last_report_end": None,
                        "configured_multiplier": _format_numeric_for_response(product["configured_multiplier"]) if product["configured_multiplier"] is not None else None,
                        "is_configured": bool(product["is_configured"]),
                        "order_index": int(product.get("order_index") or 0),
                    }
                )

    for extra_row in aggregated.values():
        extra_row["order_index"] = 10 ** 9
        product_rows.append(extra_row)

    if cleaned_search:
        search_lower = cleaned_search.lower()
        product_rows = [
            row
            for row in product_rows
            if search_lower in str(row["category_name"]).lower() or search_lower in str(row["item_name"]).lower()
        ]

    product_rows.sort(
        key=lambda row: (
            int(row.get("order_index") or 10 ** 9),
            str(row["item_name"]).lower(),
            str(row["category_name"]).lower(),
        )
    )

    summary = {
        "total_qty_sold": _format_numeric_for_response(sum(float(row["total_qty_sold"] or 0) for row in product_rows)),
        "total_units": _format_numeric_for_response(sum(float(row["total_units"] or 0) for row in product_rows)),
        "item_dollars": _format_numeric_for_response(sum(float(row.get("item_dollars") or 0) for row in product_rows)),
        "void_dollars": _format_numeric_for_response(sum(float(row.get("void_dollars") or 0) for row in product_rows)),
        "products": len(product_rows),
    }
    return product_rows, summary


def _get_recent_product_mix_uploads(restaurant=None, limit=12, search_text="", start_date=None, end_date=None):
    conn = get_db_connection()
    where_clauses = []
    params = []

    if _is_admin_user():
        pass
    elif restaurant:
        where_clauses.append("u.restaurant_id = ?")
        params.append(restaurant["id"])
    else:
        conn.close()
        return []

    cleaned_search = _clean_text(search_text, 120)
    if cleaned_search:
        like_value = f"%{cleaned_search}%"
        where_clauses.append("(u.filename LIKE ? OR r.name LIKE ? OR COALESCE(r.location, '') LIKE ?)")
        params.extend([like_value, like_value, like_value])

    if start_date:
        where_clauses.append("COALESCE(u.report_end_date, u.report_start_date, '') >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("COALESCE(u.report_start_date, u.report_end_date, '') <= ?")
        params.append(end_date)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"""
        SELECT u.id, u.filename, u.report_start_date, u.report_end_date, u.uploaded_at,
               r.id AS restaurant_id, r.name AS restaurant_name, r.location AS restaurant_location
        FROM product_mix_uploads u
        JOIN restaurants r ON r.id = u.restaurant_id
        {where_sql}
        ORDER BY u.id DESC
    """
    if limit is None:
        rows = conn.execute(query, params).fetchall()
    else:
        rows = conn.execute(f"{query}\nLIMIT ?", (*params, int(limit))).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_production_list_report_rows(restaurant=None, start_date=None, end_date=None, search_text=""):
    if not restaurant:
        return []

    conn = get_db_connection()

    join_params = []
    date_clauses = []
    if start_date:
        date_clauses.append("r.report_start_date >= ?")
        join_params.append(start_date)
    if end_date:
        date_clauses.append("r.report_end_date <= ?")
        join_params.append(end_date)

    report_join_filter = ""
    if date_clauses:
        report_join_filter = " AND " + " AND ".join(date_clauses)

    where_params = [int(restaurant["id"])]
    search_clause = ""
    cleaned_search = _clean_text(search_text, 120)
    if cleaned_search:
        like_value = f"%{cleaned_search}%"
        search_clause = " AND (m.production_item_name LIKE ? OR m.source_item_name LIKE ?)"
        where_params.extend([like_value, like_value])

    params = [*join_params, *where_params]

    rows = conn.execute(
        f"""
        SELECT
            m.production_item_name,
            m.source_item_name,
            COALESCE(m.units_per_order, 0) AS units_per_order,
            COALESCE(SUM(r.col_i), 0) AS orders,
            COALESCE(SUM(r.col_l), 0) AS gross_total,
            COALESCE(AVG(r.col_j), 0) AS avg_price
        FROM product_item_production_mappings m
        LEFT JOIN all_levels_items i
          ON i.restaurant_id = m.restaurant_id
         AND LOWER(TRIM(i.item_name)) = LOWER(TRIM(m.source_item_name))
        LEFT JOIN all_levels_records r
          ON r.item_id = i.id
         {report_join_filter}
        WHERE m.restaurant_id = ?
          AND m.production_category_name = 'Production List'
          {search_clause}
        GROUP BY m.production_item_name, m.source_item_name, m.units_per_order
        ORDER BY LOWER(m.production_item_name) ASC, LOWER(m.source_item_name) ASC
        """,
        params,
    ).fetchall()
    conn.close()

    case_size = 250.0
    grouped = {}
    for row in rows:
        production_item = str(row["production_item_name"] or "").strip()
        source_item = str(row["source_item_name"] or "").strip()
        if not production_item or not source_item:
            continue

        orders = float(row["orders"] or 0)
        gross_total = float(row["gross_total"] or 0)
        avg_price = float(row["avg_price"] or 0)
        units_per_order = float(row["units_per_order"] or 0)
        item_cost = (gross_total / orders) if orders > 0 else avg_price
        total_units = orders * units_per_order

        group = grouped.setdefault(
            production_item,
            {
                "production_item_name": production_item,
                "rows": [],
                "total_units": 0.0,
                "total_orders": 0.0,
                "total_gross": 0.0,
            },
        )
        group["rows"].append(
            {
                "source_item_name": source_item,
                "item_cost": item_cost,
                "orders": orders,
                "gross_total": gross_total,
                "units_per_order": units_per_order,
                "total_units": total_units,
            }
        )
        group["total_units"] += total_units
        group["total_orders"] += orders
        group["total_gross"] += gross_total

    result = []
    for production_item in sorted(grouped.keys(), key=lambda v: v.lower()):
        group = grouped[production_item]
        group["rows"].sort(key=lambda r: r["source_item_name"].lower())
        group["cases_required"] = math.ceil(group["total_units"] / case_size) if group["total_units"] > 0 else 0
        group["case_size"] = case_size
        result.append(group)

    return result


def _get_product_mix_upload_record(upload_id):
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT u.id, u.filename, u.report_start_date, u.report_end_date, u.uploaded_at,
               r.id AS restaurant_id, r.name AS restaurant_name, r.location AS restaurant_location
        FROM product_mix_uploads u
        JOIN restaurants r ON r.id = u.restaurant_id
        WHERE u.id = ?
        LIMIT 1
        """,
        (int(upload_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _build_saved_category_payload(category_name, saved_rows):
    category_config = CATEGORIES.get(category_name, {})
    configured_items = category_config.get("items", {})
    ordered_names = list(configured_items.keys())
    rows_by_name = {str(row["item_name"]): dict(row) for row in saved_rows}

    all_item_rows = []
    for item_name in ordered_names:
        row = rows_by_name.pop(item_name, None)
        qty_sold = float(row["qty_sold"]) if row else 0.0
        multiplier = float(row["multiplier"]) if row else float(configured_items.get(item_name, 0))
        total = float(row["total"]) if row else qty_sold * multiplier
        all_item_rows.append(
            {
                "item_name": item_name,
                "qty_sold": int(qty_sold) if qty_sold == int(qty_sold) else round(qty_sold, 2),
                "multiplier": int(multiplier) if multiplier == int(multiplier) else round(multiplier, 2),
                "total": int(total) if total == int(total) else round(total, 2),
            }
        )

    for extra_name, row in rows_by_name.items():
        qty_sold = float(row["qty_sold"])
        multiplier = float(row["multiplier"])
        total = float(row["total"])
        all_item_rows.append(
            {
                "item_name": extra_name,
                "qty_sold": int(qty_sold) if qty_sold == int(qty_sold) else round(qty_sold, 2),
                "multiplier": int(multiplier) if multiplier == int(multiplier) else round(multiplier, 2),
                "total": int(total) if total == int(total) else round(total, 2),
            }
        )

    results = [row for row in all_item_rows if float(row["qty_sold"]) > 0]
    total_items = sum(float(row["total"]) for row in all_item_rows)
    case_quantity = float(category_config.get("case_quantity", 0) or 0)
    is_weight_based = bool(category_config.get("is_weight_based", False)) or any(bool(r["is_weight_based"]) for r in saved_rows)
    oz_per_piece = category_config.get("oz_per_piece")
    summary = {"case_quantity": case_quantity}

    if is_weight_based and oz_per_piece:
        total_oz = total_items * float(oz_per_piece)
        total_lbs = total_oz / 16
        cases_required = total_lbs / case_quantity if case_quantity else 0
        summary.update(
            {
                "type": "weight",
                "total_items": int(total_items) if total_items == int(total_items) else round(total_items, 2),
                "total_oz": round(total_oz, 2),
                "total_lbs": round(total_lbs, 2),
                "oz_per_piece": oz_per_piece,
                "cases_required": round(cases_required, 2),
                "cases_rounded": math.ceil(cases_required),
            }
        )
    else:
        cases_required = total_items / case_quantity if case_quantity else 0
        summary.update(
            {
                "type": "regular",
                "total_items": int(total_items) if total_items == int(total_items) else round(total_items, 2),
                "cases_required": round(cases_required, 2),
                "cases_rounded": math.ceil(cases_required),
            }
        )

    return {
        "category": category_name,
        "results": results,
        "all_items": all_item_rows,
        "summary": summary,
    }


def _build_saved_upload_payload(upload_id):
    upload_row = _get_product_mix_upload_record(upload_id)
    if not upload_row:
        return None, "Upload not found", 404
    if not _has_access_to_restaurant_id(upload_row["restaurant_id"]):
        return None, "You do not have access to this upload", 403

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT category_name, item_name, qty_sold, multiplier, total, is_weight_based
        FROM product_mix_items
        WHERE upload_id = ?
        ORDER BY id ASC
        """,
        (int(upload_id),),
    ).fetchall()
    conn.close()

    grouped_rows = {}
    for row in rows:
        grouped_rows.setdefault(row["category_name"], []).append(row)

    all_results = {}
    for category_name in CATEGORIES.keys():
        all_results[category_name] = _build_saved_category_payload(category_name, grouped_rows.get(category_name, []))

    for category_name, category_rows in grouped_rows.items():
        if category_name not in all_results:
            all_results[category_name] = _build_saved_category_payload(category_name, category_rows)

    return {
        "data": all_results,
        "upload": {
            "id": upload_row["id"],
            "restaurant_id": upload_row["restaurant_id"],
            "restaurant_name": upload_row["restaurant_name"],
            "restaurant_location": upload_row["restaurant_location"],
            "filename": upload_row["filename"],
            "report_start_date": upload_row["report_start_date"],
            "report_end_date": upload_row["report_end_date"],
            "uploaded_at": upload_row["uploaded_at"],
        },
    }, None, None


def _delete_product_mix_upload(upload_id):
    upload_row = _get_product_mix_upload_record(upload_id)
    if not upload_row:
        return "Upload not found", 404
    if not _has_access_to_restaurant_id(upload_row["restaurant_id"]):
        return "You do not have access to this upload", 403

    conn = get_db_connection()
    conn.execute("DELETE FROM product_mix_items WHERE upload_id = ?", (int(upload_id),))
    conn.execute("DELETE FROM product_mix_uploads WHERE id = ?", (int(upload_id),))
    conn.commit()
    conn.close()
    return None, None


def resolve_item_qty_columns(df):
    """Resolve item and qty columns across legacy and new Product Mix exports."""
    normalized = {str(c).strip().lower(): c for c in df.columns}

    item_candidates = ["item, open item", "item"]
    qty_candidates = ["qty sold", "qty_sold", "qty"]

    item_col_name = next((normalized[c] for c in item_candidates if c in normalized), None)
    qty_col_name = next((normalized[c] for c in qty_candidates if c in normalized), None)

    if item_col_name is not None and qty_col_name is not None:
        return df[item_col_name], df[qty_col_name]

    # Legacy fallback based on fixed column positions H and N.
    if df.shape[1] >= 14:
        return df.iloc[:, 7], df.iloc[:, 13]

    raise ValueError(
        "Could not find item and quantity columns. "
        f"Available columns: {list(df.columns)}"
    )


def read_product_mix_excel(file_storage):
    """Read expected product mix sheet with graceful fallback for real-world sheet names."""
    preferred_names = [
        "Selected levels",
        "Selected Levels",
        "selected levels",
        "All levels",
        "Items",
    ]

    file_storage.stream.seek(0)
    workbook = pd.ExcelFile(file_storage)

    picked_sheet = None
    for name in preferred_names:
        if name in workbook.sheet_names:
            picked_sheet = name
            break

    if not picked_sheet and not workbook.sheet_names:
        raise ValueError("Workbook has no sheets")

    if picked_sheet:
        parsed = workbook.parse(sheet_name=picked_sheet)
        try:
            resolve_item_qty_columns(parsed)
            return parsed
        except ValueError:
            pass

    # Fallback: choose the first sheet that actually contains item + qty columns.
    for candidate in workbook.sheet_names:
        candidate_df = workbook.parse(sheet_name=candidate)
        try:
            resolve_item_qty_columns(candidate_df)
            return candidate_df
        except ValueError:
            continue

    raise ValueError("No compatible product mix sheet was found in this workbook")


# ---------------------------------------------------------------------------
# All Levels parsing (new per-item strategy)
# ---------------------------------------------------------------------------

_ALL_LEVELS_COL_INDICES = {"B": 1, "C": 2, "E": 4, "I": 8, "J": 9, "L": 11, "N": 13, "O": 14, "P": 15}
_ALL_LEVELS_TAB_NAMES = ["All Levels", "All levels", "all levels", "ALL LEVELS"]


def _read_all_levels_sheet(file_storage):
    """Open a product mix workbook and read the 'All Levels' tab.

    Returns (data_df, headers_dict) where:
      - data_df   : DataFrame of data rows (header row dropped), integer-indexed columns
      - headers_dict : dict mapping column letter -> detected header string from row 0
    """
    file_storage.stream.seek(0)
    wb = pd.ExcelFile(file_storage)

    sheet_name = next((s for s in _ALL_LEVELS_TAB_NAMES if s in wb.sheet_names), None)
    if sheet_name is None:
        lower_map = {s.lower(): s for s in wb.sheet_names}
        sheet_name = lower_map.get("all levels")

    if sheet_name is None:
        available = ", ".join(wb.sheet_names)
        raise ValueError(f"No 'All Levels' tab found. Available sheets: {available}")

    df = wb.parse(sheet_name=sheet_name, header=None)

    min_cols = max(_ALL_LEVELS_COL_INDICES.values()) + 1  # 16
    if df.shape[1] < min_cols:
        raise ValueError(
            f"'All Levels' tab has {df.shape[1]} columns; need at least {min_cols} (A–P)."
        )

    headers_dict = {}
    for letter, idx in _ALL_LEVELS_COL_INDICES.items():
        raw = df.iloc[0, idx]
        headers_dict[letter] = str(raw).strip() if pd.notna(raw) else letter

    # Drop header row; return data rows with reset index
    data_df = df.iloc[1:].reset_index(drop=True)
    return data_df, headers_dict


def _process_all_levels_file(file_storage, restaurant):
    """Process an uploaded product mix Excel using the 'All Levels' per-item strategy.

    Column E = item_name (primary key per restaurant).
    Columns B, C, I, J, L, N, O, P = numeric attributes stored per upload date.
    Existing items are matched by name; new dated records are appended.
    Duplicate upload of the same file is silently ignored (UNIQUE guard on item_id+upload_id).
    """
    if file_storage.mimetype not in ALLOWED_UPLOAD_MIME_TYPES:
        return None, {"error": f"{file_storage.filename}: Invalid file type"}, 400

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None, {"error": "Filename is invalid"}, 400

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        return None, {"error": f"{filename}: Only .xlsx / .xls files are allowed"}, 400

    try:
        data_df, headers_dict = _read_all_levels_sheet(file_storage)
    except Exception as e:
        return None, {"error": f"Could not read Excel file '{filename}': {str(e)}"}, 400

    start_date, end_date = parse_dates_from_filename(filename)

    col_e = _ALL_LEVELS_COL_INDICES["E"]
    col_b = _ALL_LEVELS_COL_INDICES["B"]
    col_c = _ALL_LEVELS_COL_INDICES["C"]
    col_i = _ALL_LEVELS_COL_INDICES["I"]
    col_j = _ALL_LEVELS_COL_INDICES["J"]
    col_l = _ALL_LEVELS_COL_INDICES["L"]
    col_n = _ALL_LEVELS_COL_INDICES["N"]
    col_o = _ALL_LEVELS_COL_INDICES["O"]
    col_p = _ALL_LEVELS_COL_INDICES["P"]

    try:
        conn = get_db_connection()

        # One upload per restaurant per report day. Other restaurants may upload the same day.
        dedupe_day = start_date or end_date
        existing_upload = _find_existing_upload_for_restaurant_day(conn, restaurant["id"], dedupe_day)
        if existing_upload:
            conn.close()
            return {
                "skipped": True,
                "skip_reason": "duplicate_day",
                "skip_message": f"{filename}: Skipped. A Product Mix for {dedupe_day} already exists for this location ({existing_upload['filename']}).",
                "upload": {
                    "restaurant_id": restaurant["id"],
                    "restaurant_name": restaurant["name"],
                    "filename": filename,
                    "report_start_date": start_date,
                    "report_end_date": end_date,
                    "existing_upload_id": int(existing_upload["id"]),
                    "existing_filename": str(existing_upload["filename"] or ""),
                    "existing_uploaded_at": existing_upload["uploaded_at"],
                },
            }, None, None

        # Insert upload metadata record
        cur = conn.execute(
            """
            INSERT INTO product_mix_uploads (restaurant_id, filename, report_start_date, report_end_date)
            VALUES (?, ?, ?, ?)
            """,
            (restaurant["id"], filename, start_date, end_date),
        )
        upload_id = cur.lastrowid

        # Upsert detected column header names (skip E — that's the key column)
        for letter, header_name in headers_dict.items():
            if letter == "E":
                continue
            conn.execute(
                """
                INSERT INTO all_levels_column_headers (restaurant_id, col_letter, header_name)
                VALUES (?, ?, ?)
                ON CONFLICT(restaurant_id, col_letter) DO UPDATE SET header_name = excluded.header_name
                """,
                (restaurant["id"], letter, header_name),
            )

        items_processed = 0
        items_new = 0

        for _, row in data_df.iterrows():
            raw_name = row.iloc[col_e]
            item_name = str(raw_name).strip() if pd.notna(raw_name) else ""
            if not item_name or item_name.lower() in {"nan", "none"}:
                continue

            # INSERT OR IGNORE into item registry; then fetch id
            conn.execute(
                "INSERT OR IGNORE INTO all_levels_items (restaurant_id, item_name) VALUES (?, ?)",
                (restaurant["id"], item_name),
            )
            item_row = conn.execute(
                "SELECT id FROM all_levels_items WHERE restaurant_id = ? AND item_name = ?",
                (restaurant["id"], item_name),
            ).fetchone()
            if not item_row:
                continue
            item_id = item_row["id"]

            # Check if this was a new insert (changes() == 1 only right after INSERT OR IGNORE)
            was_new = conn.execute("SELECT changes()").fetchone()[0]
            if was_new:
                items_new += 1

            # Insert dated attribute record; ignore if same item+upload already exists
            conn.execute(
                """
                INSERT OR IGNORE INTO all_levels_records
                (item_id, upload_id, restaurant_id, report_start_date, report_end_date,
                 col_b, col_c, col_i, col_j, col_l, col_n, col_o, col_p)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id, upload_id, restaurant["id"], start_date, end_date,
                    _safe_float(row.iloc[col_b]),
                    _safe_float(row.iloc[col_c]),
                    _safe_float(row.iloc[col_i]),
                    _safe_float(row.iloc[col_j]),
                    _safe_float(row.iloc[col_l]),
                    _safe_float(row.iloc[col_n]),
                    _safe_float(row.iloc[col_o]),
                    _safe_float(row.iloc[col_p]),
                ),
            )
            items_processed += 1

        conn.commit()
        conn.close()

    except Exception as e:
        return None, {"error": f"Failed while processing '{filename}': {str(e)}"}, 500

    return {
        "upload": {
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "filename": filename,
            "report_start_date": start_date,
            "report_end_date": end_date,
            "items_processed": items_processed,
            "items_new": items_new,
        },
    }, None, None


init_db()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe_float(val):
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def process_category(df, cat_name, cat_data):
    items = cat_data["items"]
    case_qty = cat_data["case_quantity"]
    is_weight = cat_data.get("is_weight_based", False)
    oz_per_piece = cat_data.get("oz_per_piece")

    item_col, qty_col = resolve_item_qty_columns(df)

    all_item_rows = []
    results = []
    total_items = 0.0

    # Consolidate each mapped product into one row; this guarantees product data is created per item.
    for item_name, multiplier in items.items():
        qty_sold = 0.0
        for idx, cell in enumerate(item_col):
            if pd.notna(cell) and item_name in str(cell):
                qty_sold += _safe_float(qty_col.iloc[idx])

        total = qty_sold * multiplier
        total_items += total

        row = {
            "item_name": item_name,
            "qty_sold": int(qty_sold) if qty_sold == int(qty_sold) else round(qty_sold, 2),
            "multiplier": multiplier,
            "total": int(total) if total == int(total) else round(total, 2),
        }
        all_item_rows.append(row)

        if qty_sold > 0:
            results.append(row)

    summary = {"case_quantity": case_qty}

    if is_weight and oz_per_piece:
        total_oz = total_items * oz_per_piece
        total_lbs = total_oz / 16
        cases_required = total_lbs / case_qty if case_qty else 0
        cases_rounded = math.ceil(cases_required)
        summary.update({
            "type": "weight",
            "total_items": int(total_items) if total_items == int(total_items) else round(total_items, 2),
            "total_oz": round(total_oz, 2),
            "total_lbs": round(total_lbs, 2),
            "oz_per_piece": oz_per_piece,
            "cases_required": round(cases_required, 2),
            "cases_rounded": cases_rounded,
        })
    else:
        cases_required = total_items / case_qty if case_qty else 0
        cases_rounded = math.ceil(cases_required)
        summary.update({
            "type": "regular",
            "total_items": int(total_items) if total_items == int(total_items) else round(total_items, 2),
            "cases_required": round(cases_required, 2),
            "cases_rounded": cases_rounded,
        })

    return {
        "results": results,
        "all_items": all_item_rows,
        "summary": summary,
        "category": cat_name,
    }


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if FORMULA_MODE:
        return redirect(url_for("home"))

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = request.args.get("error")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("login.html", error="Email and password are required.")

        auth_row = get_user_auth_row_by_email(email)
        if not auth_row or not check_password_hash(auth_row["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.")

        login_user(User(auth_row), remember=False)

        next_path = request.args.get("next")
        if next_path and next_path.startswith("/"):
            return redirect(next_path)
        return redirect(url_for("home"))

    return render_template("login.html", error=error)


@app.route("/auth/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if FORMULA_MODE:
        return redirect(url_for("home"))

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = request.args.get("error")
    success = request.args.get("success")

    if request.method == "POST":
        full_name = _clean_text(request.form.get("full_name", ""), 120)
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password:
            return render_template("register.html", error="Email and password are required.", success=success)

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return render_template("register.html", error="Enter a valid email address.", success=success)

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters.", success=success)

        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match.", success=success)

        existing = get_user_auth_row_by_email(email)
        if existing:
            return render_template("register.html", error="Email is already registered.", success=success)

        try:
            create_user(email=email, password=password, full_name=full_name)
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Email is already registered.", success=success)

        return redirect(url_for("login", error="Account created. Please sign in."))

    return render_template("register.html", error=error, success=success)


@app.post("/auth/logout")
@login_required
@limiter.limit("20 per minute")
def logout():
    if FORMULA_MODE:
        return redirect(url_for("home"))

    logout_user()
    return redirect(url_for("login", error="You have been signed out."))

@app.route("/")
@login_required
def home():
    restaurant = get_active_restaurant()
    return redirect(url_for("index"))


@app.route("/product-mix")
@login_required
def index():
    restaurant = get_active_restaurant()
    load_upload_id_raw = (request.args.get("load_upload_id") or "").strip()
    load_upload_id = int(load_upload_id_raw) if load_upload_id_raw.isdigit() else None
    start_date = _normalize_report_date_filter(request.args.get("start_date")) or ""
    end_date = _normalize_report_date_filter(request.args.get("end_date")) or ""
    recent_uploads = _get_recent_product_mix_uploads(restaurant=restaurant, limit=None)
    return render_template(
        "index.html",
        categories=list(CATEGORIES.keys()),
        restaurant=restaurant,
        load_upload_id=load_upload_id,
        recent_uploads=recent_uploads,
        product_log_filters={
            "start_date": start_date,
            "end_date": end_date,
        },
    )


@app.get("/health")
def health():
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return jsonify({"status": "ok", "db": "connected"}), 200
    except Exception:
        return jsonify({"status": "error", "db": "unavailable"}), 503


@app.route("/reports")
@login_required
def reports_page():
    restaurant = get_active_restaurant()
    location_options = _get_accessible_restaurant_switch_options()
    scoped_restaurant = _resolve_report_restaurant(request.args.get("location_id"), restaurant)
    search_text = (request.args.get("search") or "").strip()
    start_date = _normalize_report_date_filter(request.args.get("start_date"))
    end_date = _normalize_report_date_filter(request.args.get("end_date"))

    conn = get_db_connection()
    if _is_admin_user():
        restaurants_count = conn.execute("SELECT COUNT(*) AS total FROM restaurants").fetchone()["total"]
        uploads_count = conn.execute("SELECT COUNT(*) AS total FROM product_mix_uploads").fetchone()["total"]
        items_count = conn.execute("SELECT COUNT(*) AS total FROM all_levels_items").fetchone()["total"]
    elif scoped_restaurant:
        restaurants_count = conn.execute(
            "SELECT COUNT(*) AS total FROM user_restaurants WHERE user_id = ?",
            (int(current_user.id),),
        ).fetchone()["total"]
        uploads_count = conn.execute(
            "SELECT COUNT(*) AS total FROM product_mix_uploads WHERE restaurant_id = ?",
            (scoped_restaurant["id"],),
        ).fetchone()["total"]
        items_count = conn.execute(
            "SELECT COUNT(*) AS total FROM all_levels_items WHERE restaurant_id = ?",
            (scoped_restaurant["id"],),
        ).fetchone()["total"]
    else:
        restaurants_count = 0
        uploads_count = 0
        items_count = 0

    # Fetch column header names detected during upload for this restaurant
    col_headers = {}
    if scoped_restaurant:
        for hrow in conn.execute(
            "SELECT col_letter, header_name FROM all_levels_column_headers WHERE restaurant_id = ?",
            (scoped_restaurant["id"],),
        ).fetchall():
            col_headers[hrow["col_letter"]] = hrow["header_name"]

    # Build items summary query with optional filters
    items_rows = []
    if scoped_restaurant:
        params = [scoped_restaurant["id"]]
        where_clauses = ["i.restaurant_id = ?"]

        if search_text:
            where_clauses.append("i.item_name LIKE ?")
            params.append(f"%{search_text}%")
        if start_date:
            where_clauses.append("r.report_start_date >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("r.report_end_date <= ?")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)
        rows = conn.execute(
            f"""
            SELECT
                i.id   AS item_id,
                i.item_name,
                COUNT(DISTINCT r.upload_id) AS date_count,
                COALESCE(SUM(r.col_i), 0)  AS total_qty_sold,
                COALESCE(AVG(r.col_j), 0)  AS avg_price,
                MIN(r.report_start_date)   AS first_date,
                MAX(r.report_end_date)     AS last_date
            FROM all_levels_items i
            LEFT JOIN all_levels_records r ON r.item_id = i.id
            WHERE {where_sql}
            GROUP BY i.id, i.item_name
            ORDER BY i.item_name ASC
            """,
            params,
        ).fetchall()
        items_rows = [dict(r) for r in rows]

    conn.close()

    recent_uploads = _get_recent_product_mix_uploads(
        restaurant=scoped_restaurant,
        limit=50,
        search_text=search_text,
        start_date=start_date,
        end_date=end_date,
    )

    summary = {
        "locations": restaurants_count,
        "uploads": uploads_count,
        "tracked_items": items_count,
    }
    return render_template(
        "reports.html",
        restaurant=scoped_restaurant,
        summary=summary,
        recent_uploads=recent_uploads,
        items_rows=items_rows,
        col_headers=col_headers,
        location_options=location_options,
        success=request.args.get("success"),
        error=request.args.get("error"),
        upload_filters={
            "search": search_text,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "location_id": str(scoped_restaurant["id"]) if scoped_restaurant else "",
        },
    )


@app.route("/reports/production")
@login_required
def reports_production_page():
    restaurant = get_active_restaurant()
    location_options = _get_accessible_restaurant_switch_options()
    scoped_restaurant = _resolve_report_restaurant(request.args.get("location_id"), restaurant)
    search_text = (request.args.get("search") or "").strip()
    start_date = _normalize_report_date_filter(request.args.get("start_date"))
    end_date = _normalize_report_date_filter(request.args.get("end_date"))

    production_report_rows = _get_production_list_report_rows(
        restaurant=scoped_restaurant,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
    )

    total_menu_items = sum(len(group.get("rows", [])) for group in production_report_rows)
    total_units = sum(float(group.get("total_units") or 0) for group in production_report_rows)
    total_cases = sum(int(group.get("cases_required") or 0) for group in production_report_rows)

    summary = {
        "production_items": len(production_report_rows),
        "mapped_menu_items": total_menu_items,
        "total_units": _format_numeric_for_response(total_units),
        "cases_required": total_cases,
    }

    return render_template(
        "reports_production.html",
        restaurant=scoped_restaurant,
        summary=summary,
        production_report_rows=production_report_rows,
        location_options=location_options,
        success=request.args.get("success"),
        error=request.args.get("error"),
        upload_filters={
            "search": search_text,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "location_id": str(scoped_restaurant["id"]) if scoped_restaurant else "",
        },
    )


@app.route("/item/<int:item_id>")
@login_required
def item_detail_page(item_id):
    restaurant = get_active_restaurant()
    conn = get_db_connection()

    item_row = conn.execute(
        "SELECT * FROM all_levels_items WHERE id = ?",
        (item_id,),
    ).fetchone()

    if not item_row:
        conn.close()
        return render_template("error.html", error="Item not found", status=404), 404

    item = dict(item_row)

    # Access control: non-admins may only view items for their active restaurant
    if not _is_admin_user() and (not restaurant or item["restaurant_id"] != restaurant["id"]):
        conn.close()
        return render_template("error.html", error="You do not have access to this item", status=403), 403

    # Fetch column header names
    col_headers = {}
    for hrow in conn.execute(
        "SELECT col_letter, header_name FROM all_levels_column_headers WHERE restaurant_id = ?",
        (item["restaurant_id"],),
    ).fetchall():
        col_headers[hrow["col_letter"]] = hrow["header_name"]

    # Fetch all dated records for this item, newest first
    records = [
        dict(r)
        for r in conn.execute(
            """
            SELECT r.*, u.filename, u.uploaded_at
            FROM all_levels_records r
            JOIN product_mix_uploads u ON u.id = r.upload_id
            WHERE r.item_id = ?
            ORDER BY r.report_start_date DESC, r.id DESC
            """,
            (item_id,),
        ).fetchall()
    ]

    conn.close()

    # Compute cross-date summary aggregates
    summary = None
    if records:
        n = len(records)
        summary = {
            "col_b": sum((r["col_b"] or 0) for r in records),
            "col_c": sum((r["col_c"] or 0) for r in records),
            "col_i": sum((r["col_i"] or 0) for r in records),
            "col_j": sum((r["col_j"] or 0) for r in records) / n,
            "col_l": sum((r["col_l"] or 0) for r in records),
            "col_n": sum((r["col_n"] or 0) for r in records),
            "col_o": sum((r["col_o"] or 0) for r in records),
            "col_p": sum((r["col_p"] or 0) for r in records),
        }

    return render_template(
        "item_detail.html",
        item=item,
        records=records,
        summary=summary,
        col_headers=col_headers,
        restaurant=restaurant,
    )


@app.post("/reports/map-item-category")
@login_required
@limiter.limit("30 per minute")
def map_item_category_page():
    item_name = str(request.form.get("item_name") or "").strip()[:180]
    location_id_raw = (request.form.get("location_id") or "").strip()

    if not item_name:
        next_url = request.form.get("next") or url_for("reports_page")
        separator = "&" if "?" in next_url else "?"
        return redirect(f"{next_url}{separator}error=Item+name+is+required")

    mapping_entries, mapping_error = _extract_mapping_entries_from_form(request.form)
    if mapping_error:
        next_url = request.form.get("next") or url_for("reports_page")
        return _append_redirect_message(next_url, "error", mapping_error)

    scoped_restaurant = _resolve_report_restaurant(location_id_raw, get_active_restaurant())
    if not scoped_restaurant:
        return redirect(url_for("reports_page", error="Select+a+location+first"))

    conn = get_db_connection()
    restaurant_ids = _get_selected_sync_restaurant_ids(scoped_restaurant, request.form.getlist("sync_id"))

    for restaurant_id in restaurant_ids:
        conn.execute(
            """
            INSERT INTO product_item_category_overrides (restaurant_id, item_name, category_name)
            VALUES (?, ?, ?)
            ON CONFLICT(restaurant_id, item_name)
            DO UPDATE SET category_name = excluded.category_name
            """,
            (restaurant_id, item_name, "Production List"),
        )
        conn.execute(
            """
            DELETE FROM product_item_production_mappings
            WHERE restaurant_id = ? AND source_item_name = ?
            """,
            (restaurant_id, item_name),
        )
        for entry in mapping_entries:
            if entry["is_new"]:
                master_item = _upsert_master_item(conn, restaurant_id, entry["production_item_name"])
                production_item = _upsert_production_item(
                    conn,
                    restaurant_id,
                    entry["production_item_name"],
                    master_item["id"] if master_item else None,
                    "unit",
                )
            else:
                production_item = _upsert_production_item(conn, restaurant_id, entry["production_item_name"])

            if not production_item:
                conn.close()
                next_url = request.form.get("next") or url_for("reports_page", location_id=scoped_restaurant["id"])
                return _append_redirect_message(next_url, "error", "Choose a valid production item")

            conn.execute(
                """
                INSERT INTO product_item_production_mappings
                (restaurant_id, source_item_name, production_category_name, production_item_name, units_per_order, item_dollars_per_order, void_dollars_per_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    restaurant_id,
                    item_name,
                    "Production List",
                    production_item["item_name"],
                    float(entry["units_per_order"]),
                    float(entry["item_dollars_per_order"]),
                    float(entry["void_dollars_per_order"]),
                ),
            )
    conn.commit()
    conn.close()

    next_url = request.form.get("next") or url_for("reports_page", location_id=scoped_restaurant["id"])
    return _append_redirect_message(next_url, "success", "Mapping saved")


def _append_redirect_message(next_url, key, message):
    safe_next = str(next_url or "").strip() or url_for("production_list_page")
    split = urlsplit(safe_next)
    query_items = parse_qsl(split.query, keep_blank_values=True)

    # Replace any existing key so the latest result is always visible.
    query_items = [(k, v) for (k, v) in query_items if k != key]
    query_items.append((key, str(message or "")))

    rebuilt = split._replace(query=urlencode(query_items, doseq=True))
    return redirect(urlunsplit(rebuilt))


def _get_production_list_next_url(restaurant=None):
    next_url = (request.form.get("next") or "").strip()
    if next_url:
        return next_url
    if restaurant:
        return url_for("production_list_page", location_id=restaurant["id"])
    return url_for("production_list_page")


@app.post("/reports/unmap-item")
@login_required
@limiter.limit("30 per minute")
def unmap_item_category_page():
    item_name = str(request.form.get("item_name") or "").strip()[:180]
    location_id_raw = (request.form.get("location_id") or "").strip()

    next_url = request.form.get("next") or url_for("production_list_page")
    if not item_name:
        return _append_redirect_message(next_url, "error", "Item name is required")

    scoped_restaurant = _resolve_report_restaurant(location_id_raw, get_active_restaurant())
    if not scoped_restaurant:
        return _append_redirect_message(next_url, "error", "Select a location first")

    conn = get_db_connection()
    restaurant_ids = _get_selected_sync_restaurant_ids(scoped_restaurant, request.form.getlist("sync_id"))
    for restaurant_id in restaurant_ids:
        conn.execute(
            """
            DELETE FROM product_item_production_mappings
            WHERE restaurant_id = ? AND source_item_name = ?
            """,
            (restaurant_id, item_name),
        )
        conn.execute(
            """
            DELETE FROM product_item_category_overrides
            WHERE restaurant_id = ? AND item_name = ? AND category_name = 'Production List'
            """,
            (restaurant_id, item_name),
        )

    conn.commit()
    conn.close()
    return _append_redirect_message(next_url, "success", "Mapping removed")


@app.get("/admin")
@login_required
def admin_dashboard():
    if not _is_admin_user():
        return _error_response("You do not have access to the admin dashboard.", 403, "forbidden")

    conn = get_db_connection()
    summary = {
        "restaurants": conn.execute("SELECT COUNT(*) AS total FROM restaurants").fetchone()["total"],
        "users": conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"],
        "uploads": conn.execute("SELECT COUNT(*) AS total FROM product_mix_uploads").fetchone()["total"],
        "tracked_items": conn.execute("SELECT COUNT(*) AS total FROM all_levels_items").fetchone()["total"],
        "dated_records": conn.execute("SELECT COUNT(*) AS total FROM all_levels_records").fetchone()["total"],
    }

    recent_users = conn.execute(
        """
        SELECT id, email, full_name, restaurant_id, created_at
        FROM users
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()

    recent_restaurants = conn.execute(
        """
        SELECT id, name, city, state, created_at
        FROM restaurants
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        summary=summary,
        recent_users=[dict(r) for r in recent_users],
        recent_restaurants=[dict(r) for r in recent_restaurants],
    )


@app.route("/categories")
@login_required
def categories_page():
    return redirect(url_for("production_list_page"))


@app.route("/production-list")
@login_required
def production_list_page():
    restaurant = get_active_restaurant()
    items = []
    master_items = []
    mapping_rows = []
    source_item_rows = []
    sync_target_options = []
    selected_sync_restaurants = []
    selected_sync_ids = []
    selected_sync_id_values = []
    sync_group_restaurants = _get_sync_group_restaurants(restaurant) if restaurant else []

    production_search = _clean_text(request.args.get("production_search"), 120).lower()
    source_search = _clean_text(request.args.get("source_search"), 120).lower()
    source_status = (request.args.get("source_status") or "all").strip().lower()
    count_mode_filter = (request.args.get("count_mode") or "all").strip().lower()

    if restaurant:
        sync_target_options = _get_accessible_restaurant_switch_options()
        requested_sync_ids = request.args.getlist("sync_id")
        if requested_sync_ids:
            selected_sync_ids = _get_selected_sync_restaurant_ids(restaurant, requested_sync_ids)
        else:
            brand_key = _restaurant_sync_group_key(restaurant.get("name"))
            selected_sync_ids = [
                int(option["id"])
                for option in sync_target_options
                if _restaurant_sync_group_key(option.get("name")) == brand_key
            ] or [int(restaurant["id"])]
        selected_lookup = {int(v) for v in selected_sync_ids}
        selected_sync_id_values = [str(v) for v in selected_sync_ids]
        selected_sync_restaurants = [
            option
            for option in sync_target_options
            if int(option["id"]) in selected_lookup
        ]

        conn = get_db_connection()
        _sync_business_reference_data(conn, restaurant)
        existing_items = _get_production_items(conn, restaurant["id"])
        for row in existing_items:
            if row["master_item_id"]:
                continue
            master_item = _upsert_master_item(conn, restaurant["id"], row["item_name"])
            if master_item:
                conn.execute(
                    "UPDATE production_items SET master_item_id = ? WHERE id = ? AND restaurant_id = ?",
                    (int(master_item["id"]), int(row["id"]), int(restaurant["id"])),
                )
        conn.commit()
        items = _get_production_items(conn, restaurant["id"])
        master_items = _get_master_items(conn, restaurant["id"])
        mapping_rows = _get_production_mapping_rows(conn, restaurant["id"])
        conn.close()
        source_item_rows = _get_source_item_history_rows(restaurant, limit=1000, restaurant_ids=selected_sync_ids)

    if production_search:
        items = [
            row
            for row in items
            if production_search in str(row.get("item_name", "")).lower()
            or production_search in str(row.get("master_item_name", "")).lower()
        ]
        master_items = [
            row
            for row in master_items
            if production_search in str(row.get("item_name", "")).lower()
        ]

    if count_mode_filter in {"unit", "weight"}:
        items = [
            row
            for row in items
            if str(row.get("count_mode", "")).lower() == count_mode_filter
        ]

    if source_search:
        source_item_rows = [
            row
            for row in source_item_rows
            if source_search in str(row.get("item_name", "")).lower()
            or source_search in str(row.get("mapped_to", "")).lower()
        ]

    if source_status == "organized":
        source_item_rows = [row for row in source_item_rows if row.get("is_mapped")]
    elif source_status == "unorganized":
        source_item_rows = [row for row in source_item_rows if not row.get("is_mapped")]

    unorganized_source_item_rows = [row for row in source_item_rows if not row.get("is_mapped")]

    return render_template(
        "production_list.html",
        restaurant=restaurant,
        items=items,
        master_items=master_items,
        mapping_rows=mapping_rows,
        source_item_rows=source_item_rows,
        unorganized_source_item_rows=unorganized_source_item_rows,
        sync_group_restaurants=sync_group_restaurants,
        sync_target_options=sync_target_options,
        selected_sync_restaurants=selected_sync_restaurants,
        selected_sync_ids=selected_sync_ids,
        selected_sync_id_values=selected_sync_id_values,
        production_search=production_search,
        source_search=source_search,
        source_status=source_status,
        count_mode_filter=count_mode_filter,
    )


@app.post("/master-items/create")
@login_required
@limiter.limit("30 per minute")
def create_master_item():
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    next_url = _get_production_list_next_url(restaurant)
    item_name = _clean_text(request.form.get("item_name"), 180)
    if not item_name:
        return _append_redirect_message(next_url, "error", "Master item name is required")

    conn = get_db_connection()
    restaurant_ids = _get_sync_group_restaurant_ids(restaurant) or [int(restaurant["id"])]
    for restaurant_id in restaurant_ids:
        _upsert_master_item(conn, restaurant_id, item_name)
    conn.commit()
    conn.close()
    return _append_redirect_message(next_url, "success", "Master item saved")


@app.post("/production-list/create")
@login_required
@limiter.limit("30 per minute")
def create_production_item():
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    next_url = _get_production_list_next_url(restaurant)
    item_name = _clean_text(request.form.get("item_name"), 180)
    master_item_id_raw = (request.form.get("master_item_id") or "").strip()
    count_mode = (request.form.get("count_mode") or "unit").strip().lower()
    if not item_name:
        return _append_redirect_message(next_url, "error", "Production item name is required")
    if not master_item_id_raw.isdigit():
        return _append_redirect_message(next_url, "error", "Choose a master item")
    if count_mode not in {"unit", "weight"}:
        return _append_redirect_message(next_url, "error", "Choose a valid count mode")

    conn = get_db_connection()
    master_row = conn.execute(
        "SELECT item_name FROM master_items WHERE id = ? AND restaurant_id = ? LIMIT 1",
        (int(master_item_id_raw), int(restaurant["id"])),
    ).fetchone()
    if not master_row:
        conn.close()
        return _append_redirect_message(next_url, "error", "Master item not found")

    master_item_name = str(master_row["item_name"])
    restaurant_ids = _get_sync_group_restaurant_ids(restaurant) or [int(restaurant["id"])]
    for restaurant_id in restaurant_ids:
        master_item = _upsert_master_item(conn, restaurant_id, master_item_name)
        _upsert_production_item(conn, restaurant_id, item_name, master_item["id"] if master_item else None, count_mode)
    conn.commit()
    conn.close()
    return _append_redirect_message(next_url, "success", "Production item saved")


@app.post("/production-list/load-template")
@login_required
@limiter.limit("20 per minute")
def load_production_item_template():
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    next_url = _get_production_list_next_url(restaurant)
    conn = get_db_connection()
    inserted = 0
    restaurant_ids = _get_sync_group_restaurant_ids(restaurant) or [int(restaurant["id"])]
    for restaurant_id in restaurant_ids:
        for item_name in PRODUCTION_ITEM_TEMPLATE:
            before = conn.total_changes
            master_item = _upsert_master_item(conn, restaurant_id, item_name)
            _upsert_production_item(conn, restaurant_id, item_name, master_item["id"] if master_item else None, "unit")
            if restaurant_id == int(restaurant["id"]) and conn.total_changes > before:
                inserted += 1

    conn.commit()
    conn.close()
    return _append_redirect_message(next_url, "success", f"Starter template loaded. Added {inserted} item(s).")


@app.post("/production-list/delete/<int:item_id>")
@login_required
@limiter.limit("30 per minute")
def delete_production_item(item_id):
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    next_url = _get_production_list_next_url(restaurant)
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, item_name FROM production_items WHERE id = ? AND restaurant_id = ?",
        (int(item_id), int(restaurant["id"])),
    ).fetchone()
    if not row:
        conn.close()
        return _append_redirect_message(next_url, "error", "Production item not found")

    production_name = str(row["item_name"])
    restaurant_ids = _get_sync_group_restaurant_ids(restaurant) or [int(restaurant["id"])]
    placeholders = ",".join("?" for _ in restaurant_ids)
    conn.execute(
        f"DELETE FROM production_items WHERE restaurant_id IN ({placeholders}) AND item_name = ?",
        (*restaurant_ids, production_name),
    )
    conn.execute(
        f"DELETE FROM product_item_production_mappings WHERE restaurant_id IN ({placeholders}) AND production_item_name = ?",
        (*restaurant_ids, production_name),
    )
    conn.commit()
    conn.close()
    return _append_redirect_message(next_url, "success", "Production item deleted")


@app.route("/restaurant-setup", methods=["GET", "POST"])
@login_required
@limiter.limit("60 per minute")
def restaurant_setup():
    if request.method == "POST":
        payload, payload_error = _validate_restaurant_payload(request.form)
        if payload_error:
            return redirect(url_for("restaurant_setup", error=payload_error.replace(" ", "+")))

        conn = get_db_connection()
        cur = conn.execute(
            """
            INSERT INTO restaurants (name, location, address, city, state, zip_code, phone)
            VALUES (:name, :location, :address, :city, :state, :zip_code, :phone)
            """,
            payload,
        )
        conn.commit()

        _link_user_to_restaurant(conn, int(current_user.id), cur.lastrowid)
        conn.commit()
        conn.close()

        set_active_restaurant(cur.lastrowid)

        return redirect(url_for("restaurant_setup", success="Location+saved"))

    audit_location_filter = _clean_text(request.args.get("audit_location", ""), 120)
    audit_editor_filter = _clean_text(request.args.get("audit_editor", ""), 120)
    audit_request_id_filter = _clean_text(request.args.get("audit_request_id", ""), 32)

    conn = get_db_connection()
    if _is_admin_user():
        rows = conn.execute("SELECT * FROM restaurants ORDER BY id ASC").fetchall()
        audit_query = """
            SELECT a.id, a.edited_at, a.request_id, a.changes_json,
                   r.name AS restaurant_name,
                   r.location AS restaurant_location,
                   u.email AS edited_by_email
            FROM location_edit_audit a
            JOIN restaurants r ON r.id = a.restaurant_id
            JOIN users u ON u.id = a.edited_by_user_id
            WHERE 1=1
        """
        audit_params = []

        if audit_location_filter:
            audit_query += " AND (r.name LIKE ? OR COALESCE(r.location, '') LIKE ?)"
            like_location = f"%{audit_location_filter}%"
            audit_params.extend([like_location, like_location])

        if audit_editor_filter:
            audit_query += " AND u.email LIKE ?"
            audit_params.append(f"%{audit_editor_filter}%")

        if audit_request_id_filter:
            audit_query += " AND COALESCE(a.request_id, '') LIKE ?"
            audit_params.append(f"%{audit_request_id_filter}%")

        audit_query += " ORDER BY a.id DESC LIMIT 25"
        audit_rows = conn.execute(audit_query, audit_params).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT r.*
            FROM restaurants r
            JOIN user_restaurants ur ON ur.restaurant_id = r.id
            WHERE ur.user_id = ?
            ORDER BY r.id ASC
            """,
            (int(current_user.id),),
        ).fetchall()
        audit_rows = []
    conn.close()
    restaurants = [dict(r) for r in rows]
    audit_entries = []
    for row in audit_rows:
        item = dict(row)
        item["changes_summary"] = _format_audit_changes(item.get("changes_json"))
        audit_entries.append(item)

    active_restaurant = get_active_restaurant()
    return render_template(
        "restaurant_setup.html",
        restaurants=restaurants,
        audit_entries=audit_entries,
        audit_location_filter=audit_location_filter,
        audit_editor_filter=audit_editor_filter,
        audit_request_id_filter=audit_request_id_filter,
        active_restaurant=active_restaurant,
        error=request.args.get("error"),
        success=request.args.get("success"),
    )


@app.post("/restaurant/select/<int:restaurant_id>")
@login_required
@limiter.limit("30 per minute")
def select_restaurant(restaurant_id):
    switch_error = _switch_active_restaurant_or_error(restaurant_id)
    if switch_error:
        return redirect(url_for("restaurant_setup", error=switch_error))

    return redirect(url_for("restaurant_setup", success="Active+location+updated"))


@app.post("/restaurant/select")
@login_required
@limiter.limit("30 per minute")
def select_restaurant_post():
    restaurant_id_raw = (request.form.get("restaurant_id") or "").strip()
    if not restaurant_id_raw.isdigit():
        return redirect(url_for("restaurant_setup", error="Restaurant+not+found"))

    switch_error = _switch_active_restaurant_or_error(int(restaurant_id_raw))
    next_url = request.form.get("next") or request.referrer or url_for("restaurant_setup")
    if switch_error:
        separator = "&" if "?" in next_url else "?"
        return redirect(f"{next_url}{separator}error={switch_error}")

    separator = "&" if "?" in next_url else "?"
    return redirect(f"{next_url}{separator}success=Active+location+updated")


@app.post("/restaurant/next")
@login_required
@limiter.limit("30 per minute")
def select_next_restaurant():
    next_url = request.form.get("next") or request.referrer or url_for("home")
    next_restaurant_id = _get_next_restaurant_id(_current_restaurant_id())
    separator = "&" if "?" in next_url else "?"

    if next_restaurant_id is None:
        return redirect(f"{next_url}{separator}error=No+restaurant+available")

    switch_error = _switch_active_restaurant_or_error(next_restaurant_id)
    if switch_error:
        return redirect(f"{next_url}{separator}error={switch_error}")

    return redirect(f"{next_url}{separator}success=Active+location+updated")


@app.post("/restaurant/update/<int:restaurant_id>")
@login_required
@limiter.limit("30 per minute")
def update_restaurant(restaurant_id):
    if not _has_access_to_restaurant_id(restaurant_id):
        return redirect(url_for("restaurant_setup", error="You+cannot+edit+that+location"))

    payload, payload_error = _validate_restaurant_payload(request.form)
    if payload_error:
        return redirect(url_for("restaurant_setup", error=payload_error.replace(" ", "+")))

    conn = get_db_connection()
    existing = conn.execute(
        """
        SELECT id, name, location, address, city, state, zip_code, phone
        FROM restaurants
        WHERE id = ?
        """,
        (restaurant_id,),
    ).fetchone()
    if not existing:
        conn.close()
        return redirect(url_for("restaurant_setup", error="Location+not+found"))

    changes = _restaurant_change_set(existing, payload)

    cur = conn.execute(
        """
        UPDATE restaurants
        SET name = :name,
            location = :location,
            address = :address,
            city = :city,
            state = :state,
            zip_code = :zip_code,
            phone = :phone
        WHERE id = :id
        """,
        {
            "id": restaurant_id,
            "name": payload["name"],
            "location": payload["location"],
            "address": payload["address"],
            "city": payload["city"],
            "state": payload["state"],
            "zip_code": payload["zip_code"],
            "phone": payload["phone"],
        },
    )

    if cur.rowcount == 0:
        conn.close()
        return redirect(url_for("restaurant_setup", error="Location+not+found"))

    if changes:
        conn.execute(
            """
            INSERT INTO location_edit_audit (restaurant_id, edited_by_user_id, request_id, changes_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(restaurant_id),
                int(current_user.id),
                getattr(g, "request_id", None),
                json.dumps(changes, ensure_ascii=True),
            ),
        )

    conn.commit()
    conn.close()
    return redirect(url_for("restaurant_setup", success="Location+updated"))


@app.post("/categories/create")
@login_required
@limiter.limit("30 per minute")
def create_category():
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    payload, payload_error = _validate_category_payload(request.form)
    if payload_error:
        return redirect(url_for("categories_page"))

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO product_categories
        (restaurant_id, name, case_quantity, is_weight_based, oz_per_piece)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(restaurant_id, name)
        DO UPDATE SET
            case_quantity = excluded.case_quantity,
            is_weight_based = excluded.is_weight_based,
            oz_per_piece = excluded.oz_per_piece
        """,
        (
            restaurant["id"],
            payload["name"],
            payload["case_quantity"],
            payload["is_weight_based"],
            payload["oz_per_piece"],
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("categories_page"))


@app.post("/categories/update/<int:category_id>")
@login_required
@limiter.limit("30 per minute")
def update_category(category_id):
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    payload, payload_error = _validate_category_payload(request.form)
    if payload_error:
        return redirect(url_for("categories_page"))

    conn = get_db_connection()
    cur = conn.execute(
        """
        UPDATE product_categories
        SET name = ?, case_quantity = ?, is_weight_based = ?, oz_per_piece = ?
        WHERE id = ? AND restaurant_id = ?
        """,
        (
            payload["name"],
            payload["case_quantity"],
            payload["is_weight_based"],
            payload["oz_per_piece"],
            category_id,
            restaurant["id"],
        ),
    )

    if cur.rowcount == 0:
        existing = conn.execute(
            "SELECT id FROM product_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        conn.close()
        if existing:
            return _error_response("You do not have permission to modify this category.", 403, "forbidden")
        return redirect(url_for("categories_page", error="Category+not+found"))

    conn.commit()
    conn.close()
    return redirect(url_for("categories_page", success="Category+updated"))


@app.post("/categories/delete/<int:category_id>")
@login_required
@limiter.limit("30 per minute")
def delete_category(category_id):
    restaurant = get_active_restaurant()
    if not restaurant:
        return redirect(url_for("restaurant_setup", error="Add+restaurant+information+first"))

    conn = get_db_connection()
    cur = conn.execute(
        "DELETE FROM product_categories WHERE id = ? AND restaurant_id = ?",
        (category_id, restaurant["id"]),
    )

    if cur.rowcount == 0:
        existing = conn.execute(
            "SELECT id FROM product_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        conn.close()
        if existing:
            return _error_response("You do not have permission to delete this category.", 403, "forbidden")
        return redirect(url_for("categories_page", error="Category+not+found"))

    conn.commit()
    conn.close()
    return redirect(url_for("categories_page", success="Category+deleted"))


@app.route("/api/restaurants", methods=["GET", "POST"])
@login_required
@limiter.limit("60 per minute")
def restaurants_api():
    if request.method == "GET":
        conn = get_db_connection()
        if _is_admin_user():
            rows = conn.execute("SELECT * FROM restaurants ORDER BY id ASC").fetchall()
        else:
            rows = conn.execute(
                """
                SELECT r.*
                FROM restaurants r
                JOIN user_restaurants ur ON ur.restaurant_id = r.id
                WHERE ur.user_id = ?
                ORDER BY r.id ASC
                """,
                (int(current_user.id),),
            ).fetchall()
        conn.close()
        return jsonify({"restaurants": [dict(r) for r in rows]})

    payload = request.get_json(silent=True) or {}
    record, payload_error = _validate_restaurant_payload(payload)
    if payload_error:
        return jsonify({"error": payload_error}), 400

    conn = get_db_connection()
    cur = conn.execute(
        """
        INSERT INTO restaurants (name, location, address, city, state, zip_code, phone)
        VALUES (:name, :location, :address, :city, :state, :zip_code, :phone)
        """,
        record,
    )
    conn.commit()
    _link_user_to_restaurant(conn, int(current_user.id), cur.lastrowid)
    conn.commit()

    row = conn.execute("SELECT * FROM restaurants WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    set_active_restaurant(cur.lastrowid)
    return jsonify({"restaurant": dict(row)}), 201


@app.get("/api/restaurant/current")
@login_required
def current_restaurant_api():
    return jsonify({"restaurant": get_active_restaurant()})


@app.get("/api/uploads/recent")
@login_required
def recent_uploads_api():
    restaurant = get_active_restaurant()
    limit_raw = (request.args.get("limit") or "12").strip()
    limit = 12
    if limit_raw.isdigit():
        limit = max(1, min(int(limit_raw), 50))

    search_text = (request.args.get("search") or "").strip()
    start_date = _normalize_report_date_filter(request.args.get("start_date"))
    end_date = _normalize_report_date_filter(request.args.get("end_date"))

    return jsonify(
        {
            "restaurant": restaurant,
            "uploads": _get_recent_product_mix_uploads(
                restaurant=restaurant,
                limit=limit,
                search_text=search_text,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    )


@app.get("/api/reports/product-log")
@login_required
def product_purchase_log_api():
    restaurant = _resolve_report_restaurant(request.args.get("location_id"), get_active_restaurant())
    start_date = _normalize_report_date_filter(request.args.get("start_date"))
    end_date = _normalize_report_date_filter(request.args.get("end_date"))
    search_text = (request.args.get("search") or "").strip()
    include_zero_rows_raw = (request.args.get("include_zero") or "1").strip().lower()
    include_zero_rows = include_zero_rows_raw not in {"0", "false", "no"}

    rows, summary = _get_product_purchase_log(
        restaurant=restaurant,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
        include_zero_rows=include_zero_rows,
    )

    return jsonify(
        {
            "restaurant": restaurant,
            "filters": {
                "search": search_text,
                "start_date": start_date,
                "end_date": end_date,
                "include_zero": include_zero_rows,
            },
            "summary": summary,
            "rows": rows,
        }
    )


@app.get("/api/reports/uncategorized")
@login_required
def uncategorized_source_items_api():
    restaurant = _resolve_report_restaurant(request.args.get("location_id"), get_active_restaurant())
    start_date = _normalize_report_date_filter(request.args.get("start_date"))
    end_date = _normalize_report_date_filter(request.args.get("end_date"))
    search_text = (request.args.get("search") or "").strip()
    limit = _parse_limited_positive_int(request.args.get("limit"), 200, min_value=1, max_value=2000)

    rows = _get_uncategorized_source_items(
        restaurant=restaurant,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
        limit=limit,
    )

    return jsonify(
        {
            "restaurant": restaurant,
            "filters": {
                "search": search_text,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
            "rows": rows,
            "count": len(rows),
        }
    )


@app.get("/api/reports/source-history")
@login_required
def source_item_history_api():
    restaurant = _resolve_report_restaurant(request.args.get("location_id"), get_active_restaurant())
    limit = _parse_limited_positive_int(request.args.get("limit"), 500, min_value=1, max_value=5000)
    search_text = _clean_text(request.args.get("search"), 120).lower()

    rows = _get_source_item_history_rows(restaurant=restaurant, limit=limit)
    if search_text:
        rows = [
            row
            for row in rows
            if search_text in str(row.get("item_name", "")).lower()
            or search_text in str(row.get("mapped_to", "")).lower()
        ]

    return jsonify(
        {
            "restaurant": restaurant,
            "filters": {
                "search": search_text,
                "limit": limit,
            },
            "rows": rows,
            "count": len(rows),
        }
    )


@app.get("/api/reports/product-log/export.csv")
@login_required
def product_purchase_log_export_csv_api():
    restaurant = _resolve_report_restaurant(request.args.get("location_id"), get_active_restaurant())
    start_date = _normalize_report_date_filter(request.args.get("start_date"))
    end_date = _normalize_report_date_filter(request.args.get("end_date"))
    search_text = (request.args.get("search") or "").strip()
    include_zero_rows_raw = (request.args.get("include_zero") or "1").strip().lower()
    include_zero_rows = include_zero_rows_raw not in {"0", "false", "no"}

    rows, summary = _get_product_purchase_log(
        restaurant=restaurant,
        start_date=start_date,
        end_date=end_date,
        search_text=search_text,
        include_zero_rows=include_zero_rows,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Category",
        "Item",
        "Qty Sold",
        "Units",
        "Item Dollars",
        "Void Dollars",
        "Upload Count",
        "Configured Multiplier",
        "Configured",
        "First Report Start",
        "Last Report End",
    ])

    for row in rows:
        writer.writerow(
            [
                row.get("category_name", ""),
                row.get("item_name", ""),
                row.get("total_qty_sold", 0),
                row.get("total_units", 0),
                row.get("item_dollars", 0),
                row.get("void_dollars", 0),
                row.get("upload_count", 0),
                row.get("configured_multiplier", ""),
                "yes" if row.get("is_configured") else "no",
                row.get("first_report_start", ""),
                row.get("last_report_end", ""),
            ]
        )

    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Products", summary.get("products", 0)])
    writer.writerow(["Total Qty Sold", summary.get("total_qty_sold", 0)])
    writer.writerow(["Total Units", summary.get("total_units", 0)])
    writer.writerow(["Total Item Dollars", summary.get("item_dollars", 0)])
    writer.writerow(["Total Void Dollars", summary.get("void_dollars", 0)])

    output.seek(0)
    filename = f"product_purchase_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/uploads/<int:upload_id>")
@login_required
def upload_detail_api(upload_id):
    payload, error_message, status_code = _build_saved_upload_payload(upload_id)
    if error_message:
        return _error_response(error_message, status_code, "upload_lookup_failed")
    return jsonify(payload)


@app.post("/api/uploads/<int:upload_id>/delete")
@login_required
def delete_upload_api(upload_id):
    error_message, status_code = _delete_product_mix_upload(upload_id)
    if error_message:
        return _error_response(error_message, status_code, "upload_delete_failed")
    return jsonify({"success": True, "upload_id": upload_id})


@app.post("/uploads/delete/<int:upload_id>")
@login_required
def delete_upload_page(upload_id):
    error_message, _ = _delete_product_mix_upload(upload_id)
    if error_message:
        flash(error_message, "danger")
    else:
        flash("Saved upload deleted.", "success")

    next_url = request.form.get("next") or url_for("reports_page")
    return redirect(next_url)


@app.get("/api/categories")
@login_required
def categories_api():
    restaurant = get_active_restaurant()
    if not restaurant:
        return jsonify({"categories": [], "restaurant": None})

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, name, case_quantity, is_weight_based, oz_per_piece
        FROM product_categories
        WHERE restaurant_id = ?
        ORDER BY name ASC
        """,
        (restaurant["id"],),
    ).fetchall()
    conn.close()
    return jsonify({"restaurant": restaurant, "categories": [dict(r) for r in rows]})


@app.get("/api/reports/overview")
@login_required
def reports_overview_api():
    conn = get_db_connection()
    restaurant = get_active_restaurant()

    if _is_admin_user():
        restaurants_count = conn.execute("SELECT COUNT(*) AS total FROM restaurants").fetchone()["total"]
        production_items_count = conn.execute("SELECT COUNT(*) AS total FROM production_items").fetchone()["total"]
        uploads_count = conn.execute("SELECT COUNT(*) AS total FROM product_mix_uploads").fetchone()["total"]
        product_rows_count = conn.execute("SELECT COUNT(*) AS total FROM product_mix_items").fetchone()["total"]
    elif restaurant:
        restaurants_count = conn.execute(
            "SELECT COUNT(*) AS total FROM user_restaurants WHERE user_id = ?",
            (int(current_user.id),),
        ).fetchone()["total"]
        production_items_count = conn.execute(
            "SELECT COUNT(*) AS total FROM production_items WHERE restaurant_id = ?",
            (restaurant["id"],),
        ).fetchone()["total"]
        uploads_count = conn.execute(
            "SELECT COUNT(*) AS total FROM product_mix_uploads WHERE restaurant_id = ?",
            (restaurant["id"],),
        ).fetchone()["total"]
        product_rows_count = conn.execute(
            "SELECT COUNT(*) AS total FROM product_mix_items WHERE restaurant_id = ?",
            (restaurant["id"],),
        ).fetchone()["total"]
    else:
        restaurants_count = 0
        production_items_count = 0
        uploads_count = 0
        product_rows_count = 0
    conn.close()
    return jsonify(
        {
            "summary": {
                "restaurants": restaurants_count,
                "configured_categories": production_items_count,
                "production_items": production_items_count,
                "product_mix_templates": len(CATEGORIES),
                "uploads": uploads_count,
                "product_rows": product_rows_count,
            }
        }
    )


@app.route("/upload", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def upload():
    restaurant = get_active_restaurant()
    if not restaurant:
        message = "Restaurant information is required first. Open Restaurant Setup."
        if _wants_json_response():
            return jsonify({"error": message}), 400
        return redirect(url_for("index", error=message))

    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files and "file" in request.files and request.files["file"].filename:
        files = [request.files["file"]]

    if not files:
        message = "No file provided"
        if _wants_json_response():
            return jsonify({"error": message}), 400
        return redirect(url_for("index", error=message))

    processed = []
    skipped = []
    for file_storage in files:
        result, error_payload, status_code = _process_all_levels_file(file_storage, restaurant)
        if error_payload:
            if _wants_json_response():
                return jsonify(error_payload), status_code
            message = str(error_payload.get("error") or "Upload failed")
            return redirect(url_for("index", error=message))
        if result and result.get("skipped"):
            skipped.append(result)
            continue
        processed.append(result)

    payload = {
        "success": True,
        "processed_count": len(processed),
        "processed_uploads": [entry["upload"] for entry in processed],
        "skipped_count": len(skipped),
        "skipped_uploads": [entry.get("upload", {}) for entry in skipped],
        "upload": processed[-1]["upload"] if processed else (skipped[-1].get("upload") if skipped else None),
    }
    if _wants_json_response():
        return jsonify(payload)

    message_parts = []
    if processed:
        message_parts.append(f"Uploaded {len(processed)} file(s).")
    if skipped:
        message_parts.append(f"Skipped {len(skipped)} file(s) because that day already exists for the active location.")
    if not message_parts:
        message_parts.append("No files were uploaded.")

    message = " ".join(message_parts)
    return redirect(url_for("index", success=message))


@app.route("/export", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def export():
    payload = request.get_json(silent=True)
    if not payload or "data" not in payload:
        return jsonify({"error": "No data provided"}), 400

    output = io.StringIO()
    writer = csv.writer(output)

    try:
        for cat_name, cat_data in payload["data"].items():
            writer.writerow([f"=== {cat_name.upper()} ==="])

            summary = cat_data.get("summary", {})
            is_weight = summary.get("type") == "weight"
            col_header = "Total Pieces" if is_weight else f"Total {cat_name}"

            writer.writerow(["Item Name", "Qty Sold", "Multiplier", col_header])

            for row in cat_data.get("results", []):
                writer.writerow([row["item_name"], row["qty_sold"], row["multiplier"], row["total"]])

            writer.writerow([])

            if is_weight:
                writer.writerow(["TOTAL PIECES", "", "", summary.get("total_items", "")])
                writer.writerow([f"TOTAL OUNCES ({summary.get('oz_per_piece')} oz per piece)", "", "", summary.get("total_oz", "")])
                writer.writerow(["TOTAL POUNDS", "", "", summary.get("total_lbs", "")])
                writer.writerow([f"CASES REQUIRED ({summary.get('case_quantity')} lbs per case)", "", "", summary.get("cases_required", "")])
            else:
                writer.writerow([f"TOTAL {cat_name.upper()}", "", "", summary.get("total_items", "")])
                writer.writerow([f"CASES REQUIRED ({summary.get('case_quantity')} per case)", "", "", summary.get("cases_required", "")])

            writer.writerow(["CASES ROUND UP", "", "", summary.get("cases_rounded", "")])
            inventory = cat_data.get("inventory", 0)
            writer.writerow(["ITEM INVENTORY", "", "", inventory])
            total_required = math.ceil(summary.get("cases_rounded", 0) - float(inventory))
            writer.writerow(["TOTAL REQUIRED", "", "", total_required])
            writer.writerow([])
    except Exception as e:
        return jsonify({"error": f"Failed to create CSV export: {str(e)}"}), 500

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=product_mix_results.csv"},
    )


@app.get("/api/ping")
@login_required
@limiter.limit("5 per minute")
def api_ping():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Return JSON for API routes so frontend can show useful errors."""
    if isinstance(error, RequestEntityTooLarge):
        if UPLOAD_MAX_BYTES > 0:
            max_mb = max(1, int(math.ceil(UPLOAD_MAX_BYTES / (1024 * 1024))))
            return _error_response(f"File is too large. Max upload size is {max_mb} MB.", 413, "payload_too_large")
        return _error_response("File is too large. The server rejected the upload payload.", 413, "payload_too_large")

    if isinstance(error, HTTPException):
        if _is_api_request():
            return _error_response(error.description, error.code, "http_error")
        return error

    if _is_api_request():
        return _error_response(f"Unexpected server error: {str(error)}", 500, "internal_error")

    return _error_response("Unexpected server error. Please try again.", 500, "internal_error")


@app.errorhandler(429)
def handle_rate_limit(error):
    if _is_api_request():
        return _error_response("Too many requests. Please slow down and try again.", 429, "rate_limited")

    if request.path.startswith("/auth/"):
        return render_template("login.html", error="Too many attempts. Please wait and try again."), 429

    return _error_response("Too many requests. Please wait and try again.", 429, "rate_limited")


if __name__ == "__main__":
    debug_mode = os.environ.get("PM_DEBUG", "1") == "1"
    app.run(debug=debug_mode, port=5050)
