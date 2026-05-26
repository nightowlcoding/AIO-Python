#!/usr/bin/env python3
"""
YTD Backlog Runner for Toast Sales Summary Downloads
=====================================================
Iterates over a date range (default: Jan 1 this year → yesterday) and runs
the full download workflow for every work day:

  Phase 1 — Closed Shifts CSV
    • Looks for an existing Closed_Shifts CSV in Toast Exports/
    • If missing, opens the Toast Closed Shifts URL in Chrome and waits
      for you to export it to your Downloads folder
    • Auto-detects the file and moves it into the right date folder

  Phase 2 — Per-Employee XLSX downloads
    • Builds a shift-job list from the Closed Shifts CSV
    • Every employee who worked that day gets one download
    • Split-shift employees get TWO downloads (one per shift window)
    • Calls repeat_split_shift_exports.py (already-done XLSX files are skipped)

  Progress is saved in backlog_progress.json so you can stop and resume
  at any time without re-processing finished dates.

Usage examples
--------------
# Full YTD backlog (Jan 1 → yesterday), weekdays only
python Tools/backlog_runner.py

# Custom date range
python Tools/backlog_runner.py --start-date 2026-03-01 --end-date 2026-03-31

# Just print which dates still need work (no automation)
python Tools/backlog_runner.py --list-only

# Include Saturdays and Sundays
python Tools/backlog_runner.py --include-weekends

# You have a folder full of pre-downloaded Closed Shifts CSVs — batch import them first
python Tools/backlog_runner.py --closed-shifts-dir "C:\\path\\to\\csvs"

# Re-run dates even if already marked done
python Tools/backlog_runner.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser

# Ensure Unicode output works on Windows terminals with narrow code pages
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
TOOLS_DIR = Path(__file__).parent
ROOT_DIR = TOOLS_DIR.parent

sys.path.insert(0, str(TOOLS_DIR))
import repeat_split_shift_exports as rse  # noqa: E402 (must come after sys.path)

TOAST_EXPORTS_ROOT = ROOT_DIR / "Toast Exports"
AUTOMATE_SCRIPT = ROOT_DIR / "automate_toast_downloads.py"
REPEAT_SCRIPT = TOOLS_DIR / "repeat_split_shift_exports.py"
PROGRESS_FILE = TOOLS_DIR / "backlog_progress.json"

# Toast Closed Shifts report URL — date param is YYYY-MM-DD
TOAST_CLOSED_SHIFTS_URL = (
    "https://www.toasttab.com/restaurants/admin/reports/labor/close-shifts"
    "?startDate={date}&endDate={date}"
)

# Common Chrome executable locations on Windows
_CHROME_CANDIDATES = [
    "chrome",
    "chrome.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

KNOWN_PYTHON = Path(r"C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_python_exe() -> str:
    if KNOWN_PYTHON.exists():
        return str(KNOWN_PYTHON)
    return sys.executable


def find_chrome() -> Optional[str]:
    for candidate in _CHROME_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
        if os.path.isabs(candidate) and Path(candidate).exists():
            return candidate
    return None


def open_url_in_chrome(url: str) -> None:
    chrome = find_chrome()
    if chrome:
        subprocess.Popen([chrome, url])
    else:
        webbrowser.open(url)


def work_dates(start: date, end: date, include_weekends: bool = False) -> list[date]:
    """Return all dates in [start, end], optionally skipping weekends."""
    out: list[date] = []
    cur = start
    while cur <= end:
        if include_weekends or cur.weekday() < 5:  # 0=Mon … 4=Fri
            out.append(cur)
        cur += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Progress file
# ---------------------------------------------------------------------------

def load_progress() -> dict[str, str]:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_progress(progress: dict[str, str]) -> None:
    PROGRESS_FILE.write_text(
        json.dumps(dict(sorted(progress.items())), indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# "Already done?" check
# ---------------------------------------------------------------------------

def date_already_done(report_date: str) -> bool:
    """True if at least one XLSX file for this date already exists."""
    if not TOAST_EXPORTS_ROOT.exists():
        return False
    for folder in TOAST_EXPORTS_ROOT.iterdir():
        if not folder.is_dir() or report_date not in folder.name:
            continue
        if list(folder.glob(f"*{report_date}*.xlsx")):
            return True
    return False


# ---------------------------------------------------------------------------
# Closed Shifts CSV — find / wait / import
# ---------------------------------------------------------------------------

def find_existing_closed_shifts_csv(report_date: str) -> Optional[Path]:
    """Return an already-imported Closed Shifts CSV for report_date, or None."""
    try:
        return rse.find_closed_shifts_csv(report_date, TOAST_EXPORTS_ROOT)
    except FileNotFoundError:
        return None


def wait_for_closed_shifts_download(report_date: str, timeout: int = 180) -> Optional[Path]:
    """
    Poll Downloads (and %TEMP%) for a Closed Shifts CSV that actually
    contains rows for report_date.  Returns the Path when found, or None
    on timeout.
    """
    deadline = time.time() + timeout
    last_dot = time.time()

    while time.time() < deadline:
        for d in rse.DEFAULT_DOWNLOAD_DIRS:
            if not d.exists():
                continue
            for p in d.glob("*.csv"):
                name_low = p.name.lower()
                if "closed" in name_low and "shift" in name_low:
                    if rse.closed_shifts_file_has_date(p, report_date):
                        return p
        # Print a progress dot every 10 s so the terminal doesn't look frozen
        if time.time() - last_dot >= 10:
            remaining = int(deadline - time.time())
            print(f"    ... still watching ({remaining}s left)", flush=True)
            last_dot = time.time()
        time.sleep(1)

    return None


def import_closed_shifts_csv(src: Path, report_date: str) -> Path:
    """Copy a downloaded Closed Shifts CSV into the correct Toast Exports sub-folder."""
    location_name = rse.sanitize_folder_name(
        rse.detect_location_name_from_closed_shifts(src)
    )
    location_token = rse.safe_token(location_name)
    target_dir = TOAST_EXPORTS_ROOT / f"{report_date}_{location_name}"
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"Closed_Shifts_{report_date}_{location_token}.csv"
    shutil.copy2(src, dest)
    return dest


# ---------------------------------------------------------------------------
# Per-employee XLSX download (calls repeat_split_shift_exports.py)
# ---------------------------------------------------------------------------

def run_exports_for_date(report_date: str, closed_shifts_csv: Path, no_launch_chrome: bool = True) -> str:
    """
    Call repeat_split_shift_exports.py for one date.
    Returns "done" | "partial" | "failed".
    """
    cmd = [
        get_python_exe(),
        str(REPEAT_SCRIPT),
        "--closed-shifts-csv", str(closed_shifts_csv),
        "--report-date", report_date,
        "--no-import-closed-shifts",   # we already handled the CSV
        "--auto-advance",              # auto-detect each download; no manual Enter
        "--delete-old",                # clean up stale files for these employees
        "--popup-guard-seconds", "3600",
    ]
    if no_launch_chrome:
        cmd.append("--no-launch-chrome")
    print(f"  -> Running exports ({len(cmd)} args)...")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        return "done"
    # Return partial if some files were created despite a non-zero exit
    folder = closed_shifts_csv.parent
    if list(folder.glob(f"*{report_date}*.xlsx")):
        return "partial"
    return "failed"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    today = date.today()
    ytd_start = date(today.year, 1, 1)
    yesterday = today - timedelta(days=1)

    p = argparse.ArgumentParser(
        description="YTD Backlog Runner — download Toast Sales Summary for every work day",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--start-date",
        default=ytd_start.isoformat(),
        metavar="YYYY-MM-DD",
        help=f"First date to process (default: {ytd_start})",
    )
    p.add_argument(
        "--end-date",
        default=yesterday.isoformat(),
        metavar="YYYY-MM-DD",
        help=f"Last date to process (default: {yesterday})",
    )
    p.add_argument(
        "--include-weekends",
        action="store_true",
        help="Also process Saturdays and Sundays",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-process dates already marked done in progress file",
    )
    p.add_argument(
        "--list-only",
        action="store_true",
        help="Print pending dates and exit without running automation",
    )
    p.add_argument(
        "--closed-shifts-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Folder containing pre-downloaded Closed Shifts CSVs. "
            "The script will import any that match a pending date before starting automation."
        ),
    )
    p.add_argument(
        "--no-launch-chrome",
        action="store_true",
        help="Skip launching Chrome for both the Closed Shifts download and Sales Summary automation (use when Toast is already open)",
    )
    return p


def run() -> int:
    args = build_parser().parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)

    if start > end:
        print(f"ERROR: --start-date ({start}) is after --end-date ({end})")
        return 1

    all_dates = work_dates(start, end, args.include_weekends)
    progress = load_progress()

    # ── Mark already-done dates ─────────────────────────────────────────────
    if not args.force:
        for d in all_dates:
            ds = d.isoformat()
            if progress.get(ds) != "done" and date_already_done(ds):
                progress[ds] = "done"
        save_progress(progress)

    pending = [
        d.isoformat()
        for d in all_dates
        if args.force or progress.get(d.isoformat()) not in ("done",)
    ]

    # ── Header ──────────────────────────────────────────────────────────────
    done_count = len(all_dates) - len(pending)
    print(f"\n{'='*68}")
    print("  TOAST YTD BACKLOG RUNNER")
    print(f"{'='*68}")
    print(f"  Range    : {args.start_date}  ->  {args.end_date}")
    print(f"  Work days: {len(all_dates)}")
    print(f"  Done     : {done_count}")
    print(f"  Pending  : {len(pending)}")
    print(f"{'='*68}\n")

    if args.list_only or not pending:
        if pending:
            print("Dates still pending:")
            for ds in pending:
                status = progress.get(ds, "not started")
                print(f"  {ds}  [{status}]")
        else:
            print("All dates are already processed.  Use --force to re-run.")
        return 0

    # ── Batch-import pre-downloaded Closed Shifts CSVs if dir provided ──────
    if args.closed_shifts_dir:
        print(f"Scanning for Closed Shifts CSVs in: {args.closed_shifts_dir}")
        imported = 0
        for p in sorted(Path(args.closed_shifts_dir).glob("*.csv")):
            name_low = p.name.lower()
            if "closed" not in name_low or "shift" not in name_low:
                continue
            for ds in pending:
                if rse.closed_shifts_file_has_date(p, ds):
                    dest = import_closed_shifts_csv(p, ds)
                    print(f"  Imported {p.name}  →  {dest.name}")
                    imported += 1
                    break
        print(f"  {imported} Closed Shifts CSV(s) imported.\n")

    # ── One-time Chrome prompt ───────────────────────────────────────────────
    if not args.no_launch_chrome:
        input(
            "Open Chrome and log into Toast -> Sales Summary page, then press ENTER here...\n"
        )
    else:
        print("(--no-launch-chrome: assuming Toast is already open in Chrome)\n")

    # ── Main loop ────────────────────────────────────────────────────────────
    for idx, report_date in enumerate(pending, 1):
        print(f"\n{'─'*68}")
        print(f"  [{idx}/{len(pending)}]  {report_date}")
        print(f"{'─'*68}")

        # ── Phase 1: Closed Shifts CSV ───────────────────────────────────────
        closed_csv = find_existing_closed_shifts_csv(report_date)

        if closed_csv:
            print(f"  ✓ Closed Shifts CSV: {closed_csv.name}")
        else:
            url = TOAST_CLOSED_SHIFTS_URL.format(date=report_date)
            print(f"\n  Closed Shifts CSV not found for {report_date}.")
            print(f"  Opening Toast Closed Shifts report:")
            print(f"    {url}")
            if args.no_launch_chrome:
                print("  (--no-launch-chrome: skipping browser open — please navigate to the URL above manually)")
            else:
                open_url_in_chrome(url)
            print(
                "\n  Please export the Closed Shifts report from Toast to your Downloads folder."
                "\n  The script will auto-detect the file (timeout: 3 min)...\n"
            )

            downloaded = wait_for_closed_shifts_download(report_date, timeout=180)

            if downloaded is None:
                print(
                    f"\n  ✗ Timeout — no Closed Shifts CSV detected for {report_date}."
                    f"\n    Skipping this date. Run again later to retry."
                )
                progress[report_date] = "skipped"
                save_progress(progress)
                continue

            closed_csv = import_closed_shifts_csv(downloaded, report_date)
            print(f"  ✓ Imported: {closed_csv.relative_to(ROOT_DIR)}")

        # Quick sanity check — how many employees are in the file?
        try:
            windows = rse.parse_closed_shift_rows(closed_csv, report_date)
            employees = sorted({emp for emp, *_ in windows})
            multi = [e for e in employees if sum(1 for emp, *_ in windows if emp == e) > 1]
            print(f"  Employees: {len(employees)} total, {len(multi)} split-shift")
            if not windows:
                print("  ⚠  No shift rows found for this date — skipping.")
                progress[report_date] = "skipped"
                save_progress(progress)
                continue
        except Exception as exc:
            print(f"  ⚠  Could not parse Closed Shifts CSV: {exc} — skipping.")
            progress[report_date] = "skipped"
            save_progress(progress)
            continue

        # ── Phase 2: Per-employee XLSX downloads ─────────────────────────────
        print(f"\n  Starting employee downloads for {report_date}...")
        status = run_exports_for_date(report_date, closed_csv, no_launch_chrome=args.no_launch_chrome)
        progress[report_date] = status
        save_progress(progress)

        icon = "✓" if status == "done" else ("⚠" if status == "partial" else "✗")
        print(f"\n  {icon} {report_date}  →  {status.upper()}")

    # ── Final summary ────────────────────────────────────────────────────────
    progress = load_progress()
    counts = {"done": 0, "partial": 0, "skipped": 0, "failed": 0}
    for v in progress.values():
        if v in counts:
            counts[v] += 1

    print(f"\n{'='*68}")
    print("  BACKLOG RUN COMPLETE")
    print(f"{'='*68}")
    print(f"  Done    : {counts['done']}")
    print(f"  Partial : {counts['partial']}")
    print(f"  Skipped : {counts['skipped']}")
    print(f"  Failed  : {counts['failed']}")
    print(f"{'='*68}\n")

    if counts["partial"] or counts["failed"]:
        print("  Re-run to retry partial/failed dates (they are NOT marked done).\n")

    return 0


if __name__ == "__main__":
    sys.exit(run())
