#!/usr/bin/env python3
import argparse
import csv
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_TOAST_EXPORTS_ROOT = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports")
DEFAULT_EXPORT_DIR = DEFAULT_TOAST_EXPORTS_ROOT
DEFAULT_PLAN_CSV = DEFAULT_TOAST_EXPORTS_ROOT / "Custom_Hours_MultiShift_Only.csv"
DEFAULT_DOWNLOAD_DIRS = [Path.home() / "Downloads", Path(os.environ.get("TEMP", r"C:\Windows\Temp"))]


@dataclass
class ShiftJob:
    employee: str
    shift_label: str
    start_for_toast: str
    end_for_toast: str
    start_dt: Optional[datetime]
    end_dt: Optional[datetime]


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None

    candidates = [
        "%m/%d/%y %I:%M %p",
        "%m/%d/%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]

    for fmt in candidates:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def safe_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def shift_label_from_start(start_dt: datetime) -> str:
    return "Morning" if start_dt.hour < 12 or (start_dt.hour == 12 and start_dt.minute == 0) else "Night"


def format_toast_time(value: datetime) -> str:
    return value.strftime("%-I:%M %p") if os.name != "nt" else value.strftime("%I:%M %p").lstrip("0")


def infer_report_date(plan_csv: Path, jobs: list[ShiftJob], explicit: Optional[str]) -> str:
    if explicit:
        return explicit

    m = re.search(r"(\d{4}-\d{2}-\d{2})", plan_csv.name)
    if m:
        return m.group(1)

    for job in jobs:
        if job.start_dt is not None:
            return job.start_dt.strftime("%Y-%m-%d")

    return datetime.now().strftime("%Y-%m-%d")


def load_jobs(plan_csv: Path) -> list[ShiftJob]:
    if not plan_csv.exists():
        raise FileNotFoundError(f"Plan CSV not found: {plan_csv}")

    with plan_csv.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    jobs: list[ShiftJob] = []
    for row in rows:
        employee = (row.get("Employee") or "").strip()
        start_for_toast = (row.get("StartTimeForToast") or "").strip()
        end_for_toast = (row.get("EndTimeForToast") or "").strip()
        shift_label = (row.get("ShiftLabel") or "").strip() or "Shift"
        start_dt = parse_dt((row.get("StartDateTime") or "").strip())

        if not employee or not start_for_toast or not end_for_toast:
            continue

        jobs.append(
            ShiftJob(
                employee=employee,
                shift_label=shift_label,
                start_for_toast=start_for_toast,
                end_for_toast=end_for_toast,
                start_dt=start_dt,
                end_dt=parse_dt((row.get("EndDateTime") or "").strip()),
            )
        )

    jobs.sort(key=lambda j: (j.employee.lower(), j.start_dt or datetime.max))
    return jobs


def resolve_plan_csv(plan_csv: Path, toast_exports_root: Path, report_date: Optional[str]) -> Path:
    if plan_csv.exists():
        return plan_csv

    candidates: list[tuple[int, float, Path]] = []
    date_token = report_date or ""

    for p in toast_exports_root.rglob("Custom_Hours_MultiShift_Only*.csv"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue

        score = 0
        if date_token and date_token in p.name:
            score += 30
        if date_token and date_token in str(p.parent):
            score += 10
        candidates.append((score, mtime, p))

    if not candidates:
        raise FileNotFoundError(f"Plan CSV not found: {plan_csv}")

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def find_closed_shifts_csv(report_date: str, toast_exports_root: Path) -> Path:
    if not toast_exports_root.exists():
        raise FileNotFoundError(f"Toast Exports root not found: {toast_exports_root}")

    date_token = report_date
    candidates: list[tuple[int, float, Path]] = []

    def file_has_report_date_rows(path: Path) -> bool:
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    in_raw = (row.get("In Date") or "").strip()
                    in_dt = parse_dt(in_raw)
                    if in_dt is not None and in_dt.strftime("%Y-%m-%d") == report_date:
                        return True
        except (OSError, UnicodeDecodeError, csv.Error):
            return False
        return False

    # Prefer files that include the date in the filename.
    for p in toast_exports_root.rglob("*.csv"):
        name_low = p.name.lower()
        if "closed_shifts" not in name_low:
            continue
        score = 0
        if date_token in p.name:
            score += 50
        if date_token in str(p.parent):
            score += 10

        # When date token isn't in the path, inspect rows to ensure the file actually contains the target date.
        if score == 0 and file_has_report_date_rows(p):
            score += 40

        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        candidates.append((score, mtime, p))

    if not candidates:
        raise FileNotFoundError(
            f"No Closed_Shifts CSV found under {toast_exports_root}"
        )

    # Best score first, then newest.
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

    # Require a date-related hit to avoid silently selecting a wrong-day file.
    if candidates[0][0] <= 0:
        raise FileNotFoundError(
            f"No Closed_Shifts CSV matched report date {report_date} under {toast_exports_root}"
        )

    top_score = candidates[0][0]
    top = [c for c in candidates if c[0] == top_score]
    if len(top) > 1:
        # Keep newest among ties.
        top.sort(key=lambda x: x[1], reverse=True)

    return top[0][2]


def parse_closed_shift_rows(closed_shifts_csv: Path, report_date: str) -> list[tuple[str, datetime, datetime]]:
    if not closed_shifts_csv.exists():
        raise FileNotFoundError(f"Closed shifts CSV not found: {closed_shifts_csv}")

    with closed_shifts_csv.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    normalized: list[tuple[str, datetime, datetime]] = []
    for row in rows:
        employee = (row.get("Employee") or "").strip()
        in_raw = (row.get("In Date") or "").strip()
        out_raw = (row.get("Shift Closed Date") or "").strip()
        if not employee or not in_raw or not out_raw:
            continue

        in_dt = parse_dt(in_raw)
        out_dt = parse_dt(out_raw)
        if in_dt is None or out_dt is None:
            continue

        if in_dt.strftime("%Y-%m-%d") != report_date:
            continue

        normalized.append((employee, in_dt, out_dt))

    normalized.sort(key=lambda item: (item[0].lower(), item[1]))
    return normalized


def build_jobs_from_windows(windows: list[tuple[str, datetime, datetime]]) -> list[ShiftJob]:
    jobs: list[ShiftJob] = []
    for employee, in_dt, out_dt in windows:
        jobs.append(
            ShiftJob(
                employee=employee,
                shift_label=shift_label_from_start(in_dt),
                start_for_toast=format_toast_time(in_dt),
                end_for_toast=format_toast_time(out_dt),
                start_dt=in_dt,
                end_dt=out_dt,
            )
        )

    jobs.sort(key=lambda j: (j.employee.lower(), j.start_dt or datetime.max))
    return jobs


def split_only_jobs(all_jobs: list[ShiftJob]) -> list[ShiftJob]:
    counts = Counter(job.employee for job in all_jobs)
    multi = {emp for emp, c in counts.items() if c > 1}

    jobs = [job for job in all_jobs if job.employee in multi]
    jobs.sort(key=lambda j: (j.employee.lower(), j.start_dt or datetime.max))
    return jobs


def location_suffix_from_closed_shifts(closed_shifts_csv: Path, report_date: str) -> str:
    prefix = f"Closed_Shifts_{report_date}_"
    stem = closed_shifts_csv.stem
    if stem.startswith(prefix):
        suffix = stem[len(prefix):]
        if suffix:
            return suffix

    return safe_token(closed_shifts_csv.parent.name) or "Unknown_Location"


def sanitize_folder_name(text: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Unknown Location"


def closed_shifts_file_has_date(path: Path, report_date: str) -> bool:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                in_dt = parse_dt((row.get("In Date") or "").strip())
                if in_dt is not None and in_dt.strftime("%Y-%m-%d") == report_date:
                    return True
    except (OSError, UnicodeDecodeError, csv.Error):
        return False
    return False


def detect_location_name_from_closed_shifts(path: Path) -> str:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                location = (row.get("Location") or "").strip()
                if location:
                    return location
    except (OSError, UnicodeDecodeError, csv.Error):
        return "Unknown Location"
    return "Unknown Location"


def import_closed_shifts_from_downloads(report_date: str, toast_exports_root: Path) -> Optional[Path]:
    candidates: list[tuple[float, Path]] = []

    for d in DEFAULT_DOWNLOAD_DIRS:
        if not d.exists():
            continue
        try:
            for p in d.glob("*.csv"):
                if "closed" not in p.name.lower() or "shift" not in p.name.lower():
                    continue
                if not closed_shifts_file_has_date(p, report_date):
                    continue
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                candidates.append((mtime, p))
        except OSError:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    src = candidates[0][1]

    location_name = sanitize_folder_name(detect_location_name_from_closed_shifts(src))
    location_token = safe_token(location_name)
    target_dir = toast_exports_root / f"{report_date}_{location_name}"
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / f"Closed_Shifts_{report_date}_{location_token}.csv"
    shutil.copy2(src, dest)
    return dest


def write_custom_hours_csv(output_path: Path, jobs: list[ShiftJob]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Employee",
                "StartDateTime",
                "EndDateTime",
                "StartTimeForToast",
                "EndTimeForToast",
                "StartTime24",
                "EndTime24",
                "StartHour12",
                "StartMinute",
                "StartMeridiem",
                "EndHour12",
                "EndMinute",
                "EndMeridiem",
                "ShiftLabel",
            ],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()

        for job in jobs:
            if job.start_dt is None or job.end_dt is None:
                continue

            start_dt = job.start_dt
            end_dt = job.end_dt

            writer.writerow(
                {
                    "Employee": job.employee,
                    "StartDateTime": start_dt.strftime("%-m/%-d/%y %-I:%M %p") if os.name != "nt" else start_dt.strftime("%#m/%#d/%y %#I:%M %p"),
                    "EndDateTime": end_dt.strftime("%-m/%-d/%y %-I:%M %p") if os.name != "nt" else end_dt.strftime("%#m/%#d/%y %#I:%M %p"),
                    "StartTimeForToast": job.start_for_toast,
                    "EndTimeForToast": job.end_for_toast,
                    "StartTime24": start_dt.strftime("%H:%M"),
                    "EndTime24": end_dt.strftime("%H:%M"),
                    "StartHour12": str(int(start_dt.strftime("%I"))),
                    "StartMinute": start_dt.strftime("%M"),
                    "StartMeridiem": start_dt.strftime("%p"),
                    "EndHour12": str(int(end_dt.strftime("%I"))),
                    "EndMinute": end_dt.strftime("%M"),
                    "EndMeridiem": end_dt.strftime("%p"),
                    "ShiftLabel": job.shift_label,
                }
            )


def build_jobs_from_closed_shifts(closed_shifts_csv: Path, report_date: str) -> list[ShiftJob]:
    windows = parse_closed_shift_rows(closed_shifts_csv, report_date)
    all_jobs = build_jobs_from_windows(windows)
    return split_only_jobs(all_jobs)


def file_is_zip(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def list_candidates(download_dirs: Iterable[Path], baseline_ts: float, min_size: int) -> list[Path]:
    candidates: list[Path] = []
    valid_exts = {".tmp", ".xlsx", ".xls", ".csv", ""}

    for d in download_dirs:
        if not d.exists():
            continue
        try:
            for p in d.iterdir():
                if not p.is_file():
                    continue
                if p.suffix.lower() not in valid_exts:
                    continue
                try:
                    stat = p.stat()
                except OSError:
                    continue
                if stat.st_mtime <= baseline_ts:
                    continue
                if stat.st_size < min_size:
                    continue
                candidates.append(p)
        except OSError:
            continue

    # Files in Downloads/TEMP can disappear between discovery and sorting.
    # Sort defensively so transient temp-file cleanup doesn't crash the run.
    def safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    candidates.sort(key=safe_mtime, reverse=True)
    return candidates


def wait_for_download(download_dirs: list[Path], baseline_ts: float, timeout_seconds: int, min_size: int) -> Path:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        for p in list_candidates(download_dirs, baseline_ts, min_size):
            if file_is_zip(p) or p.suffix.lower() in {".xlsx", ".xls"}:
                return p
        time.sleep(0.3)

    raise TimeoutError("No new download artifact found in time")


def delete_old_exports(export_dir: Path, jobs: list[ShiftJob], report_date: str) -> list[Path]:
    deleted: list[Path] = []

    employee_tokens = {safe_token(job.employee) for job in jobs}

    for p in export_dir.glob("*.xlsx"):
        name_low = p.name.lower()
        if report_date not in p.name:
            continue

        match_employee = any(tok.lower() in name_low for tok in employee_tokens)
        if match_employee:
            p.unlink(missing_ok=True)
            deleted.append(p)

    return deleted


def start_popup_guard(script_dir: Path, seconds: int) -> Optional[subprocess.Popen]:
    guard = script_dir / "toast_popup_guard.py"
    if not guard.exists():
        return None

    if importlib.util.find_spec("pywinauto") is None:
        print("Popup guard skipped: pywinauto is not installed in this Python environment")
        return None

    cmd = [sys.executable, str(guard), "--seconds", str(seconds)]
    return subprocess.Popen(cmd)


def run() -> int:
    parser = argparse.ArgumentParser(
        description="Repeat Toast shift export workflow with popup guard and artifact capture"
    )
    parser.add_argument("--plan-csv", type=Path, default=DEFAULT_PLAN_CSV)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--report-date", default=None, help="YYYY-MM-DD; inferred if omitted")
    parser.add_argument("--toast-exports-root", type=Path, default=DEFAULT_TOAST_EXPORTS_ROOT)
    parser.add_argument("--auto-find-closed-shifts", action="store_true", help="Find Closed_Shifts CSV for --report-date and build all jobs automatically")
    parser.add_argument("--closed-shifts-csv", type=Path, default=None, help="Explicit Closed_Shifts CSV (used with --auto-find-closed-shifts or standalone)")
    parser.add_argument("--no-import-closed-shifts", action="store_true", help="Disable importing Closed_Shifts CSV from Downloads when missing")
    parser.add_argument("--no-launch-chrome", action="store_true", help="Skip launching Chrome (use when Chrome is already open, e.g. from backlog_runner)")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for each download artifact")
    parser.add_argument("--min-size", type=int, default=1000, help="Minimum bytes for candidate download artifact")
    parser.add_argument("--popup-guard-seconds", type=int, default=1800)
    parser.add_argument("--no-popup-guard", action="store_true")
    parser.add_argument("--auto-advance", action="store_true", help="Do not prompt for Enter between jobs; wait for each new download automatically")
    parser.add_argument("--delete-old", action="store_true", help="Delete existing shift files for employees in plan")
    parser.add_argument("--list-only", action="store_true", help="Print resolved jobs and exit")
    args = parser.parse_args()

    report_date = args.report_date or datetime.now().strftime("%Y-%m-%d")

    jobs: list[ShiftJob] = []
    resolved_closed_shifts: Optional[Path] = None
    generated_all_csv: Optional[Path] = None
    generated_split_csv: Optional[Path] = None
    split_jobs: list[ShiftJob] = []

    if args.auto_find_closed_shifts or args.closed_shifts_csv is not None:
        if args.closed_shifts_csv is not None:
            resolved_closed_shifts = args.closed_shifts_csv
        else:
            try:
                resolved_closed_shifts = find_closed_shifts_csv(report_date, args.toast_exports_root)
            except FileNotFoundError:
                if args.no_import_closed_shifts:
                    raise
                imported = import_closed_shifts_from_downloads(report_date, args.toast_exports_root)
                if imported is None:
                    raise
                resolved_closed_shifts = imported
                print(f"Imported Closed Shifts CSV from Downloads: {resolved_closed_shifts}")

        if args.export_dir == DEFAULT_EXPORT_DIR:
            args.export_dir = resolved_closed_shifts.parent

        windows = parse_closed_shift_rows(resolved_closed_shifts, report_date)
        all_jobs = build_jobs_from_windows(windows)
        split_jobs = split_only_jobs(all_jobs)
        jobs = all_jobs

        location_suffix = location_suffix_from_closed_shifts(resolved_closed_shifts, report_date)
        generated_all_csv = args.export_dir / f"Custom_Hours_Shift_Windows_{report_date}_{location_suffix}.csv"
        generated_split_csv = args.export_dir / f"Custom_Hours_MultiShift_Only_{report_date}_{location_suffix}.csv"

        write_custom_hours_csv(generated_all_csv, all_jobs)
        write_custom_hours_csv(generated_split_csv, split_jobs)

        print(f"Closed Shifts CSV: {resolved_closed_shifts}")
        print(f"All shifts CSV: {generated_all_csv} ({len(all_jobs)} rows)")
        print(f"Split-only CSV: {generated_split_csv} ({len(split_jobs)} rows)")
        print(f"Jobs queued for export: {len(jobs)} total shifts")
    else:
        resolved_plan_csv = resolve_plan_csv(args.plan_csv, args.toast_exports_root, args.report_date)
        if resolved_plan_csv != args.plan_csv:
            print(f"Plan CSV not found at requested path: {args.plan_csv}")
            print(f"Using most recent available plan CSV: {resolved_plan_csv}")
        args.plan_csv = resolved_plan_csv
        jobs = load_jobs(args.plan_csv)
        report_date = infer_report_date(args.plan_csv, jobs, args.report_date)

    if not jobs:
        print("No shift jobs found for the selected settings.")
        if generated_all_csv is not None:
            print("All-shifts and split-only CSVs were generated, but no shift rows matched the selected date.")
            return 0
        return 1

    args.export_dir.mkdir(parents=True, exist_ok=True)

    popup_proc = None
    if not args.no_popup_guard:
        popup_proc = start_popup_guard(Path(__file__).parent, args.popup_guard_seconds)
        if popup_proc is not None:
            print(f"Popup guard started for {args.popup_guard_seconds}s")
        else:
            print("Popup guard script not found; continuing without it")

    if args.delete_old and not args.list_only:
        deleted = delete_old_exports(args.export_dir, jobs, report_date)
        print(f"Deleted old shift files: {len(deleted)}")

    print("\nJobs to run:")
    for idx, job in enumerate(jobs, start=1):
        out_name = f"{job.shift_label}_{safe_token(job.employee)}_{report_date}.xlsx"
        print(f"{idx}. {job.employee} | {job.start_for_toast} -> {job.end_for_toast} | {out_name}")

    if args.list_only:
        return 0

    print("\nKeep Toast on Sales Summary. For each job:")
    print("1) Set Employee")
    print("2) Set Custom hours exactly as shown")
    print("3) Click Download -> Download Excel file")
    if args.auto_advance:
        print("4) Script auto-detects the new file and moves to the next job")
    else:
        print("4) Come back here and press Enter")


    # --- AUTOMATION INTEGRATION ---
    TOAST_URL = "https://www.toasttab.com/restaurants/admin/reports/sales/sales-summary?startDate={date}&endDate={date}&datePreset=TODAY"

    if not args.no_launch_chrome:
        # Locate Chrome — check PATH first, then known install paths
        _chrome_candidates = [
            "chrome",
            "chrome.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        chrome_path = None
        for _cp in _chrome_candidates:
            _found = shutil.which(_cp)
            if _found:
                chrome_path = _found
                break
            import os as _os
            if _os.path.isabs(_cp) and Path(_cp).exists():
                chrome_path = _cp
                break

        if not chrome_path:
            print("Chrome not found. Please open Chrome manually and press Enter to continue.")
            input()
        else:
            url_date = report_date.replace("-", "")
            url = TOAST_URL.format(date=url_date)
            print(f"Launching Chrome to: {url}")
            subprocess.Popen([chrome_path, url])
            time.sleep(5)  # Give Chrome time to load
    else:
        print("(--no-launch-chrome: skipping Chrome launch — using existing window)")

    # For each job, call automate_toast_downloads.py with employee name and hours
    for idx, job in enumerate(jobs, start=1):
        out_name = f"{job.shift_label}_{safe_token(job.employee)}_{report_date}.xlsx"
        out_path = args.export_dir / out_name

        print("\n" + "-" * 72)
        print(f"[{idx}/{len(jobs)}] {job.employee}")
        print(f"Custom hours: {job.start_for_toast} -> {job.end_for_toast}")
        print(f"Target file: {out_name}")

        # Call toast_api_downloader.py if available (REST API, no browser needed),
        # otherwise fall back to automate_toast_downloads.py (legacy pyautogui).
        api_script = Path(__file__).parent / "toast_api_downloader.py"
        api_config = Path(__file__).parent / "toast_config.json"
        legacy_script = Path(__file__).parent.parent / "automate_toast_downloads.py"

        if api_script.exists() and api_config.exists():
            cmd = [sys.executable, str(api_script),
                   "--employee", job.employee,
                   "--start", job.start_for_toast,
                   "--end", job.end_for_toast,
                   "--date", report_date,
                   "--output", str(out_path),
                   "--config", str(api_config),
                   "--verbose"]
            print(f"Running (API): {api_script.name}")
            proc = subprocess.run(cmd)
            if proc.returncode == 2:
                print("JWT expired — re-extract toast_config.json via browser and retry.")
                return 1
            elif proc.returncode != 0:
                print(f"FAILED (API): {job.employee} (rc={proc.returncode})")
                continue
            else:
                print(f"[OK] {job.employee}")
        elif legacy_script.exists():
            cmd = [sys.executable, str(legacy_script),
                   "--employee", job.employee,
                   "--start", job.start_for_toast,
                   "--end", job.end_for_toast,
                   "--output", str(out_path),
                   "--report-date", report_date]
            print(f"Running (legacy): {legacy_script.name}")
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                print(f"FAILED (legacy): {job.employee}")
                continue
            else:
                print(f"[OK] {job.employee}")
        else:
            print(f"No download script found (checked {api_script} and {legacy_script})")
            return 1

    print("\nDone.")
    return 0

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
