"""
Download Jan 2 Sales Summary XLSX files for all remaining employees.
Uses the Playwright browser session already open.
"""
import asyncio
import glob
import os
import time
from pathlib import Path
from playwright.async_api import async_playwright

OUT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-02_Big House Burgers")
DOWNLOADS = Path.home() / "Downloads"

# (name_to_search, start_hour, start_min, start_ampm, end_hour, end_min, end_ampm, save_name)
EMPLOYEES = [
    ("Clarissa Cantu",  "10", "31", "AM", "4",  "59", "PM", "Clarissa_Cantu_2026-01-02.xlsx"),
    ("Gianna Cantu",    "10", "32", "AM", "5",  "43", "PM", "Gianna_Cantu_2026-01-02.xlsx"),
    ("Elena Escudero",  "4",  "23", "PM", "11", "17", "PM", "Elena_Escudero_2026-01-02.xlsx"),
    ("Kassidy Pena",    "4",  "26", "PM", "11", "17", "PM", "Kassidy_Pena_2026-01-02.xlsx"),
    ("Isabella Salinas","4",  "29", "PM", "11", "17", "PM", "Isabella_Salinas_2026-01-02.xlsx"),
    ("Sarah Moralez",   "4",  "30", "PM", "11", "17", "PM", "Sarah_Moralez_2026-01-02.xlsx"),
    ("Gabrielle Salazar","4", "45", "PM", "11", "17", "PM", "Gabrielle_Salazar_2026-01-02.xlsx"),
    ("Isabel Garcia",   "4",  "57", "PM", "9",  "10", "PM", "Isabel_Garcia_2026-01-02.xlsx"),
    ("Michaela Mireles","5",  "00", "PM", "8",  "33", "PM", "Michaela_Mireles_2026-01-02.xlsx"),
    ("Selena Gomez",    "5",  "03", "PM", "11", "00", "PM", "Selena_Gomez_2026-01-02.xlsx"),
    ("Victoria Cavazos","5",  "11", "PM", "8",  "41", "PM", "Evening_Victoria_Cavazos_2026-01-02.xlsx"),
    ("Lainey Pickard",  "5",  "31", "PM", "11", "17", "PM", "Lainey_Pickard_2026-01-02.xlsx"),
]

def wait_for_new_tmp(before_files: set, timeout=30) -> Path | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = set(DOWNLOADS.glob("*.tmp"))
        new = current - before_files
        if new:
            f = list(new)[0]
            # Wait for it to finish writing (stable size)
            prev_size = -1
            for _ in range(10):
                time.sleep(0.5)
                try:
                    size = f.stat().st_size
                except FileNotFoundError:
                    break
                if size == prev_size and size > 1000:
                    return f
                prev_size = size
        time.sleep(0.3)
    return None

async def set_employee(page, name):
    # Remove current employee if any
    tags = await page.locator('[aria-label*="Remove"], button.dismiss').all()
    for t in tags:
        await t.click()

    # Click Employees dropdown
    await page.locator('button:has-text("Employees"), [aria-label*="Employees"]').first.click()
    await page.wait_for_timeout(300)

    # Type name
    await page.get_by_role('searchbox').fill(name)
    await page.wait_for_timeout(500)

    # Click first result
    option = page.get_by_role('option').first
    await option.click()
    await page.wait_for_timeout(300)

async def remove_time_filter(page):
    # Click the time tag to remove it if present
    time_tag = page.locator('text=AM - ').first
    if await time_tag.count() > 0:
        await time_tag.click()
        await page.wait_for_timeout(200)

async def set_hours(page, sh, sm, sa, eh, em, ea):
    # Open Custom hours
    await page.locator('button:has-text("Custom hours")').click()
    await page.wait_for_timeout(400)

    boxes = await page.get_by_role('textbox').all()
    # boxes[0]=start hour, [1]=start min, [2]=end hour, [3]=end min
    await boxes[0].click(click_count=3); await boxes[0].fill(sh)
    await boxes[1].click(click_count=3); await boxes[1].fill(sm)
    await boxes[2].click(click_count=3); await boxes[2].fill(eh)
    await boxes[3].click(click_count=3); await boxes[3].fill(em)

    # Set AM/PM for start
    toggles = await page.locator('div.group').filter(has_text='AMPM').all()
    start_toggle = toggles[0]
    end_toggle = toggles[1]

    start_btn = start_toggle.locator(f'span:has-text("{sa}"), div:has-text("{sa}")').first
    await start_btn.click()
    end_btn = end_toggle.locator(f'span:has-text("{ea}"), div:has-text("{ea}")').first
    await end_btn.click()

    await page.wait_for_timeout(200)
    await page.locator('button:has-text("Apply")').click()
    await page.wait_for_timeout(800)

async def click_download_excel(page):
    await page.evaluate("window.scrollTo(0,0)")
    await page.wait_for_timeout(300)
    await page.locator('[aria-label*="download"], [aria-label*="Download"], [aria-label*="export"]').first.click()
    await page.wait_for_timeout(400)
    await page.locator('text=Download Excel file').click()

async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Connect to existing browser session via CDP
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        # Find the Sales Summary page
        target = None
        for pg in context.pages:
            if "sales-summary" in pg.url or "reports" in pg.url:
                target = pg
                break
        if not target:
            target = context.pages[0]

        await target.bring_to_front()

        for (name, sh, sm, sa, eh, em, ea, fname) in EMPLOYEES:
            dest = OUT_DIR / fname
            if dest.exists():
                print(f"  SKIP {fname} (already exists)")
                continue

            print(f"\n--- {name} ({sh}:{sm} {sa} - {eh}:{em} {ea}) ---")

            # Remove existing time filter
            await remove_time_filter(target)

            # Set employee
            await set_employee(target, name)

            # Set hours
            await set_hours(target, sh, sm, sa, eh, em, ea)

            # Snapshot Downloads before
            before = set(DOWNLOADS.glob("*.tmp"))

            # Click download
            await click_download_excel(target)

            # Wait for .tmp
            print(f"  Waiting for file...")
            tmp = wait_for_new_tmp(before, timeout=30)
            if tmp:
                tmp.rename(dest)
                print(f"  Saved: {fname}")
            else:
                print(f"  WARNING: no file found for {name}")

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
