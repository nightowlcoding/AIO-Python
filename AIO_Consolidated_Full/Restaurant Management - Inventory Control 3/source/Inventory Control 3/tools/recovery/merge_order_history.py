#!/usr/bin/env python3
"""Merge historical order data into IC3 orders_database.json safely.

Supported source inputs:
- orders_database.json style files
- invoice_import_log.json style files (converted by location + delivery_date)
- CSV files with columns that look like product/order/qty and optional location/date

Usage examples:
  python merge_order_history.py --ic3-dir ".../Inventory Control 3" --source ".../orders_database.json"
  python merge_order_history.py --ic3-dir ".../Inventory Control 3" --source-root ".../AIO-Python" --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


OrderMap = Dict[str, Dict[str, Dict[str, float]]]


@dataclass
class MergeStats:
    files_seen: int = 0
    files_parsed: int = 0
    location_dates_added: int = 0
    location_dates_updated: int = 0
    product_rows_added: int = 0


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_location(raw: str) -> Optional[str]:
    if not raw:
        return None
    txt = raw.strip().lower()
    if "king" in txt:
        return "Kingsville"
    if "alice" in txt:
        return "Alice"
    return None


def normalize_product(value: str) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"\D", "", str(value))
    return cleaned or None


def normalize_quantity(value) -> Optional[float]:
    if value is None:
        return None
    txt = str(value).strip().replace(",", "")
    if txt == "":
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def normalize_date(value: str) -> Optional[str]:
    if not value:
        return None
    txt = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", txt)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def detect_header_index(fieldnames: List[str], patterns: Iterable[str]) -> Optional[int]:
    lowered = [f.strip().lower() for f in fieldnames]
    for i, name in enumerate(lowered):
        for p in patterns:
            if p in name:
                return i
    return None


def ensure_shape(data: OrderMap) -> OrderMap:
    data.setdefault("Kingsville", {})
    data.setdefault("Alice", {})
    return data


def merge_entry(target: OrderMap, location: str, date_str: str, products: Dict[str, float], stats: MergeStats) -> None:
    if not products:
        return

    loc_map = target.setdefault(location, {})
    exists = date_str in loc_map
    dest_products = loc_map.setdefault(date_str, {})

    if exists:
        stats.location_dates_updated += 1
    else:
        stats.location_dates_added += 1

    for pn, qty in products.items():
        # Prefer non-zero values and keep the larger quantity when duplicates conflict.
        prev = dest_products.get(pn)
        if prev is None or (qty and abs(qty) > abs(prev)):
            dest_products[pn] = qty
            stats.product_rows_added += 1


def parse_orders_database(path: Path) -> OrderMap:
    raw = load_json(path)
    parsed: OrderMap = {"Kingsville": {}, "Alice": {}}

    if not isinstance(raw, dict):
        return parsed

    for loc_key, by_date in raw.items():
        loc = normalize_location(str(loc_key))
        if not loc or not isinstance(by_date, dict):
            continue
        for date_key, products in by_date.items():
            date_str = normalize_date(str(date_key))
            if not date_str or not isinstance(products, dict):
                continue
            row: Dict[str, float] = {}
            for pn, qty in products.items():
                p = normalize_product(str(pn))
                q = normalize_quantity(qty)
                if p and q is not None:
                    row[p] = q
            if row:
                parsed[loc][date_str] = row

    return parsed


def parse_invoice_import_log(path: Path) -> OrderMap:
    raw = load_json(path)
    parsed: OrderMap = {"Kingsville": {}, "Alice": {}}
    if not isinstance(raw, list):
        return parsed

    for entry in raw:
        if not isinstance(entry, dict):
            continue
        loc = normalize_location(str(entry.get("location", "")))
        date_str = normalize_date(str(entry.get("delivery_date", "")))
        products = entry.get("products", {})
        if not loc or not date_str or not isinstance(products, dict):
            continue

        row: Dict[str, float] = {}
        for pn, qty in products.items():
            p = normalize_product(str(pn))
            q = normalize_quantity(qty)
            if p and q is not None:
                row[p] = q
        if row:
            parsed[loc][date_str] = row

    return parsed


def parse_order_csv(path: Path) -> OrderMap:
    parsed: OrderMap = {"Kingsville": {}, "Alice": {}}
    rows: List[List[str]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return parsed

    # Try DictReader mode first when headers look meaningful.
    fieldnames = [c.strip() for c in rows[0]]
    if fieldnames and any(name for name in fieldnames if not name.isdigit()):
        loc_idx = detect_header_index(fieldnames, ["location", "store", "site"])
        date_idx = detect_header_index(fieldnames, ["date", "delivery"])
        product_idx = detect_header_index(fieldnames, ["product", "item", "sku", "number", "#"])
        qty_idx = detect_header_index(fieldnames, ["qty", "quantity", "order"])

        if product_idx is not None and qty_idx is not None:
            default_loc = normalize_location(path.name) or "Kingsville"
            default_date = normalize_date(path.name)
            for row in rows[1:]:
                if not row:
                    continue
                loc = normalize_location(row[loc_idx]) if loc_idx is not None and loc_idx < len(row) else default_loc
                date_str = normalize_date(row[date_idx]) if date_idx is not None and date_idx < len(row) else default_date
                p = normalize_product(row[product_idx]) if product_idx < len(row) else None
                q = normalize_quantity(row[qty_idx]) if qty_idx < len(row) else None
                if not (loc and date_str and p and q is not None):
                    continue
                parsed.setdefault(loc, {}).setdefault(date_str, {})[p] = q
            return parsed

    # Fallback for known inventory-like upload format (product in col 0, qty in col 2).
    loc = normalize_location(path.name)
    date_str = None
    for r in rows[:12]:
        for cell in r:
            d = normalize_date(cell)
            if d:
                date_str = d
                break
        if date_str:
            break

    if loc and date_str:
        start_idx = 0
        for i, r in enumerate(rows[:30]):
            joined = ",".join((c or "") for c in r).lower()
            if "product #" in joined or "product number" in joined:
                start_idx = i + 1
                break

        product_map: Dict[str, float] = {}
        for r in rows[start_idx:]:
            if not r:
                continue
            p = normalize_product(r[0] if len(r) > 0 else "")
            q = normalize_quantity(r[2] if len(r) > 2 else "")
            if p and q is not None:
                product_map[p] = q
        if product_map:
            parsed[loc][date_str] = product_map

    return parsed


def iter_source_files(source_paths: List[Path], source_root: Optional[Path]) -> List[Path]:
    candidates: List[Path] = []

    for p in source_paths:
        if p.is_file():
            candidates.append(p)
        elif p.is_dir():
            for ext in ("*.json", "*.csv"):
                candidates.extend(p.rglob(ext))

    if source_root and source_root.exists():
        for ext in ("*.json", "*.csv"):
            for p in source_root.rglob(ext):
                name = p.name.lower()
                if any(k in name for k in ["orders_database", "invoice_import_log", "order", "invoice"]):
                    candidates.append(p)

    # Deduplicate while preserving order.
    seen = set()
    unique: List[Path] = []
    for p in candidates:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def parse_source(path: Path) -> Optional[OrderMap]:
    name = path.name.lower()
    try:
        if name.endswith("orders_database.json"):
            return parse_orders_database(path)
        if name.endswith("invoice_import_log.json"):
            return parse_invoice_import_log(path)
        if name.endswith(".csv"):
            return parse_order_csv(path)
        if name.endswith(".json"):
            # Fallback to try DB-like shape.
            return parse_orders_database(path)
    except Exception:
        return None
    return None


def merged_date_count(data: OrderMap) -> int:
    return sum(len(v) for v in data.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge order history into IC3 orders database")
    ap.add_argument("--ic3-dir", required=True, help="Path to Inventory Control 3 folder")
    ap.add_argument("--source", action="append", default=[], help="Source file or folder (repeatable)")
    ap.add_argument("--source-root", help="Optional broad root to search for candidate files")
    ap.add_argument("--apply", action="store_true", help="Write merge result to orders_database.json")
    args = ap.parse_args()

    ic3_dir = Path(args.ic3_dir)
    data_dir = ic3_dir / "data"
    orders_path = data_dir / "orders_database.json"
    if not orders_path.exists():
        print(f"ERROR: missing orders database at {orders_path}")
        return 2

    current = ensure_shape(load_json(orders_path))
    before_dates = merged_date_count(current)

    source_paths = [Path(s) for s in args.source]
    source_root = Path(args.source_root) if args.source_root else None
    files = iter_source_files(source_paths, source_root)

    stats = MergeStats(files_seen=len(files))

    for fp in files:
        if str(fp.resolve()) == str(orders_path.resolve()):
            continue
        parsed = parse_source(fp)
        if not parsed:
            continue
        stats.files_parsed += 1
        for loc, by_date in parsed.items():
            for date_str, products in by_date.items():
                merge_entry(current, loc, date_str, products, stats)

    after_dates = merged_date_count(current)

    print(f"files_seen={stats.files_seen}")
    print(f"files_parsed={stats.files_parsed}")
    print(f"location_dates_before={before_dates}")
    print(f"location_dates_after={after_dates}")
    print(f"location_dates_added={stats.location_dates_added}")
    print(f"location_dates_updated={stats.location_dates_updated}")
    print(f"product_rows_added={stats.product_rows_added}")

    for loc in ("Kingsville", "Alice"):
        print(f"{loc}_dates={len(current.get(loc, {}))}")

    if args.apply:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup = data_dir / f"orders_database.premerge_{ts}.json"
        shutil.copy2(orders_path, backup)
        orders_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        print(f"backup_created={backup}")
        print(f"wrote={orders_path}")
    else:
        print("dry_run=1 (use --apply to write)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
