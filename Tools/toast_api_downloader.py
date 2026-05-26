#!/usr/bin/env python3
"""
toast_api_downloader.py — Downloads a Toast Sales Summary XLSX via the
report-generator REST API.  Replaces the old pyautogui/Chrome approach.

Usage:
    python toast_api_downloader.py \\
        --employee "Isabel Garcia" \\
        --start "10:19 AM" \\
        --end "2:50 PM" \\
        --date "2026-05-21" \\
        --output "C:\\...\\Morning_Isabel_Garcia_2026-05-21.xlsx" \\
        --config "C:\\...\\toast_config.json"

Exit codes:
    0  — success
    1  — download failed (API error, network error, etc.)
    2  — JWT expired; caller should refresh toast_config.json and retry
    3  — employee GUID not found in employee_guids.json
"""

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

LOCATION_GUID = "7b6ea663-6c82-4a7d-b305-ea7d1512a8ff"
BASE_URL = "https://www.toasttab.com"
DEFAULT_CONFIG = Path(__file__).parent / "toast_config.json"
DEFAULT_GUIDS = Path(__file__).parent / "employee_guids.json"
# Reports smaller than this are considered empty (template-only, no shift data).
EMPTY_REPORT_THRESHOLD = 18_000


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def parse_toast_time(time_str: str):
    """Parse '10:19 AM' or '4:01 PM' into (hour_24, minute)."""
    time_str = time_str.strip()
    dt = datetime.strptime(time_str, "%I:%M %p")
    return dt.hour, dt.minute


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"[toast_api] Config not found: {config_path}", file=sys.stderr)
        print("[toast_api] Run the agent refresh step to create toast_config.json.", file=sys.stderr)
        sys.exit(2)
    with config_path.open() as f:
        return json.load(f)


def check_jwt_expiry(config: dict) -> None:
    exp = config.get("expires_at", 0)
    if exp and time.time() > exp - 60:
        print("[toast_api] JWT is expired or about to expire. Refresh toast_config.json.", file=sys.stderr)
        sys.exit(2)


def load_guids(guids_path: Path) -> dict:
    if not guids_path.exists():
        print(f"[toast_api] employee_guids.json not found: {guids_path}", file=sys.stderr)
        sys.exit(3)
    with guids_path.open() as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def lookup_guids(name: str, guid_map: dict) -> list:
    key = normalize_name(name)
    if key in guid_map:
        guids = guid_map[key]
        return guids if isinstance(guids, list) else [guids]

    # Fallback: partial match on first + last word
    parts = key.split()
    for map_key, guids in guid_map.items():
        mk_parts = map_key.split()
        if parts and mk_parts and parts[0] == mk_parts[0] and parts[-1] == mk_parts[-1]:
            print(f"[toast_api] Name '{name}' matched via partial match to '{map_key}'", file=sys.stderr)
            return guids if isinstance(guids, list) else [guids]

    return []


def build_headers(config: dict) -> dict:
    return {
        "Authorization": config["authorization"],
        "Content-Type": "application/json",
        "toast-management-set-guid": config["toast-management-set-guid"],
        "toast-restaurant-external-id": config["toast-restaurant-external-id"],
        "toast-restaurant-set-guid": config["toast-restaurant-set-guid"],
    }


def build_request_body(
    employee_guid: str,
    date_str: str,
    start_hour: int,
    start_min: int,
    end_hour: int,
    end_min: int,
) -> dict:
    date_compact = date_str.replace("-", "")
    return {
        "reportName": "sales/SalesSummary",
        "locations": [[{"locationGuid": LOCATION_GUID, "locationType": "RESTAURANT"}]],
        "dateRanges": {
            "customDateRanges": [
                {"startDateYYYYMMDD": date_compact, "endDateYYYYMMDD": date_compact}
            ]
        },
        "parameters": {
            "employee": employee_guid,
            "definedHoursAndMinutes": {
                "startHourOfDay": start_hour,
                "endHourOfDay": end_hour,
                "startMinute": start_min,
                "endMinute": end_min,
            },
            "filterDiningOptions": False,
            "filterDaysOfWeek": False,
            "filterEmployees": True,
            "filterServices": False,
            "filterSources": False,
            "filterServiceAreas": False,
            "filterRevenueCenters": False,
            "filterHourOfDay": False,
            "filterHoursAndMinutes": True,
            "startHour": start_hour,
            "endHour": end_hour,
            "startMinute": start_min,
            "endMinute": end_min,
        },
        "renderer": "EXCEL",
        "dispatcher": {"type": "LIVE"},
    }


def download_report(
    headers: dict,
    body: dict,
    timeout_poll: int = 60,
) -> bytes:
    """Returns raw XLSX bytes or raises RuntimeError."""
    # Step 1: Request
    r1 = requests.post(
        f"{BASE_URL}/api/service/report-generator/v1/reportRequest",
        headers=headers,
        json=body,
        timeout=30,
    )
    if r1.status_code == 401:
        print("[toast_api] 401 Unauthorized — JWT may be expired.", file=sys.stderr)
        sys.exit(2)
    if not r1.ok:
        raise RuntimeError(f"reportRequest failed: {r1.status_code} {r1.text[:200]}")

    guid = r1.json()["reportRequestGuid"]

    # Step 2: Poll metadata
    deadline = time.time() + timeout_poll
    status = ""
    while time.time() < deadline:
        r2 = requests.get(
            f"{BASE_URL}/api/service/report-generator/v1/reportRequest/{guid}/metadata",
            headers=headers,
            timeout=15,
        )
        if not r2.ok:
            raise RuntimeError(f"metadata poll failed: {r2.status_code}")
        status = r2.json().get("status", "")
        if status == "COMPLETED":
            break
        if status == "FAILED":
            raise RuntimeError(f"Report generation FAILED: {r2.text[:200]}")
        time.sleep(1)

    if status != "COMPLETED":
        raise RuntimeError(f"Timed out waiting for report (last status: {status})")

    # Step 3: Fetch binary results
    r3 = requests.post(
        f"{BASE_URL}/api/service/report-generator/v1/reportRequest/{guid}/results",
        headers=headers,
        json={},
        timeout=30,
    )
    if not r3.ok:
        raise RuntimeError(f"results fetch failed: {r3.status_code} {r3.text[:200]}")

    return r3.content


def run() -> int:
    parser = argparse.ArgumentParser(description="Download Toast Sales Summary XLSX via API")
    parser.add_argument("--employee", required=True, help="Employee name (as in Closed Shifts CSV)")
    parser.add_argument("--start", required=True, help="Shift start time, e.g. '10:19 AM'")
    parser.add_argument("--end", required=True, help="Shift end time, e.g. '2:50 PM'")
    parser.add_argument("--date", required=True, help="Report date YYYY-MM-DD")
    parser.add_argument("--output", required=True, type=Path, help="Output .xlsx path")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to toast_config.json")
    parser.add_argument("--guids", type=Path, default=DEFAULT_GUIDS, help="Path to employee_guids.json")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    check_jwt_expiry(config)
    headers = build_headers(config)
    guid_map = load_guids(args.guids)

    guids = lookup_guids(args.employee, guid_map)
    if not guids:
        print(f"[toast_api] Employee not found: '{args.employee}'", file=sys.stderr)
        print("[toast_api] Add them to employee_guids.json or check spelling.", file=sys.stderr)
        return 3

    start_hour, start_min = parse_toast_time(args.start)
    end_hour, end_min = parse_toast_time(args.end)

    if args.verbose:
        print(f"[toast_api] Employee: {args.employee}")
        print(f"[toast_api] GUIDs to try: {guids}")
        print(f"[toast_api] Hours: {start_hour:02d}:{start_min:02d} -> {end_hour:02d}:{end_min:02d}")
        print(f"[toast_api] Date: {args.date}")
        print(f"[toast_api] Output: {args.output}")

    best_data: bytes = b""
    last_error: str = ""

    for guid in guids:
        body = build_request_body(guid, args.date, start_hour, start_min, end_hour, end_min)
        try:
            data = download_report(headers, body)
            if args.verbose:
                print(f"[toast_api]   GUID {guid}: {len(data)} bytes")
            if len(data) > len(best_data):
                best_data = data
            # If we got meaningful data, no need to try remaining GUIDs.
            if len(best_data) >= EMPTY_REPORT_THRESHOLD:
                break
        except SystemExit:
            raise
        except Exception as exc:
            last_error = str(exc)
            if args.verbose:
                print(f"[toast_api]   GUID {guid} failed: {exc}", file=sys.stderr)

    if not best_data:
        print(f"[toast_api] All GUIDs failed for {args.employee}. Last error: {last_error}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(best_data)
    size_kb = len(best_data) / 1024
    print(f"[toast_api] Saved {args.output.name} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
