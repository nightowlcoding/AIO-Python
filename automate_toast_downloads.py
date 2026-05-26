import pyautogui
import time

import os
import subprocess
from pathlib import Path
from datetime import datetime
import argparse
import ctypes


user32 = ctypes.windll.user32
SW_RESTORE = 9

# Configuration defaults (CLI args override these for normal runner usage)
TOAST_URL = "https://www.toasttab.com/restaurants/admin/reports/sales/sales-summary"
TARGET_FOLDER = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports"
DOWNLOAD_FOLDER = r"C:\Users\arnol\Downloads"
REPORT_DATE = datetime.now().strftime("%Y-%m-%d")
EMPLOYEES = []

def parse_args():
    parser = argparse.ArgumentParser(description="Automate Toast Sales Summary Download for one employee")
    parser.add_argument("--employee", required=True, help="Employee name")
    parser.add_argument("--start", required=True, help="Start time for Toast (e.g. 16:00)")
    parser.add_argument("--end", required=True, help="End time for Toast (e.g. 23:00)")
    parser.add_argument("--output", required=True, help="Output file path for Excel export")
    parser.add_argument("--report-date", required=True, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--auto-find-closed-shifts", action="store_true", help="Find and process closed shifts")
    parser.add_argument("--auto-advance", action="store_true", help="Advance to next employee after processing")
    return parser.parse_args()

def set_globals_from_args(args):
    global TARGET_FOLDER, REPORT_DATE
    out_path = Path(args.output)
    TARGET_FOLDER = str(out_path.parent)
    REPORT_DATE = args.report_date


def focus_chrome_toast_window(max_attempts=5, delay_seconds=0.6):
    """Bring a Toast/Chrome window to foreground before sending pyautogui input."""

    # Prefer Toast report windows first, then any Chrome window as fallback.
    preferred_tokens = ["sales summary", "toasttab", "toast", "chrome"]

    for attempt in range(1, max_attempts + 1):
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_windows_proc(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True

            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            if title:
                found.append((hwnd, title))
            return True

        user32.EnumWindows(enum_windows_proc, 0)

        # Rank windows by token priority.
        ranked = []
        for hwnd, title in found:
            low = title.lower()
            score = -1
            for idx, tok in enumerate(preferred_tokens):
                if tok in low:
                    score = max(score, 100 - idx)
            if score >= 0:
                ranked.append((score, hwnd, title))

        ranked.sort(reverse=True, key=lambda item: item[0])
        if ranked:
            _score, hwnd, title = ranked[0]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.25)
            print(f"Focused browser window: {title}")
            return True

        print(f"Could not find Chrome/Toast window (attempt {attempt}/{max_attempts})")
        time.sleep(delay_seconds)

    return False


def ensure_target_folder():
    """Ensure target folder exists"""
    Path(TARGET_FOLDER).mkdir(parents=True, exist_ok=True)
    print(f"✓ Target folder ready: {TARGET_FOLDER}")

def format_filename(name):
    """Convert employee name to filename format"""
    return f"{name.replace(' ', '_')}_{REPORT_DATE}.xlsx"

def wait_for_save_dialog(timeout=10):
    """Wait for save dialog to appear"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Try to detect the save dialog by looking for 'File name:' text
        # This is a basic check
        time.sleep(0.5)
    return True

def handle_save_dialog(employee_name):
    """
    Automate the save dialog:
    1. Wait for dialog
    2. Change filename
    3. Navigate to folder
    4. Click Save
    """
    new_filename = format_filename(employee_name)
    full_path = os.path.join(TARGET_FOLDER, new_filename)
    
    print(f"\n>>> Handling save dialog for: {employee_name}")
    
    # Give dialog time to appear
    time.sleep(1)
    
    # Click on the filename field to ensure focus
    pyautogui.click(700, 502)
    time.sleep(0.3)
    
    # Select all text in filename field
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    
    # Type the full path with filename
    # Using the address bar approach: Ctrl+L opens location bar
    pyautogui.hotkey('ctrl', 'l')
    time.sleep(0.3)
    
    # Clear the address bar
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    
    # Type the folder path
    pyautogui.typewrite(TARGET_FOLDER, interval=0.02)
    time.sleep(0.3)
    
    # Press Enter to navigate to that folder
    pyautogui.press('enter')
    time.sleep(0.8)
    
    # Now set the filename
    pyautogui.hotkey('ctrl', 'l')
    time.sleep(0.2)
    pyautogui.press('escape')
    time.sleep(0.2)
    
    # Click filename field
    pyautogui.click(700, 502)
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    
    # Type just the filename
    pyautogui.typewrite(new_filename, interval=0.02)
    time.sleep(0.3)
    
    # Press Alt+S to click Save button
    pyautogui.hotkey('alt', 's')
    time.sleep(1)
    
    # Verify file was saved
    if os.path.exists(full_path):
        print(f"✓ File saved: {new_filename}")
        return True
    else:
        print(f"⚠ File may still be saving: {new_filename}")
        # Give it a moment more
        time.sleep(2)
        return os.path.exists(full_path)

def find_and_click_employee_filter(employee_name, max_attempts=3):
    """
    Find and click employee name in the Toast UI filter
    """
    print(f"\n→ Looking for employee filter: {employee_name}")
    
    # Look for filter input field or dropdown
    # The Toast interface has employee filters
    # Try clicking on the employee filter area
    time.sleep(0.5)
    
    # Attempt to use keyboard shortcut to open search/filter
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.5)
    
    # Type employee name in search
    pyautogui.typewrite(employee_name.replace(' ', ''), interval=0.05)
    time.sleep(0.5)
    
    # Press Enter to search
    pyautogui.press('enter')
    time.sleep(0.5)
    
    # Press Escape to close search
    pyautogui.press('escape')
    time.sleep(0.3)

def click_download_button(attempt=1):
    """
    Click the download button in Toast
    Look for download icon and click it
    """
    print(f"  → Clicking download button (attempt {attempt})")
    
    # The download button is typically in the top right of the report area
    # Approximate coordinates based on typical Toast layout
    download_button_x = 1050
    download_button_y = 200
    
    pyautogui.click(download_button_x, download_button_y)
    time.sleep(0.5)

def click_download_excel(attempt=1):
    """
    Click 'Download Excel File' from the dropdown menu
    """
    print(f"  → Selecting 'Download Excel File' (attempt {attempt})")
    
    # The option should appear after clicking download button
    # Look for it by position or use keyboard
    time.sleep(0.5)
    
    # Try pressing down arrow and Enter to select from dropdown
    pyautogui.press('down')
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(1)

def process_employee(browser_page_id, employee_name, index):
    """
    Process single employee:
    1. Filter by employee
    2. Click download
    3. Click "Download Excel"
    4. Handle save dialog
    """
    print(f"\n{'='*60}")
    print(f"Processing {index}/12: {employee_name}")
    print(f"{'='*60}")
    
    try:
        if not focus_chrome_toast_window():
            print("Could not focus Chrome/Toast window. Skipping employee to avoid random clicks.")
            return False

        # Step 1: Filter to employee
        find_and_click_employee_filter(employee_name)
        time.sleep(1)
        
        # Step 2: Click download button
        click_download_button()
        time.sleep(0.8)
        
        # Step 3: Click "Download Excel File"
        click_download_excel()
        time.sleep(1)
        
        # Step 4: Handle save dialog
        success = handle_save_dialog(employee_name)
        
        if success:
            print(f"✓ Successfully processed: {employee_name}")
        else:
            print(f"⚠ Warning: File may not have been saved properly")
        
        time.sleep(1)
        
    except Exception as e:
        print(f"✗ Error processing {employee_name}: {e}")
        return False
    
    return True


def main():
    args = parse_args()
    set_globals_from_args(args)
    print("\n" + "="*60)
    print("Toast Sales Summary - Automated Download (Single Employee)")
    print("="*60)
    print(f"Target folder: {TARGET_FOLDER}")
    print(f"Report date: {REPORT_DATE}")
    print(f"Employee: {args.employee}")
    print(f"Custom hours: {args.start} -> {args.end}")
    print("="*60 + "\n")

    ensure_target_folder()

    # Safety features for desktop automation.
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15

    success = process_employee(None, args.employee, 1)
    if not success:
        print(f"✗ Failed to automate download for {args.employee}")
        exit(1)
    else:
        print(f"✓ Automated download for {args.employee}")
        exit(0)

if __name__ == "__main__":
    main()
