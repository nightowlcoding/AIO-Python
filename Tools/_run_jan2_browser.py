"""Search by name, set hours, click Download Excel, move .tmp to correct name."""
import time, os, glob, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-02_Big House Burgers")
DL  = Path.home() / "Downloads"

EMPLOYEES = [
    ("Clarissa", "10","31","AM","4", "59","PM","Clarissa_Cantu_2026-01-02.xlsx"),
    ("Gianna",   "10","32","AM","5", "43","PM","Gianna_Cantu_2026-01-02.xlsx"),
    ("Elena",    "4", "23","PM","11","17","PM","Elena_Escudero_2026-01-02.xlsx"),
    ("Kassidy",  "4", "26","PM","11","17","PM","Kassidy_Pena_2026-01-02.xlsx"),
    ("Isabella", "4", "29","PM","11","17","PM","Isabella_Salinas_2026-01-02.xlsx"),
    ("Sarah",    "4", "30","PM","11","17","PM","Sarah_Moralez_2026-01-02.xlsx"),
    ("Gabby",    "4", "45","PM","11","17","PM","Gabrielle_Salazar_2026-01-02.xlsx"),
    ("Isabel",   "4", "57","PM","9", "10","PM","Isabel_Garcia_2026-01-02.xlsx"),
    ("Michaela", "5", "00","PM","8", "33","PM","Michaela_Mireles_2026-01-02.xlsx"),
    ("Selena",   "5", "03","PM","11","00","PM","Selena_Gomez_2026-01-02.xlsx"),
    ("Lainey",   "5", "31","PM","11","17","PM","Lainey_Pickard_2026-01-02.xlsx"),
]

def get_tmps():
    return set(DL.glob("*.tmp"))

def wait_for_tmp(before, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        after = get_tmps()
        new = after - before
        if new:
            f = list(new)[0]
            prev = -1
            for _ in range(15):
                time.sleep(0.4)
                try:
                    s = f.stat().st_size
                    if s == prev and s > 1000:
                        return f
                    prev = s
                except FileNotFoundError:
                    break
        time.sleep(0.3)
    return None

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    page = browser.contexts[0].pages[0]
    for ctx_page in browser.contexts[0].pages:
        if "sales-summary" in ctx_page.url:
            page = ctx_page
            break

    OUT.mkdir(parents=True, exist_ok=True)

    for search, sh, sm, sa, eh, em, ea, fname in EMPLOYEES:
        dest = OUT / fname
        if dest.exists():
            print(f"SKIP {fname}"); continue

        print(f"  {search}...", end=" ", flush=True)

        # Clear existing employee
        for btn in page.locator('[aria-label*="Remove"]').all():
            btn.click()
        # Clear time filter
        for tag in page.locator('button:has-text("AM"), button:has-text("PM")').all():
            try: tag.click()
            except: pass

        # Search employee
        page.locator('button:has-text("Employees")').first.click()
        page.wait_for_timeout(300)
        page.get_by_role('searchbox').fill(search)
        page.wait_for_timeout(600)
        page.get_by_role('option').first.click()
        page.wait_for_timeout(300)

        # Set custom hours
        page.locator('button:has-text("Custom hours")').click()
        page.wait_for_timeout(400)
        boxes = page.get_by_role('textbox').all()
        boxes[0].click(click_count=3); boxes[0].fill(sh)
        boxes[1].click(click_count=3); boxes[1].fill(sm)
        boxes[2].click(click_count=3); boxes[2].fill(eh)
        boxes[3].click(click_count=3); boxes[3].fill(em)

        # AM/PM
        toggles = page.locator('div.group').filter(has_text='AMPM').all()
        if len(toggles) > 0: toggles[0].locator(f'span:has-text("{sa}")').first.click()
        if len(toggles) > 1: toggles[1].locator(f'span:has-text("{ea}")').first.click()

        page.locator('button:has-text("Apply")').click()
        page.wait_for_timeout(1000)

        # Click download
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(200)
        page.locator('[aria-label*="ownload"], [aria-label*="xport"]').first.click()
        page.wait_for_timeout(300)

        before = get_tmps()
        page.locator('text=Download Excel file').click()

        tmp = wait_for_tmp(before, timeout=35)
        if tmp:
            shutil.move(str(tmp), str(dest))
            print(f"saved ({dest.stat().st_size:,} bytes)")
        else:
            print(f"NO FILE - check manually")

        page.wait_for_timeout(800)
