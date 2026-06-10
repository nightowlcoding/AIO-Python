"""
Fast URL-navigation download for Jan 4, 2026 Sales Summary XLSX files.

Shift data from Toast Closed Shifts report (01-04-2026).
Elena Escudero worked two shifts — both are included.

NOTE: Katie Arnold (In 3:37 PM / Out 9:01 PM) is MISSING a GUID.
      She is not in the active employee dropdown (terminated).
      Add her entry once her GUID is found.

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

DATE = "20260104"
LOCATION = "e26mY2yCSn2zBep9FRKo%2Fw%3D%3D"
BASE_URL = "https://www.toasttab.com/restaurants/admin/reports/sales/sales-summary"

OUT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-04_Big House Burgers")
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
# Shift In/Out times from Closed Shifts report 01-04-2026.
# ---------------------------------------------------------------------------

EMPLOYEES = [
    # MORNING SHIFTS
    ("e13d0c10-9de1-4edd-9784-0364bca8f19a", "10",  "7", "AM",  "5",  "3", "PM", "Morning_Michaela_Mireles_2026-01-04.xlsx"),
    ("1bd514ee-2eca-4787-a648-d181307d6e4f", "10", "30", "AM",  "5", "21", "PM", "Morning_Felicity_Alaniz_2026-01-04.xlsx"),
    ("92530978-a74c-4e46-b583-3ed746011012", "10", "30", "AM",  "3", "55", "PM", "Morning_Victoria_Cavazos_2026-01-04.xlsx"),
    ("97b0c37d-40db-4397-bf89-eda6f8099bdd", "10", "30", "AM",  "3", "59", "PM", "Morning_Alexa_Rae_Garcia_2026-01-04.xlsx"),
    ("c938def8-6649-4f00-a2c4-a2b3b2375ccd", "10", "31", "AM",  "3", "56", "PM", "Morning_Kiara_Mccoy_2026-01-04.xlsx"),
    ("04aa4add-0fa5-4041-95e8-6ae95056bd69", "10", "56", "AM",  "5",  "4", "PM", "Morning_Elena_Escudero_2026-01-04.xlsx"),
    ("11263f3c-66ff-4880-b4d1-5e4ba00ea94f", "11", "45", "AM",  "4", "30", "PM", "Morning_Clarissa_Cantu_2026-01-04.xlsx"),
    ("676c3f34-a19f-48be-aa6f-5fafa9972b0e", "11", "55", "AM",  "5", "22", "PM", "Morning_Dominique_Zamora_2026-01-04.xlsx"),
    # TODO: Katie Arnold  In 3:37 PM / Out 9:01 PM — GUID not yet found (terminated employee)
    # NIGHT SHIFTS
    ("b0688001-68e5-499d-bd4f-8b58178eac9b",  "3", "41", "PM",  "9",  "8", "PM", "Night_Isabella_Salinas_2026-01-04.xlsx"),
    ("03a691e4-84e6-4666-89ce-950d8063a1cc",  "3", "42", "PM",  "9",  "1", "PM", "Night_Gianna_Cantu_2026-01-04.xlsx"),
    ("6e09d45f-e509-4037-aa7c-6b2ab8cb9edf",  "3", "42", "PM",  "8", "54", "PM", "Night_Kassidy_Pena_2026-01-04.xlsx"),
    ("c75d2ed4-2c8b-4e70-a73c-abaf8a173984",  "3", "45", "PM",  "8", "53", "PM", "Night_Gabrielle_Salazar_2026-01-04.xlsx"),
    ("b4b1ae64-2626-4ac7-a2a7-f4c3c523bd60",  "3", "45", "PM",  "9", "39", "PM", "Night_Alyssa_Garcia_2026-01-04.xlsx"),
    ("bc5392c1-5f3a-48ee-a3d0-5b1a26f094b3",  "4",  "6", "PM",  "9", "47", "PM", "Night_Isabel_Garcia_2026-01-04.xlsx"),
    ("2874b799-4a55-4124-8a00-297527d7eb5d",  "4", "59", "PM",  "9", "39", "PM", "Night_Selena_Gomez_2026-01-04.xlsx"),
    ("e40915c5-495d-4e21-8ef3-fe942d6605a0",  "4", "59", "PM", "10", "19", "PM", "Night_Blaine_Roberson_2026-01-04.xlsx"),
    ("04aa4add-0fa5-4041-95e8-6ae95056bd69",  "6", "20", "PM",  "9", "38", "PM", "Night_Elena_Escudero_2026-01-04.xlsx"),
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
            await target.wait_for_timeout(2000)

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


if __name__ == "__main__":
    asyncio.run(main())
