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

DEPOSIT_KEYWORDS = [
    "EDEPOSIT",
    "DEPOSIT",
]

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


def parse_csv(filepath: str):
    """Parse Wells Fargo CSV (no header). Returns list of dicts."""
    rows = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 5:
                continue
            try:
                date_str = row[0].strip().strip('"')
                amount_str = row[1].strip().strip('"')
                desc = row[4].strip().strip('"')
                date = datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
                amount = float(amount_str.replace(",", ""))
                merchant = normalize_merchant(desc)
                category = classify(desc, amount)
                rows.append({
                    "date": date,
                    "amount": amount,
                    "description": desc,
                    "merchant": merchant,
                    "category": category,
                })
            except (ValueError, IndexError):
                continue
    return rows


def import_csv(filepath: str, filename: str) -> dict:
    rows = parse_csv(filepath)
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
            if exists:
                duplicates += 1
                continue
            conn.execute(
                "INSERT INTO transactions (import_id, date, amount, description, merchant, category) VALUES (?,?,?,?,?,?)",
                (import_id, r["date"], r["amount"], r["description"], r["merchant"], r["category"]),
            )
            inserted += 1
        conn.commit()
    return {"inserted": inserted, "duplicates": duplicates, "total": len(rows)}


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
    run_month = payload.get("run_month") or None  # e.g. "2026-05"

    totals = get_expense_totals(conn, month=run_month)
    monthly_expenses_total = totals["monthly_expenses_total"]

    contribution_1 = round(monthly_expenses_total * (split_pct_1 / 100.0), 2)
    contribution_2 = round(monthly_expenses_total * (split_pct_2 / 100.0), 2)

    leftover_1 = round(income_1 - contribution_1, 2)
    leftover_2 = round(income_2 - contribution_2, 2)

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
            "split_pct_1": round(split_pct_1, 2),
            "split_pct_2": round(split_pct_2, 2),
            "sinking_pct": round(sinking_pct, 2),
            "growth_pct": round(growth_pct, 2),
            "fun_pct": round(fun_pct, 2),
        },
        "monthly_expenses": {
            "recurring": totals["recurring"],
            "mortgage": totals["mortgage"],
            "expense": totals["expenses"],
            "total": monthly_expenses_total,
        },
        "bills_split": {
            "contribution_1": contribution_1,
            "contribution_2": contribution_2,
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
    filepath = os.path.join(BASE_DIR, "uploads_tmp.csv")
    f.save(filepath)
    result = import_csv(filepath, f.filename)
    os.remove(filepath)
    return jsonify(result)


@app.route("/api/summary")
def api_summary():
    with get_conn() as conn:
        recurring = round(abs(sum_category(conn, "recurring")), 2)
        mortgage = round(abs(sum_category(conn, "mortgage")), 2)

        expenses = round(abs(sum_category(conn, "expense")), 2)
        monthly_expenses_total = round(recurring + mortgage + expenses, 2)

        # Monthly expenses = sum of each recurring/mortgage merchant's latest month amount
        # (matches the "SUM OF LATEST AMOUNTS" total on the recurring tab)
        rec_rows = conn.execute("""
            SELECT merchant, strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM transactions WHERE category IN ('recurring','mortgage')
            GROUP BY merchant, month
            UNION ALL
            SELECT merchant, strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM manual_entries WHERE category IN ('recurring','mortgage')
            GROUP BY merchant, month
            ORDER BY merchant, month
        """).fetchall()
        merchant_latest = {}
        for r in rec_rows:
            m = r["merchant"]
            if m not in merchant_latest or r["month"] > merchant_latest[m]["month"]:
                merchant_latest[m] = {"month": r["month"], "total": abs(r["total"])}
            elif r["month"] == merchant_latest[m]["month"]:
                merchant_latest[m]["total"] += abs(r["total"])
        monthly_expenses_avg = round(sum(v["total"] for v in merchant_latest.values()), 2)

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
        last = amounts[-1] if amounts else 0
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
        rows = conn.execute("SELECT DISTINCT strftime('%Y-%m', date) as m FROM transactions ORDER BY m").fetchall()
    return jsonify([r["m"] for r in rows])


if __name__ == "__main__":
    init_db()
    print("Starting Dexter's Budget Tracker at http://localhost:5000")
    app.run(debug=True, port=5000)
