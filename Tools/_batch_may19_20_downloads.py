"""
Batch download missing XLSX files for May 19 and May 20 using existing CustomHours CSV data.
Skips files that already exist.
"""
import csv, os, subprocess, sys

VENV_PY    = r"C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe"
API_SCRIPT  = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Tools\toast_api_downloader.py"
CONFIG      = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Tools\toast_config.json"
EXPORTS_DIR = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports"

DATES = {
    "2026-05-19": r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers\Custom_Hours_MultiShift_Only_2026-05-19_Big_House_Burgers.csv",
    "2026-05-20": r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-20_Big House Burgers\Custom_Hours_MultiShift_Only_2026-05-20_Big_House_Burgers.csv",
}

ok = 0; skip = 0; fail = 0

for date_str, csv_path in DATES.items():
    folder = os.path.join(EXPORTS_DIR, f"{date_str}_Big House Burgers")
    print(f"\n=== {date_str} ===")

    rows = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append(r)

    for row in rows:
        emp   = row["Employee"]
        start = row["StartTimeForToast"]
        end   = row["EndTimeForToast"]
        label = row["ShiftLabel"]

        safe_name = emp.replace(" ", "_").replace("'", "").replace("/", "_")
        out_file  = os.path.join(folder, f"{label}_{safe_name}_{date_str}.xlsx")

        if os.path.exists(out_file):
            print(f"  SKIP (exists): {label}_{safe_name}")
            skip += 1
            continue

        print(f"  Downloading: {emp}  {start} - {end}  ({label})", end=" ... ", flush=True)
        result = subprocess.run(
            [VENV_PY, API_SCRIPT,
             "--employee", emp,
             "--start", start, "--end", end,
             "--date", date_str,
             "--output", out_file,
             "--config", CONFIG,
             "--verbose"],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            size = os.path.getsize(out_file) // 1024
            print(f"OK ({size} KB)")
            ok += 1
        elif result.returncode == 2:
            print("JWT EXPIRED — stopping")
            sys.exit(2)
        else:
            print(f"FAILED (exit {result.returncode})")
            print(result.stdout[-400:] if result.stdout else "")
            print(result.stderr[-200:] if result.stderr else "")
            fail += 1

print(f"\n=== Done: {ok} downloaded, {skip} skipped, {fail} failed ===")
