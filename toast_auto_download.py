#!/usr/bin/env python3
"""
Toast Sales Summary Automated Download
Handles the complete workflow for each employee
"""

import pyautogui
import time
import os
from pathlib import Path

# Configuration
TARGET_FOLDER = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers"
REPORT_DATE = "2026-05-19"

EMPLOYEES = [
    "Emileigh Salinas",
    "Blaine Roberson",
    "Bryan Garcia",
    "Indira Garcia",
    "Kiara Mccoy",
    "Kaitlyn Esfahani",
    "Bailee Pena",
    "J'Elle Longoria",
    "Alyssa Rodriguez",
    "Marissa Alvarez",
    "Lariah Saenz",
    "Isabel Garcia",
]

def format_filename(name):
    """Convert 'First Last' to 'First_Last_YYYY-MM-DD.xlsx'"""
    return f"{name.replace(' ', '_')}_{REPORT_DATE}.xlsx"

def wait_for_save_dialog(timeout=20):
    """Wait for save dialog to appear"""
    print("  ⏳ Waiting for save dialog...")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
    print("  ✓ Dialog should be ready")
    return True

def handle_save_dialog(employee_name):
    """
    Handle Windows Save As dialog:
    1. Navigate to target folder
    2. Set filename
    3. Click Save
    """
    filename = format_filename(employee_name)
    full_path = os.path.join(TARGET_FOLDER, filename)
    
    print(f"  → Automating save dialog...")
    time.sleep(0.5)
    
    # Ensure dialog is focused
    pyautogui.click(500, 400)  # Click somewhere in the dialog area
    time.sleep(0.3)
    
    # Method: Type full path directly in filename field
    # First, click on the filename field (should be already focused)
    pyautogui.click(680, 527)  # Based on screenshot coordinates
    time.sleep(0.3)
    
    # Select all existing text
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    
    # Type the full path with filename using clipboard (more reliable)
    import subprocess
    path_with_file = full_path
    
    # Copy to clipboard
    process = subprocess.Popen(['powershell', '-Command', 
        f'"{path_with_file}" | Set-Clipboard'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.wait()
    time.sleep(0.2)
    
    # Paste from clipboard
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.5)
    
    print(f"    📝 Filename set: {filename}")
    
    # Click Save button
    pyautogui.click(897, 706)  # Save button coordinates from screenshot
    time.sleep(2)
    
    # Verify
    if os.path.exists(full_path):
        print(f"    ✓ Saved successfully!")
        return True
    else:
        print(f"    ⚠ Checking file... (may be processing)")
        time.sleep(1)
        if os.path.exists(full_path):
            print(f"    ✓ File confirmed!")
            return True
        else:
            print(f"    ✗ File not found")
            return False

def download_employee_sales_summary(employee_name):
    """
    Download sales summary for one employee:
    1. Find employee in Toast
    2. Download Excel file
    3. Handle save dialog
    """
    print(f"\n  Downloading for: {employee_name}")
    time.sleep(0.5)
    
    # Step 1: Find employee (using Toast filter/search)
    print(f"  Step 1️⃣  Finding employee...")
    
    # Use browser find (Ctrl+F)
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.5)
    
    # Type first name to search
    first_name = employee_name.split()[0]
    pyautogui.typewrite(first_name, interval=0.06)
    time.sleep(0.3)
    
    pyautogui.press('enter')
    time.sleep(0.5)
    
    # Close find
    pyautogui.press('escape')
    time.sleep(0.5)
    
    # Step 2: Click download button
    print(f"  Step 2️⃣  Clicking download...")
    
    # Make sure Toast window is focused
    pyautogui.hotkey('alt', 'tab')
    time.sleep(0.3)
    
    # Click download icon (approximate location)
    # Usually top right of report area
    pyautogui.click(1050, 180)
    time.sleep(0.8)
    
    # Step 3: Select "Download Excel File"
    print(f"  Step 3️⃣  Selecting Excel download...")
    time.sleep(0.5)
    
    # Use keyboard to navigate menu
    pyautogui.press('down')
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(1)
    
    # Step 4: Handle save dialog
    print(f"  Step 4️⃣  Saving file...")
    wait_for_save_dialog()
    success = handle_save_dialog(employee_name)
    
    return success

def process_all_employees():
    """Main loop: process each employee"""
    Path(TARGET_FOLDER).mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*70)
    print("TOAST SALES SUMMARY - AUTOMATED BULK DOWNLOAD")
    print("="*70)
    print(f"📁 Saving to: {TARGET_FOLDER}")
    print(f"📅 Report date: {REPORT_DATE}")
    print(f"👥 Employees: {len(EMPLOYEES)}")
    print("="*70)
    
    # Wait for user to be ready
    input("\n⏸️  Press ENTER when Toast page is open and visible...")
    
    successful = []
    failed = []
    
    for index, employee_name in enumerate(EMPLOYEES, 1):
        print(f"\n{'─'*70}")
        print(f"[{index}/{len(EMPLOYEES)}] {employee_name}")
        print(f"{'─'*70}")
        
        try:
            if download_employee_sales_summary(employee_name):
                successful.append(employee_name)
                print(f"✅ SUCCESS")
            else:
                failed.append(employee_name)
                print(f"❌ FAILED")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  STOPPED BY USER")
            break
        
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed.append(employee_name)
        
        # Wait before next employee
        if index < len(EMPLOYEES):
            print(f"\n⏳ Ready for next employee...")
            time.sleep(2)
    
    # Final summary
    print("\n" + "="*70)
    print("FINAL REPORT")
    print("="*70)
    print(f"✅ Success: {len(successful)}/{len(EMPLOYEES)}")
    print(f"❌ Failed:  {len(failed)}/{len(EMPLOYEES)}")
    
    if successful:
        print(f"\n✅ Downloaded:")
        for name in successful:
            print(f"   • {name}")
    
    if failed:
        print(f"\n❌ Failed to download:")
        for name in failed:
            print(f"   • {name}")
    
    # Verify files
    print(f"\n{'='*70}")
    print("📋 VERIFICATION - Files in folder:")
    print(f"{'='*70}")
    
    files = sorted([f for f in os.listdir(TARGET_FOLDER) if f.endswith('.xlsx') and '_' in f])
    
    if files:
        for file in files:
            path = os.path.join(TARGET_FOLDER, file)
            size = os.path.getsize(path) / 1024
            print(f"   ✓ {file:<50} ({size:>6.1f} KB)")
    else:
        print("   No files found")
    
    print(f"{'='*70}\n")

if __name__ == "__main__":
    try:
        process_all_employees()
    except KeyboardInterrupt:
        print("\n\n⚠️  Automation stopped")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
