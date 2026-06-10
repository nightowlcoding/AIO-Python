"""
Download Jan 3, 2026 Sales Summary XLSX files for all 18 Big House Burgers employees.

REFERENCE IMPLEMENTATION — confirmed working May 26, 2026.
Uses the Playwright browser session already open (connects via CDP on port 9222).

Key patterns confirmed working:
  - Employee combobox: [role="combobox"][aria-label="Employees"]
  - Search box: [role="searchbox"]
  - Time inputs: data-testid="start-time-hours-input" etc.
  - AM/PM toggle: data-testid="start-time-am-pm-toggle-input-PM" → .evaluate(el => el.click())
  - Pre-download: Escape + window.scrollTo(0,0) + waitFor Download button not disabled
  - Download button coordinate: mouse.click(963, 202) then getByText('Download Excel file')
  - File watcher: watches Downloads/*.tmp for new files
"""

import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright

DATE = "2026-01-03"
OUT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-03_Big House Burgers")
DOWNLOADS = Path.home() / "Downloads"
PAGE_URL_FRAGMENT = "sales-summary"

# fmt: (search_term, start_h, start_m, start_ampm, end_h, end_m, end_ampm, save_filename)
# search_term: what to type in the employee search box
# If there are multiple results, the script picks the one whose display name contains `match_name`.
# match_name is optional (None = pick first result).
EMPLOYEES = [
    # --- MORNING SHIFTS ---
    ("Mireles",    "10", "20", "AM", "5",  "12", "PM", "Morning_Michaela_Mireles_2026-01-03.xlsx",    "Miki Mireles"),
    ("Alexandra",  "10", "29", "AM", "2",  "51", "PM", "Morning_Alexandra_Perez_2026-01-03.xlsx",     None),
    ("Lariah",     "10", "29", "AM", "3",  "25", "PM", "Morning_Lariah_Saenz_2026-01-03.xlsx",        None),
    ("Kiara",      "10", "29", "AM", "1",  "27", "PM", "Morning_Kiara_Mccoy_2026-01-03.xlsx",         None),
    ("Clarissa",   "10", "30", "AM", "5",  "06", "PM", "Morning_Clarissa_Cantu_2026-01-03.xlsx",      None),
    ("Cavazos",    "10", "30", "AM", "5",  "07", "PM", "Morning_Victoria_Cavazos_2026-01-03.xlsx",    "Vicky Cavazos"),
    ("Nevaeh",     "10", "32", "AM", "5",  "14", "PM", "Morning_Nevaeh_Solis_2026-01-03.xlsx",        "Nevaeh Solis"),
    ("Isabella",   "11", "10", "AM", "5",  "05", "PM", "Morning_Isabella_Salinas_2026-01-03.xlsx",    "Isabella Salinas"),
    ("Luis",       "11", "13", "AM", "5",  "00", "PM", "Morning_Luis_Alejandro_Perez_2026-01-03.xlsx","Luis Alejandro"),
    # --- NIGHT SHIFTS ---
    ("Pena",       "4",  "43", "PM", "11", "14", "PM", "Night_Kassidy_Pena_2026-01-03.xlsx",          "Kas Pena"),
    ("Salazar",    "4",  "44", "PM", "11", "17", "PM", "Night_Gabrielle_Salazar_2026-01-03.xlsx",     "Gabby Salazar"),
    ("Alyssa",     "4",  "44", "PM", "11", "17", "PM", "Night_Alyssa_Garcia_2026-01-03.xlsx",         None),
    ("Gianna",     "4",  "45", "PM", "11", "17", "PM", "Night_Gianna_Cantu_2026-01-03.xlsx",          None),
    ("Elena",      "4",  "56", "PM", "11", "22", "PM", "Night_Elena_Escudero_2026-01-03.xlsx",        "Elena Escudero"),
    ("Felicity",   "4",  "59", "PM", "8",  "11", "PM", "Night_Felicity_Alaniz_2026-01-03.xlsx",       None),
    ("Isabel",     "4",  "59", "PM", "10", "30", "PM", "Night_Isabel_Garcia_2026-01-03.xlsx",         "Isabel Garcia"),
    ("Selena",     "5",  "00", "PM", "11", "22", "PM", "Night_Selena_Gomez_2026-01-03.xlsx",          "Selena Gomez"),
    ("Blaine",     "5",  "04", "PM", "11", "33", "PM", "Night_Blaine_Roberson_2026-01-03.xlsx",       None),
]


def wait_for_new_tmp(before_files: set, timeout: int = 45) -> Path | None:
    """Poll Downloads for a new .tmp file that wasn't there before."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = set(DOWNLOADS.glob("*.tmp"))
        new = current - before_files
        if new:
            f = sorted(new, key=lambda x: x.stat().st_mtime)[-1]
            # Wait for stable size
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

    # Click via coordinate (center of 5th action button at y=182 when scroll=0)
    await page.mouse.click(963, 202)
    await page.wait_for_timeout(1000)
    await page.get_by_text("Download Excel file").click()


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        # Find the Sales Summary page
        target = None
        for pg in context.pages:
            if PAGE_URL_FRAGMENT in pg.url:
                target = pg
                break
        if target is None:
            target = context.pages[0]
            print("WARNING: could not find sales-summary page, using first tab")

        await target.bring_to_front()

        for row in EMPLOYEES:
            search_term, sh, sm, sa, eh, em, ea, fname, match_name = row
            dest = OUT_DIR / fname

            if dest.exists():
                print(f"  SKIP  {fname}")
                continue

            print(f"\n→ {fname}")
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
                print(f"  SAVED {fname}")
            else:
                print(f"  WARNING: timeout — no file for {fname}")

            await asyncio.sleep(1)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
