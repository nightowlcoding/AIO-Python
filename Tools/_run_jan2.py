"""Download all remaining Jan 2 XLSX reports using session cookies."""
import requests, json, time, sys
from pathlib import Path

OUT = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-02_Big House Burgers")
COOKIES_FILE = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Tools\toast_cookies.txt")
LOCATION = "7b6ea663-6c82-4a7d-b305-ea7d1512a8ff"
BASE = "https://www.toasttab.com"

# (filename, guid, start_h, start_m, end_h, end_m)
EMPLOYEES = [
    ("Clarissa_Cantu_2026-01-02.xlsx",    "11263f3c-66ff-4880-b4d1-5e4ba00ea94f", 10, 31, 16, 59),
    ("Gianna_Cantu_2026-01-02.xlsx",      "03a691e4-84e6-4666-89ce-950d8063a1cc", 10, 32, 17, 43),
    ("Elena_Escudero_2026-01-02.xlsx",    "04aa4add-0fa5-4041-95e8-6ae95056bd69", 16, 23, 23, 17),
    ("Kassidy_Pena_2026-01-02.xlsx",      "6e09d45f-e509-4037-aa7c-6b2ab8cb9edf", 16, 26, 23, 17),
    ("Isabella_Salinas_2026-01-02.xlsx",  "b0688001-68e5-499d-bd4f-8b58178eac9b", 16, 29, 23, 17),
    ("Sarah_Moralez_2026-01-02.xlsx",     "b64b560c-fd0f-47e0-955e-927c14aa110f", 16, 30, 23, 17),
    ("Gabrielle_Salazar_2026-01-02.xlsx", "c75d2ed4-2c8b-4e70-a73c-abaf8a173984", 16, 45, 23, 17),
    ("Isabel_Garcia_2026-01-02.xlsx",     "bc5392c1-5f3a-48ee-a3d0-5b1a26f094b3", 16, 57, 21, 10),
    ("Michaela_Mireles_2026-01-02.xlsx",  "e13d0c10-9de1-4edd-9784-0364bca8f19a", 17,  0, 20, 33),
    ("Selena_Gomez_2026-01-02.xlsx",      "2874b799-4a55-4124-8a00-297527d7eb5d", 17,  3, 23,  0),
    ("Evening_Victoria_Cavazos_2026-01-02.xlsx","92530978-a74c-4e46-b583-3ed746011012", 17, 11, 20, 41),
    ("Lainey_Pickard_2026-01-02.xlsx",    "add3ff21-6767-4875-9268-1b6daf125da9", 17, 31, 23, 17),
]

cookies = {}
for line in COOKIES_FILE.read_text().splitlines():
    if '=' in line:
        k, _, v = line.partition('=')
        cookies[k.strip()] = v.strip()

headers = {"Content-Type": "application/json"}
OUT.mkdir(parents=True, exist_ok=True)

for fname, guid, sh, sm, eh, em in EMPLOYEES:
    dest = OUT / fname
    if dest.exists():
        print(f"SKIP {fname}")
        continue
    print(f"  {fname}...", end=" ", flush=True)
    body = {
        "reportName": "sales/SalesSummary",
        "locations": [[{"locationGuid": LOCATION, "locationType": "RESTAURANT"}]],
        "dateRanges": {"customDateRanges": [{"startDateYYYYMMDD": "20260102", "endDateYYYYMMDD": "20260102"}]},
        "parameters": {
            "employee": guid,
            "definedHoursAndMinutes": {"startHourOfDay": sh, "endHourOfDay": eh, "startMinute": sm, "endMinute": em},
            "filterEmployees": True, "filterHoursAndMinutes": True,
            "filterDiningOptions": False, "filterDaysOfWeek": False,
            "filterServices": False, "filterSources": False,
            "filterServiceAreas": False, "filterRevenueCenters": False, "filterHourOfDay": False,
            "startHour": sh, "endHour": eh, "startMinute": sm, "endMinute": em,
        },
        "renderer": "EXCEL",
        "dispatcher": {"type": "LIVE"},
    }
    r = requests.post(f"{BASE}/api/service/report-generator/v1/reportRequest", headers=headers, json=body, cookies=cookies, timeout=30)
    if not r.ok:
        print(f"FAIL {r.status_code}"); continue
    guid_r = r.json()["reportRequestGuid"]
    for _ in range(60):
        m = requests.get(f"{BASE}/api/service/report-generator/v1/reportRequest/{guid_r}/metadata", headers=headers, cookies=cookies, timeout=15)
        if m.json().get("status") == "COMPLETED": break
        time.sleep(1)
    r3 = requests.post(f"{BASE}/api/service/report-generator/v1/reportRequest/{guid_r}/results", headers=headers, json={}, cookies=cookies, timeout=30)
    if r3.ok and len(r3.content) > 1000:
        dest.write_bytes(r3.content)
        print(f"OK ({len(r3.content):,} bytes)")
    else:
        print(f"FAIL size={len(r3.content)}")
