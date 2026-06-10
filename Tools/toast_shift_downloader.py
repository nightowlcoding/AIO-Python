"""
Toast Shift Downloader
Uses Playwright to download Sales Summary XLSX per shift.
Files download as .tmp — watcher catches and renames them.

HOW TO USE:
1. Set DATE and DEST_FOLDER below
2. Fill in SHIFTS list (from Shifts_Closed CSV)
3. Log into Toast in the browser Playwright opens
4. Run: python Tools/toast_shift_downloader.py
"""
import os, time, glob
from playwright.sync_api import sync_playwright

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATE         = "2026-01-02"
DEST_FOLDER  = rf"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\{DATE}_Big House Burgers"
TOAST_URL    = "https://www.toasttab.com/restaurants/admin/reports/sales/sales-summary"
DOWNLOADS    = os.path.expanduser(r"~\Downloads")

# Each shift: (file_prefix, "Employee Name", start_h, start_m, start_pm, end_h, end_m, end_pm)
# start_pm / end_pm: True = PM, False = AM
# File prefix: "Morning" if shift starts before noon, "Night" if after
SHIFTS = [
    ("Morning", "Clarissa Cantu",    10, 0,  False, 5, 55, True),
    ("Morning", "Gianna Cantu",      10, 0,  False, 5, 0,  True),
    ("Morning", "Victoria Cavazos",  10, 0,  False, 5, 11, True),
    ("Night",   "Elena Escudero",    5,  0,  True,  11, 0, True),
    # Add more shifts here...
]
# ──────────────────────────────────────────────────────────────────────────────

def watch_tmp(dest_path, timeout=45):
    """Wait for a new .tmp in Downloads, move it to dest_path."""
    before = set(glob.glob(os.path.join(DOWNLOADS, "*.tmp")))
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = set(glob.glob(os.path.join(DOWNLOADS, "*.tmp")))
        new = current - before
        if new:
            src = list(new)[0]
            time.sleep(0.8)
            os.replace(src, dest_path)
            print(f"  SAVED → {os.path.basename(dest_path)}")
            return True
        time.sleep(0.2)
    print("  TIMEOUT — file not found")
    return False

def select_employee(page, name):
    """Search by first name; fall back to last name if not found."""
    first, last = name.split()[0], name.split()[-1]
    page.locator('[data-testid="select-button"][aria-label="Employees"]').click()
    page.wait_for_timeout(600)

    for term in [first, last]:
        page.locator('[role="searchbox"]').fill(term)
        page.wait_for_timeout(800)
        opts = page.locator('[role="option"]').all_text_contents()
        match = next((o for o in opts if last.lower() in o.lower()), None)
        if match:
            page.locator('[role="option"]').filter(has_text=last).first().click()
            page.wait_for_timeout(300)
            return True

    print(f"  WARNING: '{name}' not found in Toast — skipping")
    page.keyboard.press("Escape")
    return False

def set_time(page, group_name, hour, minute, want_pm):
    """Fill hour/minute and set AM/PM for a time group."""
    h_sel = '[data-testid="start-time-hours-input"]' if "Start" in group_name else '[data-testid="end-time-hours-input"]'
    m_sel = '[data-testid="start-time-minutes-input"]' if "Start" in group_name else '[data-testid="end-time-minutes-input"]'
    pm_sel = 'start-time-am-pm-toggle-input-PM' if "Start" in group_name else 'end-time-am-pm-toggle-input-PM'

    page.locator(h_sel).click(click_count=3)
    page.keyboard.type(str(hour))
    page.keyboard.press("Tab")
    page.keyboard.type(str(minute).zfill(2) if minute < 10 else str(minute))
    page.wait_for_timeout(150)

    is_pm = page.evaluate(f'document.querySelector(\'[data-testid="{pm_sel}"]\')?.checked')
    if want_pm and not is_pm:
        page.get_by_role("group", name=group_name).locator("span").filter(has_text="PM").click()
        page.wait_for_timeout(150)
    elif not want_pm and is_pm:
        page.get_by_role("group", name=group_name).locator("span").filter(has_text="AM").click()
        page.wait_for_timeout(150)

def download_shift(page, prefix, name, sh, sm, sp, eh, em, ep):
    last_name = name.split()[-1]
    file_name = f"{prefix}_{name.replace(' ', '_')}_{DATE}.xlsx"
    dest = os.path.join(DEST_FOLDER, file_name)
    print(f"\n→ {file_name}")

    # 1. Clear previous filters
    page.locator('button', has_text="Clear all").click(timeout=2000)
    page.wait_for_timeout(300)

    # 2. Select employee
    if not select_employee(page, name):
        return

    # 3. Open Custom hours
    page.locator('button', has_text="Custom hours").click()
    page.wait_for_timeout(500)

    # 4. Set start + end times
    set_time(page, "Start time", sh, sm, sp)
    set_time(page, "End time",   eh, em, ep)

    # 5. Apply
    page.get_by_role("button", name="Apply").click()
    page.wait_for_timeout(500)

    chips = page.locator('[aria-label^="Remove "]').all_text_contents()
    print(f"  Chips: {chips}")

    # 6. Download
    page.wait_for_timeout(3000)
    page.mouse.click(963, 173)
    page.wait_for_timeout(1000)
    page.get_by_text("Download Excel file").click()

    # 7. Catch .tmp and save
    watch_tmp(dest)

def main():
    os.makedirs(DEST_FOLDER, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(TOAST_URL)

        input("\n  Log into Toast, navigate to Sales Summary, then press Enter...")

        for shift in SHIFTS:
            prefix, name, sh, sm, sp, eh, em, ep = shift
            download_shift(page, prefix, name, sh, sm, sp, eh, em, ep)

        print("\n✓ All shifts done.")
        browser.close()

if __name__ == "__main__":
    main()
