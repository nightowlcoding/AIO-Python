"""One-time fixer: rewrites _download_closed_shifts.py with fresh cookies."""
import pathlib

COOKIE_STR = (
    '_gcl_au=1.1.1571235137.1777130336; _biz_uid=28bea538778d4472a7ab7064b1ee193e;'
    ' _mkto_trk=id:713-DII-842&token:_mch-toasttab.com-59b12426ab4fff9f3e38da2c248a02b6;'
    ' _fbp=fb.1.1777130336244.199100977524643245; _tt_enable_cookie=1;'
    ' _ttp=01KQ2KHW3GQXN5EWV7MZVWRA4E_.tt.1; isCustomer=1;'
    ' _gid=GA1.2.833132989.1779744324;'
    ' _rdt_uuid=1777130336216.7024b4c6-a486-454e-acd3-068b3f88d654;'
    ' _uetsid=3e203520588011f1a8b9ef50210935c7;'
    ' _uetvid=13a17d0040ba11f1826901e22a1e4f4f;'
    ' _ga=GA1.1.116597784.1777130336;'
    ' dtFrsh="6a941995-bd32_1772414369549";'
    ' _legacy_auth0.seb21ZCkhOuMQ0TXw6L6uOkt5wjIaiTL.is.authenticated=true;'
    ' auth0.seb21ZCkhOuMQ0TXw6L6uOkt5wjIaiTL.is.authenticated=true;'
    ' __utmz=216466835.1779745919.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none);'
    ' __utma=216466835.116597784.1777130336.1779745919.1779749314.2;'
    ' loginApplication=""; lastRestaurantGuid="7b6ea663-6c82-4a7d-b305-ea7d1512a8ff";'
    ' _ga_961XLTS117=GS2.1.s1779757281$o5$g1$t1779759211$j60$l0$h0;'
    ' TOAST_SESSION="a90351b04d79997b6f89838726016e5b981244cb-reportTimeEnd='
    '&uGuid=6a941995-bd32-474d-aee1-f4d8a7e84972&reportTimeRange=-2'
    '&reportEmployeeId=&reportVoided=&rUserId=100000008243765218'
    '&reportDateRange=custom&___AT=2279d8fec6520f35f262af865b05611014103587'
    '&reportShard=&reportScheduled=&___TS=2095119089587&reportState='
    '&reportGroupIds=100000005969371643&reportSource=&reportRevenueCenter='
    '&ele=19&reportDiningOption=&reportDateStart=05-21-2026&reportDiscount='
    '&reportTimeStart=&reauthenticationTime=1779757083062&rId=61477000000000000'
    '&reportServiceArea=&reportDateEnd=05-21-2026&reportService='
    '&rGuid=7b6ea663-6c82-4a7d-b305-ea7d1512a8ff&reportItemTags='
    '&msGuid=70d84ae9-ab06-4f1a-83d2-f047d0c80e0a'
    '&___ID=5f689673-136d-42bd-a4ae-6b35a47590c3'
    '&username=arnoldrjr%40gmail.com&reportTaxExempt=";'
    ' _dd_s=aid=e4af61dc-3898-4ddd-a387-bcc002dd9b34&rum=0&expire=1779760104751'
)

SCRIPT = '''\
"""
Downloads Closed Shifts CSVs from Toast old admin for all May 2026 dates
using the active browser session cookies.

Usage: python Tools/_download_closed_shifts.py
"""
import os, requests
from datetime import date, timedelta

# -- CONFIG -------------------------------------------------------------------
EXPORTS_DIR = r"C:\\Users\\arnol\\OneDrive\\Desktop\\AIO-Python\\Toast Exports"
LOCATION    = "Big House Burgers"

COOKIE_STR = {cookie!r}

# -- DATE RANGE ---------------------------------------------------------------
START_DATE = date(2026, 5, 1)
END_DATE   = date(2026, 5, 25)

# Skip dates that already have a Closed Shifts CSV
SKIP_DATES = {{"2026-05-19", "2026-05-20", "2026-05-21"}}

# -- HELPERS ------------------------------------------------------------------
def build_headers():
    return {{
        "Cookie": COOKIE_STR,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/csv,text/html,*/*",
        "Referer": "https://www.toasttab.com/restaurants/admin/reports/home",
    }}

def count_data_rows(csv_bytes: bytes) -> int:
    try:
        text = csv_bytes.decode("windows-1252", errors="replace")
    except Exception:
        text = csv_bytes.decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    return max(0, len(lines) - 1)

# -- MAIN ---------------------------------------------------------------------
session = requests.Session()
session.headers.update(build_headers())

saved = 0; skipped = 0; empty = 0; failed = 0

current = START_DATE
while current <= END_DATE:
    date_str = current.strftime("%Y-%m-%d")
    mm_dd_yyyy = current.strftime("%m-%d-%Y")

    if date_str in SKIP_DATES:
        print(f"  SKIP (already have CSV): {{date_str}}")
        skipped += 1
        current += timedelta(days=1)
        continue

    folder_name = f"{{date_str}}_{{LOCATION}}"
    folder_path = os.path.join(EXPORTS_DIR, folder_name)
    csv_filename = f"Closed_Shifts_{{date_str}}_{{LOCATION.replace(' ', '_')}}.csv"
    csv_path = os.path.join(folder_path, csv_filename)

    if os.path.exists(csv_path):
        print(f"  SKIP (file exists): {{date_str}}")
        skipped += 1
        current += timedelta(days=1)
        continue

    print(f"  Downloading: {{date_str}}", end=" ... ", flush=True)
    try:
        url = (
            f"https://www.toasttab.com/restaurants/admin/reports/closedshifts"
            f"?excel=true&reportDateStart={{mm_dd_yyyy}}&reportDateEnd={{mm_dd_yyyy}}"
        )
        resp = session.get(url, timeout=30)
        resp.raise_for_status()

        csv_bytes = resp.content
        rows = count_data_rows(csv_bytes)
        print(f"{{len(csv_bytes)}} bytes, {{rows}} rows", end=" ")

        if rows == 0:
            print("(no data -- skipping)")
            empty += 1
        else:
            os.makedirs(folder_path, exist_ok=True)
            with open(csv_path, "wb") as f:
                f.write(csv_bytes)
            print(f"-> saved to {{csv_filename}}")
            saved += 1

    except Exception as e:
        print(f"ERROR: {{e}}")
        failed += 1

    current += timedelta(days=1)

print(f"\\n=== Done: {{saved}} saved, {{skipped}} skipped, {{empty}} empty days, {{failed}} failed ===")
'''

out = SCRIPT.format(cookie=COOKIE_STR)
target = pathlib.Path(__file__).parent / "_download_closed_shifts.py"
target.write_text(out, encoding="utf-8")

import ast
ast.parse(out)
print(f"Written OK -> {target}")
print(f"Lines: {len(out.splitlines())}")
print(f"TOAST_SESSION present: {'aa8f3703e22f21e8b28c00' in out}")
