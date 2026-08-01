import os
import re
import csv
import io
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "budget.db")

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max upload

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS csv_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id INTEGER REFERENCES csv_imports(id),
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id INTEGER NOT NULL REFERENCES csv_imports(id),
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL,
    is_duplicate INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manual_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS savings_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    run_month TEXT NOT NULL,
    income_1 REAL NOT NULL,
    income_2 REAL NOT NULL,
    monthly_expenses_total REAL NOT NULL,
    recurring_total REAL NOT NULL,
    mortgage_total REAL NOT NULL,
    expense_total REAL NOT NULL,
    split_pct_1 REAL NOT NULL,
    split_pct_2 REAL NOT NULL,
    contribution_1 REAL NOT NULL,
    contribution_2 REAL NOT NULL,
    leftover_1 REAL NOT NULL,
    leftover_2 REAL NOT NULL,
    current_balance_1 REAL NOT NULL,
    current_balance_2 REAL NOT NULL,
    buffer_goal REAL NOT NULL,
    sinking_pct REAL NOT NULL,
    growth_pct REAL NOT NULL,
    fun_pct REAL NOT NULL,
    buffer_1 REAL NOT NULL,
    sinking_1 REAL NOT NULL,
    growth_1 REAL NOT NULL,
    fun_1 REAL NOT NULL,
    buffer_2 REAL NOT NULL,
    sinking_2 REAL NOT NULL,
    growth_2 REAL NOT NULL,
    fun_2 REAL NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monthly_budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(month, category)
);
"""

# ---------------------------------------------------------------------------
# Keyword / vendor rules
# ---------------------------------------------------------------------------
MORTGAGE_KEYWORDS = ["ROCKET MORTGAGE"]

RECURRING_KEYWORDS = ["RECURRING PAYMENT"]

RECURRING_VENDORS = [
    "CRICKET WIRELESS",
    "HLU*HULUPLUS", "HULU",
    "NETFLIX",
    "PAYPAL *EXPRESSVPN", "EXPRESSVPN",
    "BGC MYCLUBHUB",
    "BRGHTWHL", "BRIGHTWHEEL",
    "AUDIBLE",
    "CUBESMART",
    "CITY OF KINGSVIL",
    "CPENERGY ENTEX",
    "CHAMPION ENERGY",
    "PROG COUNTY MUT INS",
    "PAYPAL *PADDLE",
    "PAYPAL *MICROSOFT",
    "PAYPAL *KASEENSS",
]

TRANSFER_KEYWORDS = [
    "ONLINE TRANSFER TO",
    "ONLINE TRANSFER FROM",
    "MONEY TRANSFER",
    "APPLE CASH SENT",
]

TRANSFER_EXTRA_KEYWORDS = [
    "ZELLE",
    "VENMO",
    "CASH APP",
    "PAYPAL *XFER",
    "TRANSFER",
]

DEPOSIT_KEYWORDS = [
    "EDEPOSIT",
    "DEPOSIT",
]

BUDGET_CATEGORIES = ["mortgage", "recurring", "expense", "transfer"]

# Merchant display name normalization map (substring → display name)
MERCHANT_MAP = [
    ("ROCKET MORTGAGE", "Rocket Mortgage"),
    ("CRICKET WIRELESS", "Cricket Wireless"),
    ("HLU*HULUPLUS", "Hulu"),
    ("HULU", "Hulu"),
    ("NETFLIX", "Netflix"),
    ("EXPRESSVPN", "ExpressVPN"),
    ("BGC MYCLUBHUB", "BGC MyClubHub"),
    ("BRGHTWHL", "Brightwheel"),
    ("AUDIBLE", "Audible"),
    ("CUBESMART", "CubeSmart"),
    ("CITY OF KINGSVIL", "City of Kingsville"),
    ("CPENERGY ENTEX", "CP Energy (Gas)"),
    ("CHAMPION ENERGY", "Champion Energy"),
    ("PROG COUNTY MUT INS", "Progressive Insurance"),
    ("PAYPAL *PADDLE", "PayPal - Paddle"),
    ("PAYPAL *MICROSOFT", "PayPal - Microsoft"),
    ("PAYPAL *KASEENSS", "PayPal - Kaseenss"),
    ("MIDTOWN PERK", "Midtown Perk"),
    ("HARREL", "Harrel's"),
    ("EDEPOSIT IN BRANCH", "Branch Deposit"),
    ("ONLINE TRANSFER FROM", "Transfer - Inbound"),
    ("ONLINE TRANSFER TO", "Transfer - Outbound"),
    ("MONEY TRANSFER", "Money Transfer"),
    ("APPLE CASH SENT", "Apple Cash"),
]


def normalize_merchant(desc: str) -> str:
    upper = desc.upper()
    for key, display in MERCHANT_MAP:
        if key in upper:
            return display
    # Generic extraction: take first meaningful words
    words = re.sub(r"\b(PURCHASE AUTHORIZED ON \d{2}/\d{2}|RECURRING PAYMENT AUTHORIZED ON \d{2}/\d{2}|ON \d{2}/\d{2}/\d{2}|REF #\S+|CARD \d+|ACH.*|P\d{15}|S\d{15})\b", "", desc)
    words = re.sub(r"\s+", " ", words).strip()
    parts = words.split()
    return " ".join(parts[:4]) if parts else desc[:40]


def classify(desc: str, amount: float) -> str:
    upper = desc.upper()
    for kw in MORTGAGE_KEYWORDS:
        if kw in upper:
            return "mortgage"
    for kw in TRANSFER_KEYWORDS:
        if kw in upper:
            return "transfer"
    for kw in TRANSFER_EXTRA_KEYWORDS:
        if kw in upper:
            return "transfer"
    for kw in RECURRING_KEYWORDS:
        if kw in upper:
            return "recurring"
    for v in RECURRING_VENDORS:
        if v in upper:
            return "recurring"
    if amount > 0:
        for kw in DEPOSIT_KEYWORDS:
            if kw in upper:
                return "deposit"
        return "deposit"
    for kw in DEPOSIT_KEYWORDS:
        if kw in upper:
            return "deposit"
    return "expense"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def parse_date_value(raw: str) -> str:
    value = (raw or "").strip().strip('"')
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {raw}")


def parse_money_value(raw: str) -> float:
    text = (raw or "").strip().strip('"').replace(",", "")
    if not text:
        return 0.0
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    return float(text)


def find_column_index(headers: list[str], choices: list[str]):
    lowered = [h.strip().lower() for h in headers]
    for i, h in enumerate(lowered):
        for c in choices:
            if c in h:
                return i
    return None


def parse_csv(filepath: str):
    """Parse statement CSVs. Supports Wells Fargo no-header and common header formats."""
    parsed_rows = []
    skipped_rows = 0

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        all_rows = [r for r in reader if any((x or "").strip() for x in r)]

    if not all_rows:
        return {"rows": [], "skipped": 0}

    first_row = [c.strip() for c in all_rows[0]]
    header_tokens = [
        "date", "amount", "description", "memo", "merchant", "debit", "credit", "withdrawal", "deposit",
    ]
    has_header = any(any(token in cell.lower() for token in header_tokens) for cell in first_row)

    if has_header:
        headers = first_row
        data_rows = all_rows[1:]
        date_idx = find_column_index(headers, ["date", "posted", "transaction date"])
        amount_idx = find_column_index(headers, ["amount"])
        debit_idx = find_column_index(headers, ["debit", "withdrawal", "outflow", "spent"])
        credit_idx = find_column_index(headers, ["credit", "deposit", "inflow"])
        desc_idx = find_column_index(headers, ["description", "memo", "name", "merchant", "details", "payee"])

        if date_idx is None or desc_idx is None or (amount_idx is None and debit_idx is None and credit_idx is None):
            return {"rows": [], "skipped": len(data_rows)}

        for row in data_rows:
            try:
                if max(date_idx, desc_idx) >= len(row):
                    skipped_rows += 1
                    continue

                date = parse_date_value(row[date_idx])
                desc = row[desc_idx].strip().strip('"')
                if not desc:
                    skipped_rows += 1
                    continue

                if amount_idx is not None and amount_idx < len(row) and (row[amount_idx] or "").strip():
                    amount = parse_money_value(row[amount_idx])
                else:
                    debit_val = parse_money_value(row[debit_idx]) if debit_idx is not None and debit_idx < len(row) else 0.0
                    credit_val = parse_money_value(row[credit_idx]) if credit_idx is not None and credit_idx < len(row) else 0.0
                    amount = (-abs(debit_val) if debit_val else 0.0) + abs(credit_val)

                merchant = normalize_merchant(desc)
                category = classify(desc, amount)
                parsed_rows.append(
                    {
                        "date": date,
                        "amount": amount,
                        "description": desc,
                        "merchant": merchant,
                        "category": category,
                    }
                )
            except (ValueError, IndexError):
                skipped_rows += 1
                continue

        return {"rows": parsed_rows, "skipped": skipped_rows}

    # Fallback: original Wells Fargo no-header format.
    for row in all_rows:
        if len(row) < 5:
            skipped_rows += 1
            continue
        try:
            date_str = row[0].strip().strip('"')
            amount_str = row[1].strip().strip('"')
            desc = row[4].strip().strip('"')
            date = parse_date_value(date_str)
            amount = parse_money_value(amount_str)
            merchant = normalize_merchant(desc)
            category = classify(desc, amount)
            parsed_rows.append(
                {
                    "date": date,
                    "amount": amount,
                    "description": desc,
                    "merchant": merchant,
                    "category": category,
                }
            )
        except (ValueError, IndexError):
            skipped_rows += 1
            continue

    return {"rows": parsed_rows, "skipped": skipped_rows}


def import_csv(filepath: str, filename: str) -> dict:
    parsed = parse_csv(filepath)
    rows = parsed["rows"]
    inserted = 0
    duplicates = 0
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO csv_imports (filename, imported_at) VALUES (?, ?)",
            (filename, datetime.now().isoformat()),
        )
        import_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for r in rows:
            exists = conn.execute(
                "SELECT 1 FROM transactions WHERE date=? AND amount=? AND description=?",
                (r["date"], r["amount"], r["description"]),
            ).fetchone()
            is_duplicate = 1 if exists else 0
            conn.execute(
                "INSERT INTO import_rows (import_id, date, amount, description, merchant, category, is_duplicate) VALUES (?,?,?,?,?,?,?)",
                (import_id, r["date"], r["amount"], r["description"], r["merchant"], r["category"], is_duplicate),
            )
            if exists:
                duplicates += 1
                continue
            conn.execute(
                "INSERT INTO transactions (import_id, date, amount, description, merchant, category) VALUES (?,?,?,?,?,?)",
                (import_id, r["date"], r["amount"], r["description"], r["merchant"], r["category"]),
            )
            inserted += 1
        conn.commit()
    return {
        "import_id": import_id,
        "inserted": inserted,
        "duplicates": duplicates,
        "total": len(rows),
        "skipped": parsed["skipped"],
    }


def merchant_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def slug_to_merchant(slug: str):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT merchant FROM transactions
            UNION
            SELECT DISTINCT merchant FROM manual_entries
        """).fetchall()
        for r in rows:
            if merchant_slug(r["merchant"]) == slug:
                return r["merchant"]
    return None


def sum_category(conn, category: str, month: str = None) -> float:
    if month:
        tx = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE category=? AND strftime('%Y-%m', date)=?",
            (category, month),
        ).fetchone()["s"]
        me = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM manual_entries WHERE category=? AND strftime('%Y-%m', date)=?",
            (category, month),
        ).fetchone()["s"]
    else:
        tx = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE category=?",
            (category,),
        ).fetchone()["s"]
        me = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM manual_entries WHERE category=?",
            (category,),
        ).fetchone()["s"]
    return round((tx or 0) + (me or 0), 2)


def get_expense_totals(conn, month: str = None) -> dict:
    recurring = round(abs(sum_category(conn, "recurring", month)), 2)
    mortgage = round(abs(sum_category(conn, "mortgage", month)), 2)
    expenses = round(abs(sum_category(conn, "expense", month)), 2)
    monthly_expenses_total = round(recurring + mortgage + expenses, 2)
    return {
        "recurring": recurring,
        "mortgage": mortgage,
        "expenses": expenses,
        "monthly_expenses_total": monthly_expenses_total,
    }


def get_expense_totals_from_import_rows(conn, import_id: int, month: str = None) -> dict:
    where_parts = ["import_id=?", "category IN ('recurring','mortgage','expense')"]
    params = [import_id]
    if month:
        where_parts.append("strftime('%Y-%m', date)=?")
        params.append(month)

    rows = conn.execute(
        f"SELECT category, SUM(ABS(amount)) as total FROM import_rows WHERE {' AND '.join(where_parts)} GROUP BY category",
        params,
    ).fetchall()

    result = {"recurring": 0.0, "mortgage": 0.0, "expense": 0.0}
    for r in rows:
        result[r["category"]] = round(float(r["total"] or 0), 2)

    return {
        "recurring": result["recurring"],
        "mortgage": result["mortgage"],
        "expenses": result["expense"],
        "monthly_expenses_total": round(result["recurring"] + result["mortgage"] + result["expense"], 2),
    }


def get_latest_data_month(conn):
    row = conn.execute(
        """
        SELECT MAX(m) as m FROM (
            SELECT strftime('%Y-%m', date) as m FROM transactions
            UNION
            SELECT strftime('%Y-%m', date) as m FROM manual_entries
            UNION
            SELECT strftime('%Y-%m', date) as m FROM import_rows
        )
        WHERE m IS NOT NULL
        """
    ).fetchone()
    return row["m"] if row else None


def is_transfer_like_text(text: str) -> bool:
    upper = (text or "").upper()
    for kw in TRANSFER_KEYWORDS + TRANSFER_EXTRA_KEYWORDS:
        if kw in upper:
            return True
    return False


def sum_expense_excluding_transfers(conn, month: str = None, import_id: int = None) -> float:
    tx_where = ["category='expense'"]
    tx_params = []
    if month:
        tx_where.append("strftime('%Y-%m', date)=?")
        tx_params.append(month)
    if import_id is not None:
        tx_where.append("import_id=?")
        tx_params.append(import_id)

    me_where = ["category='expense'"]
    me_params = []
    if month:
        me_where.append("strftime('%Y-%m', date)=?")
        me_params.append(month)

    tx_rows = conn.execute(
        f"SELECT amount, description FROM transactions WHERE {' AND '.join(tx_where)}",
        tx_params,
    ).fetchall()
    me_rows = conn.execute(
        f"SELECT amount, notes as description FROM manual_entries WHERE {' AND '.join(me_where)}",
        me_params,
    ).fetchall()

    total = 0.0
    for r in tx_rows:
        if not is_transfer_like_text(r["description"]):
            total += abs(r["amount"])
    for r in me_rows:
        if not is_transfer_like_text(r["description"]):
            total += abs(r["amount"])
    return round(total, 2)


def calculate_monthly_budget_breakdown(conn) -> dict:
    """Sum each recurring/mortgage merchant's most recent monthly total by category."""
    rec_rows = conn.execute(
        """
        SELECT merchant, category, strftime('%Y-%m', date) as month, SUM(amount) as total
        FROM transactions WHERE category IN ('recurring','mortgage')
        GROUP BY merchant, category, month
        UNION ALL
        SELECT merchant, category, strftime('%Y-%m', date) as month, SUM(amount) as total
        FROM manual_entries WHERE category IN ('recurring','mortgage')
        GROUP BY merchant, category, month
        ORDER BY merchant, month
        """
    ).fetchall()
    merchant_latest = {}
    for r in rec_rows:
        merchant = r["merchant"]
        if merchant not in merchant_latest or r["month"] > merchant_latest[merchant]["month"]:
            merchant_latest[merchant] = {
                "month": r["month"],
                "recurring": 0.0,
                "mortgage": 0.0,
            }
            merchant_latest[merchant][r["category"]] = abs(r["total"])
        elif r["month"] == merchant_latest[merchant]["month"]:
            merchant_latest[merchant][r["category"]] += abs(r["total"])

    recurring = round(sum(v["recurring"] for v in merchant_latest.values()), 2)
    mortgage = round(sum(v["mortgage"] for v in merchant_latest.values()), 2)
    return {
        "recurring": recurring,
        "mortgage": mortgage,
        "total": round(recurring + mortgage, 2),
    }


def calculate_monthly_expenses_avg(conn) -> float:
    return calculate_monthly_budget_breakdown(conn)["total"]


def get_actual_spend_by_category(conn, month: str) -> dict:
    rows = conn.execute(
        """
        SELECT category, SUM(ABS(amount)) as total
        FROM (
            SELECT date, category, amount FROM transactions
            UNION ALL
            SELECT date, category, amount FROM manual_entries
        )
        WHERE amount < 0
          AND strftime('%Y-%m', date) = ?
          AND category IN ('mortgage', 'recurring', 'expense', 'transfer')
        GROUP BY category
        """,
        (month,),
    ).fetchall()
    values = {cat: 0.0 for cat in BUDGET_CATEGORIES}
    for r in rows:
        values[r["category"]] = round(float(r["total"] or 0), 2)
    return values


def get_budget_by_category(conn, month: str) -> dict:
    rows = conn.execute(
        """
        SELECT category, amount
        FROM monthly_budgets
        WHERE month = ?
        """,
        (month,),
    ).fetchall()
    values = {cat: 0.0 for cat in BUDGET_CATEGORIES}
    for r in rows:
        values[r["category"]] = round(float(r["amount"] or 0), 2)
    return values


def calculate_buckets(
    current_balance,
    monthly_leftover,
    buffer_goal=1000,
    sinking_pct=0.15,
    growth_pct=0.10,
    fun_pct=0.75,
):
    if monthly_leftover <= 0:
        return {
            "buffer": 0.0,
            "sinking": 0.0,
            "growth": 0.0,
            "fun": 0.0,
        }
    buffer_amt = min(monthly_leftover, max(0, buffer_goal - current_balance))
    remaining = max(monthly_leftover - buffer_amt, 0)
    return {
        "buffer": round(buffer_amt, 2),
        "sinking": round(remaining * sinking_pct, 2),
        "growth": round(remaining * growth_pct, 2),
        "fun": round(remaining * fun_pct, 2),
    }


def validate_percentage_set(name: str, pct_values: list[float]):
    total = round(sum(pct_values), 6)
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"{name} percentages must total 100. Current total: {total}")


def compute_income_plan(payload: dict, conn) -> dict:
    income_1 = float(payload.get("income_1", 0))
    income_2 = float(payload.get("income_2", 0))
    if income_1 < 0 or income_2 < 0:
        raise ValueError("Income values must be zero or greater")

    # Bills split is fixed at 60/40 by requirement.
    split_pct_1 = 60.0
    split_pct_2 = 40.0

    sinking_pct = float(payload.get("sinking_pct", 15))
    growth_pct = float(payload.get("growth_pct", 10))
    fun_pct = float(payload.get("fun_pct", 75))
    validate_percentage_set("Bucket", [sinking_pct, growth_pct, fun_pct])

    buffer_goal = float(payload.get("buffer_goal", 1000))
    balance_1 = float(payload.get("current_balance_1", 0))
    balance_2 = float(payload.get("current_balance_2", 0))
    if balance_1 < 0 or balance_2 < 0:
        raise ValueError("Current balance values must be zero or greater")

    # Account balance is derived from both person balances by requirement.
    bills_account_balance = round(balance_1 + balance_2, 2)
    run_month = payload.get("run_month") or None  # e.g. "2026-05"
    budget = calculate_monthly_budget_breakdown(conn)
    monthly_expenses_total = budget["total"]

    contribution_1 = round(monthly_expenses_total * (split_pct_1 / 100.0), 2)
    contribution_2 = round(monthly_expenses_total * (split_pct_2 / 100.0), 2)

    # Reduce what each person needs to add if there is already money in the bills account.
    amount_due_after_balance = round(max(monthly_expenses_total - bills_account_balance, 0), 2)
    adjusted_contribution_1 = round(amount_due_after_balance * (split_pct_1 / 100.0), 2)
    adjusted_contribution_2 = round(amount_due_after_balance * (split_pct_2 / 100.0), 2)

    # Leftover should be based on each person's required bill amount after using current bills account balance.
    leftover_1 = round(income_1 - adjusted_contribution_1, 2)
    leftover_2 = round(income_2 - adjusted_contribution_2, 2)

    buckets_1 = calculate_buckets(
        balance_1,
        leftover_1,
        buffer_goal=buffer_goal,
        sinking_pct=sinking_pct / 100.0,
        growth_pct=growth_pct / 100.0,
        fun_pct=fun_pct / 100.0,
    )
    buckets_2 = calculate_buckets(
        balance_2,
        leftover_2,
        buffer_goal=buffer_goal,
        sinking_pct=sinking_pct / 100.0,
        growth_pct=growth_pct / 100.0,
        fun_pct=fun_pct / 100.0,
    )

    return {
        "inputs": {
            "income_1": round(income_1, 2),
            "income_2": round(income_2, 2),
            "current_balance_1": round(balance_1, 2),
            "current_balance_2": round(balance_2, 2),
            "buffer_goal": round(buffer_goal, 2),
            "bills_account_balance": round(bills_account_balance, 2),
            "run_month_requested": run_month,
            "run_month_used": run_month,
            "budget_basis": "latest_recurring_and_mortgage",
            "split_pct_1": round(split_pct_1, 2),
            "split_pct_2": round(split_pct_2, 2),
            "sinking_pct": round(sinking_pct, 2),
            "growth_pct": round(growth_pct, 2),
            "fun_pct": round(fun_pct, 2),
        },
        "monthly_expenses": {
            "recurring": budget["recurring"],
            "mortgage": budget["mortgage"],
            "expense": 0.0,
            "total": monthly_expenses_total,
        },
        "bills_split": {
            "contribution_1": contribution_1,
            "contribution_2": contribution_2,
        },
        "adjusted_bills_split": {
            "amount_due_after_balance": amount_due_after_balance,
            "contribution_1": adjusted_contribution_1,
            "contribution_2": adjusted_contribution_2,
        },
        "leftover": {
            "person_1": leftover_1,
            "person_2": leftover_2,
        },
        "buckets": {
            "person_1": buckets_1,
            "person_2": buckets_2,
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("csvfile")
    if not f or not f.filename:
        return jsonify({"error": "No file provided"}), 400
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a CSV statement file"}), 400
    filepath = os.path.join(BASE_DIR, "uploads_tmp.csv")
    f.save(filepath)
    result = import_csv(filepath, f.filename)
    os.remove(filepath)
    if result["total"] == 0:
        return jsonify({
            "error": "No valid transactions found in this file. Use a CSV with Date + Amount (or Debit/Credit) + Description columns.",
            "skipped": result.get("skipped", 0),
        }), 400
    return jsonify(result)


@app.route("/upload/result/<int:import_id>")
def upload_result(import_id):
    return render_template("upload_result.html", import_id=import_id)


@app.route("/api/import/<int:import_id>/rows")
def api_import_rows(import_id):
    with get_conn() as conn:
        info = conn.execute(
            "SELECT id, filename, imported_at FROM csv_imports WHERE id=?",
            (import_id,),
        ).fetchone()
        if not info:
            return jsonify({"error": "Upload not found"}), 404

        rows = conn.execute(
            """
            SELECT id, date, amount, description, merchant, category, is_duplicate
            FROM import_rows
            WHERE import_id=?
            ORDER BY date DESC, ABS(amount) DESC, merchant ASC
            """,
            (import_id,),
        ).fetchall()

        # Backward compatibility for old imports created before import_rows existed.
        if not rows:
            rows = conn.execute(
                """
                SELECT id, date, amount, description, merchant, category, 0 as is_duplicate
                FROM transactions
                WHERE import_id=?
                ORDER BY date DESC, ABS(amount) DESC, merchant ASC
                """,
                (import_id,),
            ).fetchall()

    payload_rows = [dict(r) for r in rows]
    by_category = {"mortgage": 0.0, "recurring": 0.0, "expense": 0.0, "transfer": 0.0, "deposit": 0.0}
    by_merchant = {}
    for r in payload_rows:
        cat = r["category"]
        by_category[cat] = round(by_category.get(cat, 0.0) + abs(r["amount"]), 2)
        m = r["merchant"]
        by_merchant[m] = round(by_merchant.get(m, 0.0) + abs(r["amount"]), 2)

    top_merchants = sorted(
        [{"merchant": k, "total": v} for k, v in by_merchant.items()],
        key=lambda x: x["total"],
        reverse=True,
    )[:12]

    return jsonify(
        {
            "import": dict(info),
            "totals": {
                "count": len(payload_rows),
                "duplicates": sum(1 for r in payload_rows if r.get("is_duplicate")),
                "categories": by_category,
                "net": round(sum(r["amount"] for r in payload_rows), 2),
            },
            "top_merchants": top_merchants,
            "rows": payload_rows,
        }
    )


@app.route("/api/summary")
def api_summary():
    with get_conn() as conn:
        recurring = round(abs(sum_category(conn, "recurring")), 2)
        mortgage = round(abs(sum_category(conn, "mortgage")), 2)

        latest_import = conn.execute(
            "SELECT id FROM csv_imports ORDER BY imported_at DESC, id DESC LIMIT 1"
        ).fetchone()
        latest_import_id = latest_import["id"] if latest_import else None

        expenses = sum_expense_excluding_transfers(conn, import_id=latest_import_id)
        expenses_all_time_ex_transfer = sum_expense_excluding_transfers(conn)
        monthly_expenses_total = round(recurring + mortgage + expenses, 2)

        monthly_expenses_avg = calculate_monthly_expenses_avg(conn)

        # Expense paid YTD = all recurring+mortgage expenses for the current year
        current_year = datetime.now().strftime("%Y")
        ytd_tx = round(abs(conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE category IN ('recurring','mortgage') AND strftime('%Y', date)=?",
            (current_year,)
        ).fetchone()["s"]), 2)
        ytd_me = round(abs(conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM manual_entries WHERE category IN ('recurring','mortgage') AND strftime('%Y', date)=?",
            (current_year,)
        ).fetchone()["s"]), 2)
        expense_paid_ytd = round(ytd_tx + ytd_me, 2)

        # Total income = sum of income_1 + income_2 from savings history entries
        total_income = round(conn.execute(
            "SELECT COALESCE(SUM(income_1 + income_2), 0) as s FROM savings_history"
        ).fetchone()["s"], 2)

        net = round(
            conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions").fetchone()["s"]
            + conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM manual_entries").fetchone()["s"],
            2
        )

        imports = conn.execute("SELECT id, filename, imported_at FROM csv_imports ORDER BY imported_at DESC").fetchall()

    return jsonify({
        "recurring": recurring,
        "mortgage": mortgage,
        "expenses": expenses,
        "expenses_all_time_ex_transfer": expenses_all_time_ex_transfer,
        "expenses_scope": "latest_upload_ex_transfer",
        "monthly_expenses_avg": monthly_expenses_avg,
        "total_income": total_income,
        "expense_paid_ytd": expense_paid_ytd,
        "net": net,
        "imports": [dict(i) for i in imports],
    })


@app.route("/api/income/calculate", methods=["POST"])
def api_income_calculate():
    payload = request.get_json(force=True)
    with get_conn() as conn:
        try:
            result = compute_income_plan(payload, conn)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    return jsonify(result)


@app.route("/api/income/save", methods=["POST"])
def api_income_save():
    payload = request.get_json(force=True)
    notes = payload.get("notes", "")
    run_month = payload.get("run_month") or datetime.now().strftime("%Y-%m")
    with get_conn() as conn:
        try:
            result = compute_income_plan(payload, conn)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        conn.execute(
            """
            INSERT INTO savings_history (
                run_date, run_month, income_1, income_2,
                monthly_expenses_total, recurring_total, mortgage_total, expense_total,
                split_pct_1, split_pct_2, contribution_1, contribution_2,
                leftover_1, leftover_2, current_balance_1, current_balance_2,
                buffer_goal, sinking_pct, growth_pct, fun_pct,
                buffer_1, sinking_1, growth_1, fun_1,
                buffer_2, sinking_2, growth_2, fun_2,
                notes, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d"),
                run_month,
                result["inputs"]["income_1"],
                result["inputs"]["income_2"],
                result["monthly_expenses"]["total"],
                result["monthly_expenses"]["recurring"],
                result["monthly_expenses"]["mortgage"],
                result["monthly_expenses"]["expense"],
                result["inputs"]["split_pct_1"],
                result["inputs"]["split_pct_2"],
                result["bills_split"]["contribution_1"],
                result["bills_split"]["contribution_2"],
                result["leftover"]["person_1"],
                result["leftover"]["person_2"],
                result["inputs"]["current_balance_1"],
                result["inputs"]["current_balance_2"],
                result["inputs"]["buffer_goal"],
                result["inputs"]["sinking_pct"],
                result["inputs"]["growth_pct"],
                result["inputs"]["fun_pct"],
                result["buckets"]["person_1"]["buffer"],
                result["buckets"]["person_1"]["sinking"],
                result["buckets"]["person_1"]["growth"],
                result["buckets"]["person_1"]["fun"],
                result["buckets"]["person_2"]["buffer"],
                result["buckets"]["person_2"]["sinking"],
                result["buckets"]["person_2"]["growth"],
                result["buckets"]["person_2"]["fun"],
                notes,
                datetime.now().isoformat(),
            ),
        )
        row_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        conn.commit()
    return jsonify({"ok": True, "id": row_id, "result": result})


@app.route("/api/savings/history")
def api_savings_history():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM savings_history ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/savings/pie")
def api_savings_pie():
    history_id = request.args.get("id")
    with get_conn() as conn:
        if history_id:
            row = conn.execute(
                "SELECT * FROM savings_history WHERE id=?",
                (history_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM savings_history ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()

    if not row:
        return jsonify({"error": "No savings history found"}), 404

    labels = [
        "Bills Account",
        "P1 Buffer",
        "P1 Sinking",
        "P1 Growth",
        "P1 Fun",
        "P2 Buffer",
        "P2 Sinking",
        "P2 Growth",
        "P2 Fun",
    ]
    values = [
        row["monthly_expenses_total"],
        row["buffer_1"],
        row["sinking_1"],
        row["growth_1"],
        row["fun_1"],
        row["buffer_2"],
        row["sinking_2"],
        row["growth_2"],
        row["fun_2"],
    ]

    filtered = [(l, v) for l, v in zip(labels, values) if v > 0]
    if not filtered:
        filtered = [("No Allocation", 1)]

    labels, values = zip(*filtered)
    colors = [
        "#00E5FF",
        "#00FF41",
        "#FFB300",
        "#CC66FF",
        "#7FFF00",
        "#00FF88",
        "#FFD54F",
        "#B388FF",
        "#69F0AE",
    ][: len(labels)]

    fig, ax = plt.subplots(figsize=(7, 7), facecolor="#0a0a0a")
    ax.set_facecolor("#0a0a0a")
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        startangle=120,
        textprops={"color": "#00FF41", "fontsize": 9},
    )
    ax.set_title(
        f"Savings Distribution ({row['run_month']})",
        color="#00FF41",
        fontsize=13,
    )
    for t in autotexts:
        t.set_color("#0a0a0a")

    image = io.BytesIO()
    fig.savefig(image, format="png", dpi=140, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    image.seek(0)
    return Response(image.getvalue(), mimetype="image/png")


@app.route("/api/transactions")
def api_transactions():
    category = request.args.get("category", "")
    month = request.args.get("month", "")
    with get_conn() as conn:
        where_parts = []
        params = []
        if category:
            where_parts.append("category=?")
            params.append(category)
        if month:
            where_parts.append("strftime('%Y-%m', date)=?")
            params.append(month)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        tx = conn.execute(
            f"SELECT id, date, amount, description, merchant, category, 'imported' as source FROM transactions {where} ORDER BY date DESC",
            params,
        ).fetchall()
        me = conn.execute(
            f"SELECT id, date, amount, merchant, category, entry_type as source, notes as description FROM manual_entries {where} ORDER BY date DESC",
            params,
        ).fetchall()

    rows = [dict(r) for r in tx] + [dict(r) for r in me]
    rows.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(rows)


@app.route("/api/recurring")
def api_recurring():
    with get_conn() as conn:
        latest_import = conn.execute(
            "SELECT id FROM csv_imports ORDER BY imported_at DESC, id DESC LIMIT 1"
        ).fetchone()
        latest_upload_amounts = {}
        if latest_import:
            uploaded_rows = conn.execute(
                """
                SELECT merchant, SUM(ABS(amount)) as total
                FROM transactions
                WHERE import_id=? AND category IN ('recurring','mortgage')
                GROUP BY merchant
                """,
                (latest_import["id"],),
            ).fetchall()
            latest_upload_amounts = {r["merchant"]: round(r["total"], 2) for r in uploaded_rows}

        rows = conn.execute("""
            SELECT merchant,
                   strftime('%Y-%m', date) as month,
                   SUM(amount) as total,
                   COUNT(*) as count
            FROM transactions
            WHERE category IN ('recurring','mortgage')
            GROUP BY merchant, month
            UNION ALL
            SELECT merchant,
                   strftime('%Y-%m', date) as month,
                   SUM(amount) as total,
                   COUNT(*) as count
            FROM manual_entries
            WHERE category IN ('recurring','mortgage')
            GROUP BY merchant, month
            ORDER BY merchant, month
        """).fetchall()

    data = {}
    for r in rows:
        m = r["merchant"]
        mo = r["month"]
        if m not in data:
            data[m] = {}
        if mo not in data[m]:
            data[m][mo] = {"total": 0, "count": 0}
        data[m][mo]["total"] += abs(r["total"])
        data[m][mo]["count"] += r["count"]

    result = []
    for merchant, months in data.items():
        sorted_months = sorted(months.keys())
        amounts = [months[m]["total"] for m in sorted_months]
        avg = round(sum(amounts) / len(amounts), 2) if amounts else 0
        last = latest_upload_amounts.get(merchant, amounts[-1] if amounts else 0)
        trend = "→"
        if len(amounts) >= 2:
            diff_pct = (amounts[-1] - amounts[-2]) / max(amounts[-2], 0.01) * 100
            if diff_pct > 5:
                trend = "↑"
            elif diff_pct < -5:
                trend = "↓"
        result.append({
            "merchant": merchant,
            "slug": merchant_slug(merchant),
            "avg": avg,
            "last": last,
            "trend": trend,
            "months": sorted_months,
            "amounts": amounts,
        })
    result.sort(key=lambda x: x["merchant"])
    return jsonify(result)


@app.route("/api/recurring/<slug>/entries")
def api_recurring_entries(slug):
    merchant = slug_to_merchant(slug)
    if not merchant:
        return jsonify({"error": "Not found"}), 404

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, date, amount, merchant, category, description, 'imported' as source
            FROM transactions
            WHERE merchant=? AND category IN ('recurring','mortgage')
            UNION ALL
            SELECT id, date, amount, merchant, category, notes as description, 'manual' as source
            FROM manual_entries
            WHERE merchant=? AND category IN ('recurring','mortgage')
            ORDER BY date DESC
        """, (merchant, merchant)).fetchall()

    return jsonify({
        "merchant": merchant,
        "entries": [dict(r) for r in rows],
    })


@app.route("/api/entry/<source>/<int:entry_id>", methods=["PATCH"])
def api_entry_update(source, entry_id):
    if source not in ("imported", "manual"):
        return jsonify({"error": "Invalid source"}), 400

    data = request.get_json(force=True)
    required = ["date", "amount", "merchant", "category"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    if data["category"] not in ("recurring", "mortgage"):
        return jsonify({"error": "Category must be recurring or mortgage"}), 400

    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
        amount = float(data["amount"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    merchant = str(data["merchant"]).strip()
    if not merchant:
        return jsonify({"error": "Merchant is required"}), 400

    description = str(data.get("description", "") or "").strip()

    with get_conn() as conn:
        if source == "imported":
            row = conn.execute(
                "SELECT description FROM transactions WHERE id=?",
                (entry_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "Entry not found"}), 404

            conn.execute(
                """
                UPDATE transactions
                SET date=?, amount=?, merchant=?, category=?, description=?
                WHERE id=?
                """,
                (
                    data["date"],
                    amount,
                    merchant,
                    data["category"],
                    description if description else row["description"],
                    entry_id,
                ),
            )
        else:
            row = conn.execute(
                "SELECT entry_type, notes FROM manual_entries WHERE id=?",
                (entry_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "Entry not found"}), 404

            conn.execute(
                """
                UPDATE manual_entries
                SET date=?, amount=?, merchant=?, category=?, notes=?, entry_type=?
                WHERE id=?
                """,
                (
                    data["date"],
                    amount,
                    merchant,
                    data["category"],
                    description if description else row["notes"],
                    data.get("entry_type", row["entry_type"]),
                    entry_id,
                ),
            )
        conn.commit()

    return jsonify({"ok": True})


@app.route("/api/trends/<slug>")
def api_trends(slug):
    merchant = slug_to_merchant(slug)
    if not merchant:
        return jsonify({"error": "Not found"}), 404
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM transactions
            WHERE merchant=?
            GROUP BY month
            ORDER BY month
        """, (merchant,)).fetchall()
    months = [r["month"] for r in rows]
    amounts = [round(abs(r["total"]), 2) for r in rows]
    return jsonify({"merchant": merchant, "months": months, "amounts": amounts})


@app.route("/api/transfers")
def api_transfers():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT date, amount, description, merchant,
                   strftime('%Y-%m', date) as month
            FROM transactions
            WHERE category='transfer'
            ORDER BY date DESC
        """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/mortgage")
def api_mortgage():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT date, amount, description, merchant,
                   strftime('%Y-%m', date) as month
            FROM transactions
            WHERE category='mortgage'
            ORDER BY date ASC
        """).fetchall()
    months_data = {}
    for r in rows:
        m = r["month"]
        if m not in months_data:
            months_data[m] = 0.0
        months_data[m] += abs(r["amount"])
    sorted_months = sorted(months_data.keys())
    return jsonify({
        "transactions": [dict(r) for r in rows],
        "months": sorted_months,
        "amounts": [round(months_data[m], 2) for m in sorted_months],
    })


@app.route("/api/manual", methods=["POST"])
def api_manual():
    data = request.get_json(force=True)
    required = ["date", "amount", "merchant", "category", "entry_type"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing field: {field}"}), 400
    try:
        amount = float(data["amount"])
        datetime.strptime(data["date"], "%Y-%m-%d")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO manual_entries (date, amount, merchant, category, entry_type, notes) VALUES (?,?,?,?,?,?)",
            (data["date"], amount, data["merchant"], data["category"], data["entry_type"], data.get("notes", "")),
        )
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/manual/<int:entry_id>", methods=["DELETE"])
def api_manual_delete(entry_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM manual_entries WHERE id=?", (entry_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/monthly_breakdown")
def api_monthly_breakdown():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', date) as month, category, SUM(ABS(amount)) as total
            FROM transactions
            WHERE amount < 0
            GROUP BY month, category
            ORDER BY month
        """).fetchall()
    result = {}
    for r in rows:
        if r["month"] not in result:
            result[r["month"]] = {}
        result[r["month"]][r["category"]] = round(r["total"], 2)
    months = sorted(result.keys())
    categories = ["mortgage", "recurring", "transfer", "expense"]
    return jsonify({
        "months": months,
        "categories": categories,
        "data": {cat: [result.get(m, {}).get(cat, 0) for m in months] for cat in categories},
    })


@app.route("/expense/<slug>")
def expense_detail(slug):
    merchant = slug_to_merchant(slug)
    if not merchant:
        return "Merchant not found", 404
    return render_template("expense.html", merchant=merchant, slug=slug)


@app.route("/api/expense/<slug>")
def api_expense(slug):
    merchant = slug_to_merchant(slug)
    if not merchant:
        return jsonify({"error": "Not found"}), 404
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT date, amount, description, category,
                   strftime('%Y-%m', date) as month
            FROM transactions
            WHERE merchant=?
            ORDER BY date DESC
        """, (merchant,)).fetchall()
        months_q = conn.execute("""
            SELECT strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM transactions WHERE merchant=?
            GROUP BY month ORDER BY month
        """, (merchant,)).fetchall()
    amounts_by_month = {r["month"]: abs(r["total"]) for r in months_q}
    sorted_months = sorted(amounts_by_month.keys())
    amounts_list = [round(amounts_by_month[m], 2) for m in sorted_months]
    all_amounts = amounts_list
    avg = round(sum(all_amounts) / len(all_amounts), 2) if all_amounts else 0
    mn = round(min(all_amounts), 2) if all_amounts else 0
    mx = round(max(all_amounts), 2) if all_amounts else 0
    trend = "→"
    if len(all_amounts) >= 2:
        diff_pct = (all_amounts[-1] - all_amounts[-2]) / max(all_amounts[-2], 0.01) * 100
        if diff_pct > 5:
            trend = "↑"
        elif diff_pct < -5:
            trend = "↓"
    return jsonify({
        "merchant": merchant,
        "transactions": [dict(r) for r in rows],
        "months": sorted_months,
        "amounts": amounts_list,
        "stats": {"avg": avg, "min": mn, "max": mx, "trend": trend},
    })


@app.route("/api/months")
def api_months():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT m FROM (
                SELECT strftime('%Y-%m', date) as m FROM transactions
                UNION
                SELECT strftime('%Y-%m', date) as m FROM manual_entries
                UNION
                SELECT strftime('%Y-%m', date) as m FROM import_rows
            )
            WHERE m IS NOT NULL
            ORDER BY m
            """
        ).fetchall()
    return jsonify([r["m"] for r in rows])


@app.route("/api/budget/save", methods=["POST"])
def api_budget_save():
    payload = request.get_json(force=True)
    month = str(payload.get("month", "")).strip()
    budgets = payload.get("budgets", {})
    notes = str(payload.get("notes", "")).strip()

    if not re.fullmatch(r"\d{4}-\d{2}", month):
        return jsonify({"error": "month must be in YYYY-MM format"}), 400
    if not isinstance(budgets, dict):
        return jsonify({"error": "budgets must be an object"}), 400

    now = datetime.now().isoformat()
    to_save = {}
    for cat in BUDGET_CATEGORIES:
        val = budgets.get(cat, 0)
        try:
            amount = float(val)
        except (TypeError, ValueError):
            return jsonify({"error": f"Invalid amount for category: {cat}"}), 400
        if amount < 0:
            return jsonify({"error": f"Budget cannot be negative for category: {cat}"}), 400
        to_save[cat] = round(amount, 2)

    with get_conn() as conn:
        for cat, amount in to_save.items():
            conn.execute(
                """
                INSERT INTO monthly_budgets (month, category, amount, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(month, category)
                DO UPDATE SET amount=excluded.amount, notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (month, cat, amount, notes, now, now),
            )
        conn.commit()

    return jsonify({"ok": True, "month": month, "budgets": to_save})


@app.route("/api/budget/compare")
def api_budget_compare():
    month = (request.args.get("month") or "").strip()
    with get_conn() as conn:
        if not month:
            found = conn.execute(
                """
                SELECT MAX(month) as month
                FROM (
                    SELECT strftime('%Y-%m', date) as month FROM transactions
                    UNION
                    SELECT strftime('%Y-%m', date) as month FROM manual_entries
                    UNION
                    SELECT month FROM monthly_budgets
                )
                """
            ).fetchone()
            month = (found["month"] if found else None) or datetime.now().strftime("%Y-%m")

        if not re.fullmatch(r"\d{4}-\d{2}", month):
            return jsonify({"error": "month must be in YYYY-MM format"}), 400

        budget = get_budget_by_category(conn, month)
        actual = get_actual_spend_by_category(conn, month)

    lines = []
    for cat in BUDGET_CATEGORIES:
        b = budget.get(cat, 0.0)
        a = actual.get(cat, 0.0)
        lines.append(
            {
                "category": cat,
                "budget": round(b, 2),
                "actual": round(a, 2),
                "variance": round(a - b, 2),
                "status": "over" if a > b else "under" if a < b else "on_track",
            }
        )

    return jsonify(
        {
            "month": month,
            "categories": lines,
            "totals": {
                "budget": round(sum(x["budget"] for x in lines), 2),
                "actual": round(sum(x["actual"] for x in lines), 2),
                "variance": round(sum(x["variance"] for x in lines), 2),
            },
        }
    )


@app.route("/api/budget/trends")
def api_budget_trends():
    months_limit = request.args.get("months", "12")
    try:
        months_limit = max(1, min(int(months_limit), 36))
    except ValueError:
        months_limit = 12

    with get_conn() as conn:
        month_rows = conn.execute(
            """
            SELECT month FROM (
                SELECT strftime('%Y-%m', date) as month FROM transactions
                UNION
                SELECT strftime('%Y-%m', date) as month FROM manual_entries
                UNION
                SELECT month FROM monthly_budgets
            )
            WHERE month IS NOT NULL
            ORDER BY month DESC
            LIMIT ?
            """,
            (months_limit,),
        ).fetchall()

        months = sorted([r["month"] for r in month_rows])
        budget_totals = []
        actual_totals = []
        variance_totals = []

        for month in months:
            budget = get_budget_by_category(conn, month)
            actual = get_actual_spend_by_category(conn, month)
            b_total = round(sum(budget.values()), 2)
            a_total = round(sum(actual.values()), 2)
            budget_totals.append(b_total)
            actual_totals.append(a_total)
            variance_totals.append(round(a_total - b_total, 2))

    return jsonify(
        {
            "months": months,
            "budget_totals": budget_totals,
            "actual_totals": actual_totals,
            "variance_totals": variance_totals,
        }
    )


@app.route("/api/budget/current")
def api_budget_current():
    month = (request.args.get("month") or "").strip()
    with get_conn() as conn:
        if not month:
            found = conn.execute(
                """
                SELECT MAX(month) as month
                FROM (
                    SELECT strftime('%Y-%m', date) as month FROM transactions
                    UNION
                    SELECT strftime('%Y-%m', date) as month FROM manual_entries
                )
                """
            ).fetchone()
            month = (found["month"] if found else None) or datetime.now().strftime("%Y-%m")

        if not re.fullmatch(r"\d{4}-\d{2}", month):
            return jsonify({"error": "month must be in YYYY-MM format"}), 400

        current_budget = calculate_monthly_expenses_avg(conn)
        selected_totals = get_expense_totals(conn, month)
        selected_bills_total = round(selected_totals["recurring"] + selected_totals["mortgage"], 2)

    return jsonify(
        {
            "month": month,
            "current_budget": round(current_budget, 2),
            "uploaded_statement_bills_total": selected_bills_total,
            "difference": round(selected_bills_total - current_budget, 2),
        }
    )


if __name__ == "__main__":
    init_db()
    print("Starting Dexter's Budget Tracker at http://localhost:5000")
    app.run(debug=True, port=5000)
