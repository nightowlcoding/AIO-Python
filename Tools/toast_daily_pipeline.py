#!/usr/bin/env python3
"""
toast_daily_pipeline.py — Three-step pipeline for Toast daily shift processing.

  step1  Download Closed_Shifts CSVs for each day in a date range.
         Requires browser session cookies from a logged-in Toast admin tab.

  step2  Scan those CSVs and print who worked split shifts each day.
         No network calls — reads only what was saved in step1.

  step3  Download Sales Summary XLSXs for every split-shift employee.
         Requires a valid JWT in Tools/toast_config.json.

Usage
-----
  python Tools/toast_daily_pipeline.py step1 --start 2026-05-22 --end 2026-05-26
  python Tools/toast_daily_pipeline.py step2 --start 2026-05-22 --end 2026-05-26
  python Tools/toast_daily_pipeline.py step3 --start 2026-05-22 --end 2026-05-26

Cookies (step1)
---------------
  Option A — paste when prompted (default, no extra flags needed)
  Option B — --cookie "full cookie string here"
  Option C — --cookie-file Tools/toast_cookies.txt  (one line with the cookie)

JWT (step3)
-----------
  Requires Tools/toast_config.json with a valid Bearer token.
  Exit code 2 = JWT expired — update the file and re-run step3.
"""

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

# ── Paths ──────────────────────────────────────────────────────────────────
TOOLS_DIR           = Path(__file__).parent
ROOT_DIR            = TOOLS_DIR.parent
TOAST_EXPORTS_ROOT  = ROOT_DIR / "Toast Exports"
DEFAULT_LOCATION    = "Big House Burgers"
DEFAULT_COOKIE_FILE = TOOLS_DIR / "toast_cookies.txt"
DEFAULT_CONFIG      = TOOLS_DIR / "toast_config.json"
DEFAULT_GUIDS       = TOOLS_DIR / "employee_guids.json"

# ── Import shared helpers ──────────────────────────────────────────────────
sys.path.insert(0, str(TOOLS_DIR))

from repeat_split_shift_exports import (   # type: ignore[import]
    parse_closed_shift_rows,
    build_jobs_from_windows,
    split_only_jobs,
    safe_token,
    format_toast_time,
)
from toast_api_downloader import (         # type: ignore[import]
    load_config,
    check_jwt_expiry,
    build_headers as _api_build_headers,
    load_guids,
    lookup_guids,
    build_request_body,
    download_report,
    parse_toast_time,
    EMPTY_REPORT_THRESHOLD,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def iter_dates(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def closed_shifts_path(date_str: str, location: str) -> Path:
    """Return the expected path for a Closed_Shifts CSV given a date + location."""
    folder = TOAST_EXPORTS_ROOT / f"{date_str}_{location}"
    fname  = f"Closed_Shifts_{date_str}_{safe_token(location)}.csv"
    return folder / fname


def count_csv_data_rows(raw: bytes) -> int:
    try:
        text = raw.decode("windows-1252", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return max(0, len(lines) - 1)   # subtract header row


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Download Closed_Shifts CSVs
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_cookie(args) -> str:
    """Return cookie string from --cookie, --cookie-file, default file, or prompt."""
    if getattr(args, "cookie", None):
        return args.cookie.strip()

    cookie_file = Path(getattr(args, "cookie_file", None) or DEFAULT_COOKIE_FILE)
    if cookie_file.exists():
        text = cookie_file.read_text(encoding="utf-8").strip()
        if text:
            print(f"[step1] Using cookies from {cookie_file}")
            return text

    print()
    print("Paste your Toast session cookie string.")
    print("  How to get it:")
    print("  1. Open Toast admin in Chrome and log in")
    print("  2. Open DevTools (F12) → Network tab")
    print("  3. Reload the page, click any request to toasttab.com")
    print("  4. Find the 'Cookie' request header and copy the full value")
    print()
    print("Paste cookie string (press Enter twice when done):")
    lines = []
    while True:
        line = input()
        if not line:
            break
        lines.append(line)
    return " ".join(lines).strip()


def step1_download_closed_shifts(args) -> int:
    start    = date.fromisoformat(args.start)
    end      = date.fromisoformat(args.end)
    location = args.location

    cookie = _resolve_cookie(args)
    if not cookie:
        print("[step1] ERROR: No cookie string provided.", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers.update({
        "Cookie":     cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "text/csv,text/html,*/*",
        "Referer":    "https://www.toasttab.com/restaurants/admin/reports/home",
    })

    print(f"\n[step1] Downloading Closed_Shifts for {args.start} → {args.end} ({location})\n")

    saved = skipped = empty = failed = 0

    for day in iter_dates(start, end):
        date_str   = day.strftime("%Y-%m-%d")
        mm_dd_yyyy = day.strftime("%m-%d-%Y")
        out_path   = closed_shifts_path(date_str, location)

        if out_path.exists():
            print(f"  SKIP  {date_str}  (already exists)")
            skipped += 1
            continue

        print(f"  GET   {date_str}", end=" … ", flush=True)

        # Step 1a: prime the session state with the correct date via DataTables request
        try:
            session.get(
                "https://www.toasttab.com/restaurants/admin/reports/closedshifts",
                params={
                    "reportDateStart": mm_dd_yyyy,
                    "reportDateEnd":   mm_dd_yyyy,
                    "sEcho":           "1",
                    "iDisplayStart":   "0",
                    "iDisplayLength":  "25",
                    "iSortingCols":    "0",
                },
                timeout=20,
            )
        except Exception as exc:
            # Non-fatal — the main download may still work
            print(f"(session prime warn: {exc}) ", end="", flush=True)

        # Step 1b: download the CSV export
        try:
            resp = session.get(
                "https://www.toasttab.com/restaurants/admin/reports/closedshifts",
                params={
                    "excel":           "true",
                    "reportDateStart": mm_dd_yyyy,
                    "reportDateEnd":   mm_dd_yyyy,
                },
                timeout=30,
            )
            resp.raise_for_status()

            rows = count_csv_data_rows(resp.content)
            print(f"{len(resp.content):,} bytes, {rows} rows", end="  ")

            if rows == 0:
                print("(no data — skipping)")
                empty += 1
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(resp.content)
                print(f"→ saved")
                saved += 1

        except Exception as exc:
            print(f"ERROR: {exc}")
            failed += 1

    print(f"\n[step1] Done — {saved} saved, {skipped} skipped, {empty} empty, {failed} failed")
    return 0 if failed == 0 else 1


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Scan for split-shift employees (no network)
# ─────────────────────────────────────────────────────────────────────────────

def step2_scan_split_shifts(args) -> int:
    start    = date.fromisoformat(args.start)
    end      = date.fromisoformat(args.end)
    location = args.location

    print(f"\n[step2] Scanning for split shifts {args.start} → {args.end} ({location})\n")

    split_days = 0

    for day in iter_dates(start, end):
        date_str = day.strftime("%Y-%m-%d")
        csv_path = closed_shifts_path(date_str, location)

        if not csv_path.exists():
            print(f"  {date_str}  MISSING  (run step1 first)")
            continue

        try:
            windows  = parse_closed_shift_rows(csv_path, date_str)
        except Exception as exc:
            print(f"  {date_str}  ERROR reading CSV: {exc}")
            continue

        all_jobs   = build_jobs_from_windows(windows)
        split_jobs = split_only_jobs(all_jobs)

        if not split_jobs:
            print(f"  {date_str}  —  {len(all_jobs)} shifts, no split shifts")
        else:
            employees = sorted({j.employee for j in split_jobs})
            shift_count = len(split_jobs)
            print(
                f"  {date_str}  SPLIT  {len(employees)} employee(s), "
                f"{shift_count} shifts  →  {', '.join(employees)}"
            )
            # Print each split-shift detail indented
            for job in split_jobs:
                print(f"             {job.employee:<30s} {job.shift_label:<8s} "
                      f"{job.start_for_toast} → {job.end_for_toast}")
            split_days += 1

    print(f"\n[step2] {split_days} day(s) with split shifts in {args.start} – {args.end}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Download Sales Summary XLSXs for split-shift employees
# ─────────────────────────────────────────────────────────────────────────────

def step3_download_reviews(args) -> int:
    start    = date.fromisoformat(args.start)
    end      = date.fromisoformat(args.end)
    location = args.location

    config_path = Path(args.config or DEFAULT_CONFIG)
    guids_path  = Path(args.guids  or DEFAULT_GUIDS)

    config   = load_config(config_path)
    check_jwt_expiry(config)
    headers  = _api_build_headers(config)
    guid_map = load_guids(guids_path)

    print(f"\n[step3] Downloading shift reviews {args.start} → {args.end} ({location})\n")

    total_saved = total_skipped = total_failed = 0

    for day in iter_dates(start, end):
        date_str = day.strftime("%Y-%m-%d")
        csv_path = closed_shifts_path(date_str, location)

        if not csv_path.exists():
            print(f"  {date_str}  SKIP — no Closed_Shifts CSV (run step1 first)")
            continue

        try:
            windows  = parse_closed_shift_rows(csv_path, date_str)
        except Exception as exc:
            print(f"  {date_str}  ERROR reading CSV: {exc}")
            continue

        all_jobs   = build_jobs_from_windows(windows)
        split_jobs = split_only_jobs(all_jobs)

        if not split_jobs:
            print(f"  {date_str}  —  no split shifts, skipping")
            continue

        export_dir = csv_path.parent
        print(f"\n  {date_str}  {len(split_jobs)} shift(s) to download:")

        for job in split_jobs:
            out_name = f"{job.shift_label}_{safe_token(job.employee)}_{date_str}.xlsx"
            out_path = export_dir / out_name

            if out_path.exists() and not args.overwrite:
                print(f"    SKIP  {out_name}  (exists, use --overwrite to force)")
                total_skipped += 1
                continue

            guids = lookup_guids(job.employee, guid_map)
            if not guids:
                print(f"    MISS  {job.employee}  — not in employee_guids.json")
                total_failed += 1
                continue

            start_h, start_m = parse_toast_time(job.start_for_toast)
            end_h,   end_m   = parse_toast_time(job.end_for_toast)

            print(
                f"    GET   {job.employee:<30s} {job.start_for_toast} → {job.end_for_toast}",
                end=" … ", flush=True,
            )

            best: bytes = b""
            last_err = ""
            for guid in guids:
                body = build_request_body(guid, date_str, start_h, start_m, end_h, end_m)
                try:
                    data = download_report(headers, body)
                    if len(data) > len(best):
                        best = data
                    if len(best) >= EMPTY_REPORT_THRESHOLD:
                        break
                except SystemExit:
                    raise
                except Exception as exc:
                    last_err = str(exc)

            if not best:
                print(f"FAILED  ({last_err})")
                total_failed += 1
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(best)
            print(f"saved  ({len(best) / 1024:.1f} KB)")
            total_saved += 1

    print(
        f"\n[step3] Done — {total_saved} saved, {total_skipped} skipped, "
        f"{total_failed} failed"
    )
    return 0 if total_failed == 0 else 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="toast_daily_pipeline",
        description="Three-step pipeline: download closed shifts → scan → download reviews",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_date_args(p):
        p.add_argument("--start",    required=True, help="Start date YYYY-MM-DD")
        p.add_argument("--end",      required=True, help="End date YYYY-MM-DD (inclusive)")
        p.add_argument("--location", default=DEFAULT_LOCATION,
                       help=f"Location name (default: {DEFAULT_LOCATION})")

    # ── step1 ──────────────────────────────────────────────────────────────
    p1 = sub.add_parser("step1", help="Download Closed_Shifts CSVs from Toast admin")
    add_date_args(p1)
    p1.add_argument("--cookie",      default=None,
                    help="Full browser Cookie header value (paste directly)")
    p1.add_argument("--cookie-file", default=None,
                    help="Path to a text file containing the cookie string "
                         f"(default: {DEFAULT_COOKIE_FILE})")

    # ── step2 ──────────────────────────────────────────────────────────────
    p2 = sub.add_parser("step2", help="Scan closed shifts and report split-shift employees")
    add_date_args(p2)

    # ── step3 ──────────────────────────────────────────────────────────────
    p3 = sub.add_parser("step3", help="Download Sales Summary XLSXs for split-shift employees")
    add_date_args(p3)
    p3.add_argument("--config",    default=None,
                    help=f"Path to toast_config.json (default: {DEFAULT_CONFIG})")
    p3.add_argument("--guids",     default=None,
                    help=f"Path to employee_guids.json (default: {DEFAULT_GUIDS})")
    p3.add_argument("--overwrite", action="store_true",
                    help="Re-download XLSXs even if they already exist")

    args = parser.parse_args()

    if args.command == "step1":
        return step1_download_closed_shifts(args)
    if args.command == "step2":
        return step2_scan_split_shifts(args)
    if args.command == "step3":
        return step3_download_reviews(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
