"""
Fast URL-navigation download for Jan 3, 2026 Sales Summary XLSX files.

Instead of using the UI (employee combobox + time picker), navigates directly
to the pre-built report URL with employee GUID and hours baked in.

Expected time: ~5–10 s/employee vs ~75 s/employee for the UI approach.

GUID → URL param: base64.b64encode(uuid.UUID(guid).bytes)
Hours format: 24-hour, e.g. hours=16%3A43%2C23%3A14 = 4:43 PM – 11:14 PM
"""

import asyncio
import base64
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright

DATE = "20260103"
LOCATION = "e26mY2yCSn2zBep9FRKo%2Fw%3D%3D"
BASE_URL = "https://www.toasttab.com/restaurants/admin/reports/sales/sales-summary"

OUT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-03_Big House Burgers")
DOWNLOADS = Path.home() / "Downloads"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def guid_to_param(guid_str: str) -> str:
    """UUID string → base64-encoded raw bytes → URL-encoded string."""
    return quote(base64.b64encode(uuid.UUID(guid_str).bytes).decode())


def to_24h(h: str, m: str, ampm: str) -> tuple[str, str]:
    h_int = int(h)
    if ampm == "PM" and h_int != 12:
        h_int += 12
    elif ampm == "AM" and h_int == 12:
        h_int = 0
    return str(h_int), m.zfill(2)


def build_url(guid_str: str, sh: str, sm: str, sa: str, eh: str, em: str, ea: str) -> str:
    sh24, sm2 = to_24h(sh, sm, sa)
    eh24, em2 = to_24h(eh, em, ea)
    emp_param = guid_to_param(guid_str)
    return (
        f"{BASE_URL}?utm_content=subnav"
        f"&employees={emp_param}"
        f"&hours={sh24}%3A{sm2}%2C{eh24}%3A{em2}"
        f"&startDate={DATE}&endDate={DATE}"
        f"&locations={LOCATION}"
    )


# ---------------------------------------------------------------------------
# Employee table: (guid, sh, sm, sa, eh, em, ea, filename)
# ---------------------------------------------------------------------------

EMPLOYEES = [
    # MORNING SHIFTS
    ("e13d0c10-9de1-4edd-9784-0364bca8f19a", "10", "20", "AM",  "5", "12", "PM", "Morning_Michaela_Mireles_2026-01-03.xlsx"),
    ("c4ee1c30-acdc-458d-b537-95dafd791c38", "10", "29", "AM",  "2", "51", "PM", "Morning_Alexandra_Perez_2026-01-03.xlsx"),
    ("6ba49c7c-a375-4fea-acc8-193bd4783900", "10", "29", "AM",  "3", "25", "PM", "Morning_Lariah_Saenz_2026-01-03.xlsx"),
    ("c938def8-6649-4f00-a2c4-a2b3b2375ccd", "10", "29", "AM",  "1", "27", "PM", "Morning_Kiara_Mccoy_2026-01-03.xlsx"),
    ("11263f3c-66ff-4880-b4d1-5e4ba00ea94f", "10", "30", "AM",  "5", "06", "PM", "Morning_Clarissa_Cantu_2026-01-03.xlsx"),
    ("92530978-a74c-4e46-b583-3ed746011012", "10", "30", "AM",  "5", "07", "PM", "Morning_Victoria_Cavazos_2026-01-03.xlsx"),
    ("d1d3370e-5487-4b68-ae4c-2572a7fc87ea", "10", "32", "AM",  "5", "14", "PM", "Morning_Nevaeh_Solis_2026-01-03.xlsx"),
    ("b0688001-68e5-499d-bd4f-8b58178eac9b", "11", "10", "AM",  "5", "05", "PM", "Morning_Isabella_Salinas_2026-01-03.xlsx"),
    ("2822cb4d-b342-46e0-90b4-1c2cedbea5fa", "11", "13", "AM",  "5", "00", "PM", "Morning_Luis_Alejandro_Perez_2026-01-03.xlsx"),
    # NIGHT SHIFTS
    ("6e09d45f-e509-4037-aa7c-6b2ab8cb9edf",  "4", "43", "PM", "11", "14", "PM", "Night_Kassidy_Pena_2026-01-03.xlsx"),
    ("c75d2ed4-2c8b-4e70-a73c-abaf8a173984",  "4", "44", "PM", "11", "17", "PM", "Night_Gabrielle_Salazar_2026-01-03.xlsx"),
    ("b4b1ae64-2626-4ac7-a2a7-f4c3c523bd60",  "4", "44", "PM", "11", "17", "PM", "Night_Alyssa_Garcia_2026-01-03.xlsx"),
    ("03a691e4-84e6-4666-89ce-950d8063a1cc",  "4", "45", "PM", "11", "17", "PM", "Night_Gianna_Cantu_2026-01-03.xlsx"),
    ("04aa4add-0fa5-4041-95e8-6ae95056bd69",  "4", "56", "PM", "11", "22", "PM", "Night_Elena_Escudero_2026-01-03.xlsx"),
    ("1bd514ee-2eca-4787-a648-d181307d6e4f",  "4", "59", "PM",  "8", "11", "PM", "Night_Felicity_Alaniz_2026-01-03.xlsx"),
    ("bc5392c1-5f3a-48ee-a3d0-5b1a26f094b3",  "4", "59", "PM", "10", "30", "PM", "Night_Isabel_Garcia_2026-01-03.xlsx"),
    ("2874b799-4a55-4124-8a00-297527d7eb5d",  "5", "00", "PM", "11", "22", "PM", "Night_Selena_Gomez_2026-01-03.xlsx"),
    ("e40915c5-495d-4e21-8ef3-fe942d6605a0",  "5", "04", "PM", "11", "33", "PM", "Night_Blaine_Roberson_2026-01-03.xlsx"),
]


# ---------------------------------------------------------------------------
# Download helpers (same as reference implementation)
# ---------------------------------------------------------------------------

def wait_for_new_tmp(before_files: set, timeout: int = 45) -> Path | None:
    """Poll Downloads for a new .tmp file that wasn't there before."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = set(DOWNLOADS.glob("*.tmp"))
        new = current - before_files
        if new:
            f = sorted(new, key=lambda x: x.stat().st_mtime)[-1]
            prev_size = -1
            for _ in range(15):
                time.sleep(0.5)
                try:
                    size = f.stat().st_size
                except FileNotFoundError:
                    break
                if size == prev_size and size > 1000:
                    return f
                prev_size = size
        time.sleep(0.2)
    return None


async def trigger_download(page):
    """Scroll to top, wait for Download button to be enabled, then click it."""
    await page.keyboard.press("Escape")
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(300)

    await page.locator('button[aria-label="Download report"]:not([disabled])').wait_for(timeout=15000)

    # Click via coordinate (center of download button at y=202 when scroll=0)
    await page.mouse.click(963, 202)
    await page.wait_for_timeout(1000)
    await page.get_by_text("Download Excel file").click()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        # Use the first available tab (doesn't matter which page it's on;
        # we'll navigate it ourselves via page.goto).
        target = None
        for pg in context.pages:
            if "toasttab.com" in pg.url:
                target = pg
                break
        if target is None:
            target = context.pages[0]
            print("WARNING: no toasttab.com page found, using first tab")

        await target.bring_to_front()

        total = len(EMPLOYEES)
        for i, row in enumerate(EMPLOYEES, 1):
            guid, sh, sm, sa, eh, em, ea, fname = row
            dest = OUT_DIR / fname

            if dest.exists():
                print(f"  SKIP  [{i}/{total}] {fname}")
                continue

            url = build_url(guid, sh, sm, sa, eh, em, ea)
            print(f"\n→ [{i}/{total}] {fname}")

            t0 = time.time()
            await target.goto(url, wait_until="domcontentloaded")
            await target.wait_for_timeout(2000)  # let report data load

            before = set(DOWNLOADS.glob("*.tmp"))
            await trigger_download(target)

            print("  Waiting for download…")
            tmp = wait_for_new_tmp(before, timeout=45)
            if tmp:
                tmp.rename(dest)
                elapsed = time.time() - t0
                print(f"  SAVED  {fname}  ({elapsed:.1f}s)")
            else:
                print(f"  WARNING: timeout — no file for {fname}")

            await asyncio.sleep(0.5)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
