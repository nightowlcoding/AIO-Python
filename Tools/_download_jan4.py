"""
Download Jan 4, 2026 Sales Summary XLSX files for all 18 Big House Burgers employees.

Modeled exactly after _download_jan3.py (confirmed working reference).
Uses the Playwright browser session already open (connects via CDP on port 9222).

Shift data from Toast Closed Shifts report 01-04-2026.
Elena Escudero worked two shifts — both are included.
"""

import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright

DATE = "2026-01-04"
OUT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-04_Big House Burgers")
DOWNLOADS = Path.home() / "Downloads"
PAGE_URL_FRAGMENT = "sales-summary"

# fmt: (search_term, start_h, start_m, start_ampm, end_h, end_m, end_ampm, save_filename, match_name)
EMPLOYEES = [
    # --- MORNING SHIFTS ---
    ("Mireles",    "10",  "7", "AM",  "5",  "3", "PM", "Morning_Michaela_Mireles_2026-01-04.xlsx",      "Miki Mireles"),
    ("Felicity",   "10", "30", "AM",  "5", "21", "PM", "Morning_Felicity_Alaniz_2026-01-04.xlsx",       None),
    ("Cavazos",    "10", "30", "AM",  "3", "55", "PM", "Morning_Victoria_Cavazos_2026-01-04.xlsx",      "Vicky Cavazos"),
    ("Alexa Rae",  "10", "30", "AM",  "3", "59", "PM", "Morning_Alexa_Rae_Garcia_2026-01-04.xlsx",      "Alexa Rae"),
    ("Kiara",      "10", "31", "AM",  "3", "56", "PM", "Morning_Kiara_Mccoy_2026-01-04.xlsx",           None),
    ("Elena",      "10", "56", "AM",  "5",  "4", "PM", "Morning_Elena_Escudero_2026-01-04.xlsx",        "Elena Escudero"),
    ("Clarissa",   "11", "45", "AM",  "4", "30", "PM", "Morning_Clarissa_Cantu_2026-01-04.xlsx",        None),
    ("Dominique",  "11", "55", "AM",  "5", "22", "PM", "Morning_Dominique_Zamora_2026-01-04.xlsx",      "Dominique Zamora"),
    # --- NIGHT SHIFTS ---
    ("Arnold",      "3", "37", "PM",  "9",  "1", "PM", "Night_Katie_Arnold_2026-01-04.xlsx",            "Katie Arnold"),
    ("Isabella",    "3", "41", "PM",  "9",  "8", "PM", "Night_Isabella_Salinas_2026-01-04.xlsx",        "Isabella Salinas"),
    ("Gianna",      "3", "42", "PM",  "9",  "1", "PM", "Night_Gianna_Cantu_2026-01-04.xlsx",            None),
    ("Pena",        "3", "42", "PM",  "8", "54", "PM", "Night_Kassidy_Pena_2026-01-04.xlsx",            "Kas Pena"),
    ("Salazar",     "3", "45", "PM",  "8", "53", "PM", "Night_Gabrielle_Salazar_2026-01-04.xlsx",       "Gabby Salazar"),
    ("Alyssa",      "3", "45", "PM",  "9", "39", "PM", "Night_Alyssa_Garcia_2026-01-04.xlsx",           None),
    ("Isabel",      "4",  "6", "PM",  "9", "47", "PM", "Night_Isabel_Garcia_2026-01-04.xlsx",           "Isabel Garcia"),
    ("Selena",      "4", "59", "PM",  "9", "39", "PM", "Night_Selena_Gomez_2026-01-04.xlsx",            "Selena Gomez"),
    ("Blaine",      "4", "59", "PM", "10", "19", "PM", "Night_Blaine_Roberson_2026-01-04.xlsx",         None),
    ("Elena",       "6", "20", "PM",  "9", "38", "PM", "Night_Elena_Escudero_2026-01-04.xlsx",          "Elena Escudero"),
]


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


async def clear_chips(page):
    """Remove all current employee/time filter chips."""
    chips = await page.locator('button[aria-label*="Remove"]').all()
    for chip in chips:
        try:
            await chip.click()
            await page.wait_for_timeout(300)
        except Exception:
            pass


async def select_employee(page, search_term: str, match_name: str | None):
    """Open the Employees combobox, search, and click the right option."""
    cb = page.locator('[role="combobox"][aria-label="Employees"]')
    await cb.click()
    await page.wait_for_timeout(400)
    await page.locator('[role="searchbox"]').fill(search_term)
    await page.wait_for_timeout(800)

    options = page.locator('[role="option"]')
    if match_name:
        await options.filter(has_text=match_name).first.click()
    else:
        await options.first.click()
    await page.wait_for_timeout(400)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)


async def set_custom_hours(page, sh, sm, sa, eh, em, ea):
    """Open Custom hours picker and set start/end times."""
    await page.locator('button, [role="button"]').filter(has_text="Custom hours").click()
    await page.wait_for_timeout(800)

    # Start time
    start_h_inp = page.locator('[data-testid="start-time-hours-input"]')
    await start_h_inp.click()
    await start_h_inp.fill(sh)
    await page.keyboard.press("Tab")
    await page.locator('[data-testid="start-time-minutes-input"]').fill(sm)
    await page.keyboard.press("Tab")
    start_is_pm = await page.evaluate(
        "document.querySelector('[data-testid=\"start-time-am-pm-toggle-input-PM\"]')?.checked"
    )
    if sa == "AM" and start_is_pm:
        await page.locator('[data-testid="start-time-am-pm-toggle-input-AM"]').evaluate("el => el.click()")
    elif sa == "PM" and not start_is_pm:
        await page.locator('[data-testid="start-time-am-pm-toggle-input-PM"]').evaluate("el => el.click()")

    # End time
    end_h_inp = page.locator('[data-testid="end-time-hours-input"]')
    await end_h_inp.click()
    await end_h_inp.fill(eh)
    await page.keyboard.press("Tab")
    await page.locator('[data-testid="end-time-minutes-input"]').fill(em)
    await page.keyboard.press("Tab")
    end_is_pm = await page.evaluate(
        "document.querySelector('[data-testid=\"end-time-am-pm-toggle-input-PM\"]')?.checked"
    )
    if ea == "AM" and end_is_pm:
        await page.locator('[data-testid="end-time-am-pm-toggle-input-AM"]').evaluate("el => el.click()")
    elif ea == "PM" and not end_is_pm:
        await page.locator('[data-testid="end-time-am-pm-toggle-input-PM"]').evaluate("el => el.click()")

    await page.wait_for_timeout(300)
    await page.get_by_role("button", name="Apply").click()
    await page.wait_for_timeout(2000)


async def trigger_download(page):
    """Scroll to top, wait for Download button to be enabled, then click it."""
    await page.keyboard.press("Escape")
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(300)

    await page.locator('button[aria-label="Download report"]:not([disabled])').wait_for(timeout=10000)

    await page.mouse.click(963, 202)
    await page.wait_for_timeout(1000)
    await page.get_by_text("Download Excel file").click()


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        target = None
        for pg in context.pages:
            if PAGE_URL_FRAGMENT in pg.url:
                target = pg
                break
        if target is None:
            target = context.pages[0]
            print("WARNING: could not find sales-summary page, using first tab")

        await target.bring_to_front()

        total = len(EMPLOYEES)
        for i, row in enumerate(EMPLOYEES, 1):
            search_term, sh, sm, sa, eh, em, ea, fname, match_name = row
            dest = OUT_DIR / fname

            if dest.exists():
                print(f"  SKIP  [{i}/{total}] {fname}")
                continue

            print(f"\n→ [{i}/{total}] {fname}")
            print(f"  Search='{search_term}' match='{match_name}'  {sh}:{sm} {sa} – {eh}:{em} {ea}")

            await clear_chips(target)
            await select_employee(target, search_term, match_name)
            await set_custom_hours(target, sh, sm, sa, eh, em, ea)

            before = set(DOWNLOADS.glob("*.tmp"))
            await trigger_download(target)

            print("  Waiting for download…")
            tmp = wait_for_new_tmp(before, timeout=45)
            if tmp:
                tmp.rename(dest)
                print(f"  SAVED  {fname}")
            else:
                print(f"  WARNING: timeout — no file for {fname}")


if __name__ == "__main__":
    asyncio.run(main())
