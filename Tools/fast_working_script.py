"""
Download Toast Sales Summary XLSX files for a given day and employee list.

This keeps the working Jan 4 flow intact, but adds small reuse improvements:
- override the date and output folder from the command line
- optionally load employee rows from JSON
- use a more robust download-button click path
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_DATE = "2026-01-04"
DEFAULT_OUT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-04_Big House Burgers")
DOWNLOADS = Path.home() / "Downloads"
PAGE_URL_FRAGMENT = "sales-summary"
DOWNLOAD_MENU_XS = (963, 915, 867, 819)
ALIASES_FILE = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Tools\employee_aliases.json")

# fmt: (search_term, start_h, start_m, start_ampm, end_h, end_m, end_ampm, save_filename, match_name)
DEFAULT_EMPLOYEES = [
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


def parse_args():
    parser = argparse.ArgumentParser(description="Download Toast Sales Summary XLSX files.")
    parser.add_argument("--date", default=DEFAULT_DATE, help="Report date in YYYY-MM-DD format.")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Optional output folder. Defaults to Toast Exports/{date}_Big House Burgers.",
    )
    parser.add_argument(
        "--employees-file",
        default=None,
        help="Optional JSON file containing the employee rows for this run.",
    )
    return parser.parse_args()


def build_default_out_dir(run_date: str) -> Path:
    return Path(rf"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\{run_date}_Big House Burgers")


def load_employees(employees_file: str | None):
    if not employees_file:
        return DEFAULT_EMPLOYEES

    with open(employees_file, "r", encoding="utf-8") as handle:
        rows = json.load(handle)

    normalized = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(
                (
                    row["search_term"],
                    row["sh"],
                    row["sm"],
                    row["sa"],
                    row["eh"],
                    row["em"],
                    row["ea"],
                    row["filename"],
                    row.get("match_name"),
                )
            )
        else:
            normalized.append(tuple(row))
    return normalized


def load_aliases(aliases_file: Path | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """Load alias data as forward and reverse lookup maps."""
    aliases_file = aliases_file or ALIASES_FILE
    if not aliases_file.exists():
        return {}, {}

    with open(aliases_file, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    forward: dict[str, str] = {}
    reverse: dict[str, str] = {}
    for canonical, aliases in raw.items():
        if isinstance(aliases, list) and aliases:
            forward[canonical.casefold()] = str(aliases[0])
        reverse[canonical.casefold()] = canonical
        if isinstance(aliases, list):
            for alias in aliases:
                reverse[str(alias).casefold()] = canonical
    return forward, reverse


def resolve_alias(name: str | None, aliases: dict[str, str]) -> str | None:
    """Return the canonical name for an alias when one exists."""
    if not name:
        return name
    return aliases.get(name.casefold(), name)


def preferred_search_term(search_term: str, match_name: str | None, forward_aliases: dict[str, str]) -> str:
    """Prefer a known Toast alias when a canonical employee name has one."""
    if not match_name:
        return search_term

    preferred = forward_aliases.get(match_name.casefold())
    if preferred:
        return preferred.split()[0].title()
    return search_term


def preferred_match_name(match_name: str | None, forward_aliases: dict[str, str]) -> str | None:
    """Return the Toast-facing display name for the employee when one exists."""
    if not match_name:
        return match_name

    preferred = forward_aliases.get(match_name.casefold())
    return preferred or match_name


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
    await page.wait_for_timeout(1400)


async def open_download_menu(page):
    """Open the report export menu using the proven coordinate click path."""
    await page.keyboard.press("Escape")
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(200)

    for x in DOWNLOAD_MENU_XS:
        await page.mouse.click(x, 173)
        await page.wait_for_timeout(300)
        if await page.get_by_text("Download Excel file").count():
            return True

    try:
        await page.locator('button[aria-label="Download report"]:not([disabled])').wait_for(timeout=3000)
        await page.mouse.click(963, 202)
        await page.wait_for_timeout(400)
        return await page.get_by_text("Download Excel file").count() > 0
    except Exception:
        return False


async def trigger_download(page):
    """Scroll to top, wait for Download button to be enabled, then click it."""
    if not await open_download_menu(page):
        raise RuntimeError("Could not open the download menu")
    await page.wait_for_timeout(300)
    await page.get_by_text("Download Excel file").click()


async def main(run_date: str = DEFAULT_DATE, out_dir: Path | None = None, employees=None):
    out_dir = out_dir or build_default_out_dir(run_date)
    employees = employees or DEFAULT_EMPLOYEES
    out_dir.mkdir(parents=True, exist_ok=True)
    forward_aliases, reverse_aliases = load_aliases()

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

        total = len(employees)
        for i, row in enumerate(employees, 1):
            search_term, sh, sm, sa, eh, em, ea, fname, match_name = row
            resolved_match_name = resolve_alias(match_name, reverse_aliases)
            preferred_match = preferred_match_name(resolved_match_name, forward_aliases)
            resolved_search_term = preferred_search_term(search_term, preferred_match, forward_aliases)
            dest = out_dir / fname

            if dest.exists():
                print(f"  SKIP  [{i}/{total}] {fname}")
                continue

            print(f"\n→ [{i}/{total}] {fname}")
            print(f"  Search='{resolved_search_term}' match='{preferred_match}'  {sh}:{sm} {sa} – {eh}:{em} {ea}")

            await clear_chips(target)
            await select_employee(target, resolved_search_term, preferred_match)
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
    args = parse_args()
    run_date = args.date
    out_dir = Path(args.out_dir) if args.out_dir else None
    employees = load_employees(args.employees_file)
    asyncio.run(main(run_date=run_date, out_dir=out_dir, employees=employees))
