import csv
import os
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pdfplumber

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PDF_INPUT_DIR = os.path.join(BASE_DIR, "pdf_input")
OUTPUT_DIR = os.path.join(BASE_DIR, "expense_output")

CATEGORY_KEYWORDS = {
    "Utilities": ["electric", "water", "internet", "utility", "spectrum", "at&t", "verizon", "city of"],
    "Food Expense": ["restaurant depot", "sysco", "food", "grocery", "produce", "meat"],
    "Maintenance": ["lowe", "home depot", "repair", "maintenance", "hvac", "plumb", "pest"],
    "Beer Expense": ["beer", "distributor", "beverage", "brew"],
    "Transfers": ["transfer", "zelle", "venmo", "cash app", "ach transfer"],
    "Recurring": ["netflix", "spotify", "adobe", "insurance", "subscription", "rent", "mortgage"],
}

SKIP_LINE_HINTS = [
    "beginning balance",
    "ending balance",
    "daily balance",
    "total deposits",
    "total withdrawals",
    "account number",
    "statement period",
    "page ",
]

DATE_PREFIX_RE = re.compile(r"^\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b")
AMOUNT_RE = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*\.\d{2}\)?")
FILENAME_DATE_RE = re.compile(r"(\d{4})[-_](\d{2})[-_](\d{2})")


def normalize_text(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def compact_spaced_line(value: str) -> str:
    """Collapse character-spaced PDF text into parseable tokens.

    Example: "1 / 0 2 D E P O S I T 2 . 0 2" -> "1/02 DEPOSIT 2.02"
    """
    s = (value or "").strip()
    if not s:
        return ""

    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s*,\s*", ",", s)
    s = re.sub(r"\s*\.\s*", ".", s)

    # Remove spacing between one-character tokens but keep word boundaries.
    while True:
        updated = re.sub(r"\b([A-Za-z0-9])\s+([A-Za-z0-9])\b", r"\1\2", s)
        if updated == s:
            break
        s = updated

    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_merchant(merchant: str) -> str:
    m = normalize_text(merchant)
    m = re.sub(r"\d+", "", m)
    m = re.sub(r"[^a-z\s&]", "", m)
    m = re.sub(r"\s+", " ", m).strip()
    return m


def parse_amount(raw: str) -> float:
    value = (raw or "").replace("$", "").replace(",", "").strip()
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    try:
        return float(value)
    except ValueError:
        return 0.0


def categorize(merchant_norm: str) -> str:
    for category, words in CATEGORY_KEYWORDS.items():
        if any(word in merchant_norm for word in words):
            return category
    return "Other"


def normalize_date(raw_date: str, statement_year_hint: Optional[int]) -> Tuple[str, str]:
    value = (raw_date or "").strip()
    if not value:
        return "", "unknown-month"

    fmts = ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"]

    for fmt in fmts:
        try:
            parsed = datetime.strptime(value, fmt)
            if "%y" in fmt and "%Y" not in fmt and statement_year_hint:
                parsed = parsed.replace(year=statement_year_hint)
            return parsed.strftime("%Y-%m-%d"), parsed.strftime("%Y-%m")
        except ValueError:
            continue

    md_match = re.match(r"^(\d{1,2})[/-](\d{1,2})$", value)
    if md_match and statement_year_hint:
        try:
            parsed = datetime(statement_year_hint, int(md_match.group(1)), int(md_match.group(2)))
            return parsed.strftime("%Y-%m-%d"), parsed.strftime("%Y-%m")
        except ValueError:
            pass

    return value, "unknown-month"


def statement_year_from_filename(filename: str) -> Optional[int]:
    match = FILENAME_DATE_RE.search(filename)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_transaction_line(line: str, year_hint: Optional[int]) -> Optional[Dict[str, str]]:
    raw = compact_spaced_line(line)
    if not raw:
        return None

    lowered = raw.lower()
    if any(hint in lowered for hint in SKIP_LINE_HINTS):
        return None

    date_match = DATE_PREFIX_RE.match(raw)
    if not date_match:
        return None

    date_raw = date_match.group(1)
    amount_matches = list(AMOUNT_RE.finditer(raw))
    if not amount_matches:
        return None

    # Most statement rows end with amount and often balance. Use second-to-last when two+ amounts exist.
    amount_match = amount_matches[-2] if len(amount_matches) >= 2 else amount_matches[-1]
    amount_raw = amount_match.group(0)

    desc_start = date_match.end()
    desc_end = amount_match.start()
    description = raw[desc_start:desc_end].strip(" -\t")
    description = re.sub(r"\s+", " ", description)

    if not description:
        return None

    amount = parse_amount(amount_raw)
    date_iso, month_key = normalize_date(date_raw, year_hint)

    return {
        "date_raw": date_raw,
        "date": date_iso,
        "month": month_key,
        "description": description,
        "amount": amount,
    }


def infer_section(line: str, current_section: str) -> str:
    text = compact_spaced_line(line).upper()
    if not text:
        return current_section

    if "DEPOSITS AND ADDITIONS" in text or "DEPOSITS/CREDITS" in text:
        return "DEPOSIT"
    if (
        "CHECKS AND WITHDRAWALS" in text
        or "CHECKS/DEBITS" in text
        or "CHECKS PAID" in text
        or "OTHER WITHDRAWALS" in text
        or "ELECTRONIC DEBITS" in text
        or "DEBITS" in text
    ):
        return "EXPENSE"
    if "DAILY BALANCE" in text or "SUMMARY" in text:
        return "UNKNOWN"

    return current_section


def extract_transactions_from_pdf(pdf_path: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    transactions = []
    unmatched = []
    year_hint = statement_year_from_filename(os.path.basename(pdf_path))

    with pdfplumber.open(pdf_path) as pdf:
        current_section = "UNKNOWN"
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = text.splitlines()

            for line_no, line in enumerate(lines, start=1):
                current_section = infer_section(line, current_section)
                parsed = parse_transaction_line(line, year_hint)
                if parsed:
                    amount = abs(float(parsed["amount"]))
                    if current_section == "EXPENSE":
                        parsed["amount"] = -amount
                    elif current_section == "DEPOSIT":
                        parsed["amount"] = amount

                    parsed["pdf_file"] = os.path.basename(pdf_path)
                    parsed["page"] = page_idx
                    parsed["line_no"] = line_no
                    parsed["section_hint"] = current_section
                    transactions.append(parsed)
                else:
                    if DATE_PREFIX_RE.match(compact_spaced_line(line)):
                        unmatched.append(
                            {
                                "pdf_file": os.path.basename(pdf_path),
                                "page": page_idx,
                                "line_no": line_no,
                                "line_text": compact_spaced_line(line),
                            }
                        )

    return transactions, unmatched


def copy_files_into_folder(file_paths: List[str], destination_folder: str) -> Tuple[int, int]:
    os.makedirs(destination_folder, exist_ok=True)
    copied = 0
    skipped = 0

    for src in file_paths:
        name = os.path.basename(src)
        dest = os.path.join(destination_folder, name)
        if os.path.exists(dest):
            skipped += 1
            continue
        shutil.copy2(src, dest)
        copied += 1

    return copied, skipped


def write_csv(path: str, fieldnames: List[str], rows: List[Dict[str, object]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_transaction_organizer(base_dir: str) -> Dict[str, str]:
    pdf_dir = os.path.join(base_dir, "pdf_input")
    output_dir = os.path.join(base_dir, "expense_output")
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = [
        os.path.join(pdf_dir, n)
        for n in os.listdir(pdf_dir)
        if n.lower().endswith(".pdf") and os.path.isfile(os.path.join(pdf_dir, n))
    ]

    if not pdf_files:
        raise RuntimeError(f"No PDFs found in: {pdf_dir}")

    all_transactions: List[Dict[str, object]] = []
    unmatched_lines: List[Dict[str, str]] = []

    for pdf_path in sorted(pdf_files):
        parsed, unmatched = extract_transactions_from_pdf(pdf_path)
        all_transactions.extend(parsed)
        unmatched_lines.extend(unmatched)

    if not all_transactions:
        raise RuntimeError("No transactions were parsed from the selected PDFs.")

    for tx in all_transactions:
        description = str(tx["description"])
        merchant_norm = normalize_merchant(description)
        amount = float(tx["amount"])

        tx["merchant_norm"] = merchant_norm
        tx["type"] = "DEPOSIT" if amount > 0 else "EXPENSE"
        tx["category"] = "Deposit/Income" if amount > 0 else categorize(merchant_norm)

    merchant_months = defaultdict(set)
    merchant_amounts = defaultdict(list)
    merchant_labels = defaultdict(set)

    for tx in all_transactions:
        merchant = str(tx["merchant_norm"]) or "unknown"
        month = str(tx["month"])
        amount = abs(float(tx["amount"]))
        merchant_months[merchant].add(month)
        merchant_amounts[merchant].append(amount)
        merchant_labels[merchant].add(normalize_text(str(tx["description"])))

    recurring_lookup: Dict[str, Dict[str, object]] = {}
    recurring_rows: List[Dict[str, object]] = []

    for merchant, months in merchant_months.items():
        if len(months) < 2:
            continue

        amounts = merchant_amounts[merchant]
        med = median(amounts) if amounts else 0.0
        max_dev = 0.0
        if med > 0:
            max_dev = max(abs(a - med) / med for a in amounts)

        reasons = []
        if len(merchant_labels[merchant]) > 2:
            reasons.append("name-variation")
        if max_dev > 0.20:
            reasons.append("amount-variance>20%")
        if len(months) == 2 and len(amounts) <= 2:
            reasons.append("sparse-pattern")

        row = {
            "merchant_norm": merchant,
            "months_seen": ";".join(sorted(months)),
            "count": len(amounts),
            "median_amount": round(med, 2),
            "review_flag": 1 if reasons else 0,
            "review_reasons": ";".join(reasons),
        }
        recurring_rows.append(row)
        recurring_lookup[merchant] = row

    for tx in all_transactions:
        merchant = str(tx["merchant_norm"]) or "unknown"
        recurring = merchant in recurring_lookup
        tx["is_recurring"] = 1 if recurring else 0
        tx["review_flag"] = int(recurring_lookup.get(merchant, {}).get("review_flag", 0))
        tx["review_reasons"] = recurring_lookup.get(merchant, {}).get("review_reasons", "")
        if recurring and tx["type"] == "EXPENSE":
            tx["category"] = "Recurring"

    all_out = os.path.join(output_dir, "all_transactions.csv")
    expenses_out = os.path.join(output_dir, "expenses_categorized.csv")
    deposits_out = os.path.join(output_dir, "deposits.csv")
    recurring_out = os.path.join(output_dir, "recurring_summary.csv")
    unmatched_out = os.path.join(output_dir, "unmatched_lines.csv")

    all_fields = [
        "month",
        "date",
        "date_raw",
        "description",
        "merchant_norm",
        "amount",
        "type",
        "category",
        "is_recurring",
        "review_flag",
        "review_reasons",
        "section_hint",
        "pdf_file",
        "page",
        "line_no",
    ]

    all_sorted = sorted(
        all_transactions,
        key=lambda r: (str(r.get("date", "")), str(r.get("pdf_file", "")), int(r.get("page", 0)), int(r.get("line_no", 0))),
    )

    write_csv(all_out, all_fields, all_sorted)

    expenses = [row for row in all_sorted if row.get("type") == "EXPENSE"]
    deposits = [row for row in all_sorted if row.get("type") == "DEPOSIT"]

    write_csv(expenses_out, all_fields, expenses)
    write_csv(deposits_out, all_fields, deposits)

    recurring_fields = ["merchant_norm", "months_seen", "count", "median_amount", "review_flag", "review_reasons"]
    write_csv(recurring_out, recurring_fields, sorted(recurring_rows, key=lambda r: str(r["merchant_norm"])))

    unmatched_fields = ["pdf_file", "page", "line_no", "line_text"]
    write_csv(unmatched_out, unmatched_fields, unmatched_lines)

    buckets: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for row in expenses:
        buckets[(str(row["month"]), str(row["category"]))].append(row)

    for (month, category), rows in buckets.items():
        month_dir = os.path.join(output_dir, month)
        os.makedirs(month_dir, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", category)
        out_file = os.path.join(month_dir, f"{safe_name}.csv")
        write_csv(out_file, all_fields, rows)

    return {
        "pdf_count": str(len(pdf_files)),
        "tx_count": str(len(all_transactions)),
        "expense_count": str(len(expenses)),
        "deposit_count": str(len(deposits)),
        "unmatched_count": str(len(unmatched_lines)),
        "all_out": all_out,
        "expenses_out": expenses_out,
        "deposits_out": deposits_out,
        "recurring_out": recurring_out,
        "unmatched_out": unmatched_out,
        "output_dir": output_dir,
    }


class TransactionOrganizerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDF Transaction Organizer")
        self.root.geometry("980x700")

        self.base_dir_var = tk.StringVar(value=BASE_DIR)

        self._build_ui()
        self.log("Ready. Import PDFs and run transaction organization.")
        self.refresh_status()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        row = ttk.Frame(main)
        row.pack(fill="x")

        ttk.Label(row, text="Working Folder:").pack(side="left")
        ttk.Entry(row, textvariable=self.base_dir_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Browse", command=self.choose_working_folder).pack(side="left")

        status_row = ttk.Frame(main)
        status_row.pack(fill="x", pady=(10, 8))

        self.status_label = ttk.Label(status_row, text="")
        self.status_label.pack(side="left")
        ttk.Button(status_row, text="Refresh", command=self.refresh_status).pack(side="right")

        action_box = ttk.LabelFrame(main, text="Actions", padding=10)
        action_box.pack(fill="x")

        ttk.Button(action_box, text="Import PDFs", command=self.import_pdfs).pack(side="left")
        ttk.Button(action_box, text="Run Transaction Organizer", command=self.run_organizer).pack(side="left", padx=8)
        ttk.Button(action_box, text="Open Output Folder", command=self.open_output_folder).pack(side="left")

        log_box = ttk.LabelFrame(main, text="Activity Log", padding=8)
        log_box.pack(fill="both", expand=True, pady=(10, 0))

        self.log_text = tk.Text(log_box, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")

    def current_base(self) -> str:
        base = self.base_dir_var.get().strip()
        if not base:
            raise RuntimeError("Working folder is empty.")
        os.makedirs(base, exist_ok=True)
        return os.path.abspath(base)

    def choose_working_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.base_dir_var.get() or BASE_DIR)
        if not chosen:
            return
        self.base_dir_var.set(chosen)
        self.log(f"Working folder set: {chosen}")
        self.refresh_status()

    def refresh_status(self) -> None:
        try:
            base = self.current_base()
            pdf_dir = os.path.join(base, "pdf_input")
            out_dir = os.path.join(base, "expense_output")
            pdf_count = 0
            if os.path.exists(pdf_dir):
                pdf_count = len([n for n in os.listdir(pdf_dir) if n.lower().endswith(".pdf")])
            self.status_label.configure(text=f"PDFs in pdf_input: {pdf_count} | Output: {out_dir}")
        except Exception as exc:
            self.status_label.configure(text=f"Status error: {exc}")

    def import_pdfs(self) -> None:
        try:
            base = self.current_base()
            pdf_dir = os.path.join(base, "pdf_input")
            selected = filedialog.askopenfilenames(
                title="Select PDF statements",
                filetypes=[("PDF files", "*.pdf")],
            )
            if not selected:
                return
            copied, skipped = copy_files_into_folder(list(selected), pdf_dir)
            self.log(f"Imported PDFs: copied {copied}, skipped {skipped} duplicates.")
            self.refresh_status()
        except Exception as exc:
            messagebox.showerror("Import PDFs", str(exc))

    def run_organizer(self) -> None:
        try:
            base = self.current_base()
            result = run_transaction_organizer(base)
            self.log("Transaction organization completed.")
            self.log(f"PDF files processed: {result['pdf_count']}")
            self.log(f"Transactions parsed: {result['tx_count']}")
            self.log(f"Expenses: {result['expense_count']} | Deposits: {result['deposit_count']}")
            self.log(f"Unmatched lines for review: {result['unmatched_count']}")
            self.log(f"All transactions: {result['all_out']}")
            self.log(f"Recurring summary: {result['recurring_out']}")
            self.log(f"Deposits file: {result['deposits_out']}")
            self.refresh_status()
        except Exception as exc:
            messagebox.showerror("Run Transaction Organizer", str(exc))

    def open_output_folder(self) -> None:
        try:
            base = self.current_base()
            out_dir = os.path.join(base, "expense_output")
            os.makedirs(out_dir, exist_ok=True)
            if os.name == "nt":
                os.startfile(out_dir)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", out_dir], check=False)
            self.log(f"Opened output folder: {out_dir}")
        except Exception as exc:
            messagebox.showerror("Open Output Folder", str(exc))


def main() -> None:
    os.makedirs(PDF_INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    root = tk.Tk()
    TransactionOrganizerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
