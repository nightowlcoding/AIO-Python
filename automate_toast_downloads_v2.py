import pyautogui
import time
import os
import win32gui
import win32con
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
    """Convert employee name to filename format"""
    return f"{name.replace(' ', '_')}_{REPORT_DATE}.xlsx"

def find_save_dialog():
    """Find the Windows Save As dialog window"""
    try:
        hwnd = win32gui.FindWindow("#32770", "Save As")
        if hwnd:
            return hwnd
    except:
        pass
    
    # Try alternative dialog titles
    for title in ["Save", "Save As", "Export File"]:
        try:
            hwnd = win32gui.FindWindow("#32770", title)
            if hwnd:
                return hwnd
        except:
            pass
    
    return None

def handle_save_dialog_robust(employee_name):
    """
    More robust save dialog handling using direct window focus
    """
    new_filename = format_filename(employee_name)
    full_path = os.path.join(TARGET_FOLDER, new_filename)
    
    print(f"  Handling save dialog for: {employee_name}")
    
    # Find and focus the save dialog
    hwnd = find_save_dialog()
    if hwnd:
        print(f"    Dialog found, bringing to focus...")
        try:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        except:
            pass
    
    # Method 1: Use keyboard to navigate
    # Ctrl+L opens the location bar in file dialogs
    pyautogui.hotkey('ctrl', 'l')
    time.sleep(0.4)
    
    # Clear existing path
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    
    # Type folder path using slower input to avoid issues
    for char in TARGET_FOLDER:
        pyautogui.press(char) if char.isalnum() else pyautogui.typewrite(char, interval=0.01)
        time.sleep(0.02)
    
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(0.8)
    
    # Now handle the filename field
    # Tab to filename field or click on it
    pyautogui.press('tab')
    time.sleep(0.3)
    
    # Select all and replace filename
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    
    # Type the filename more carefully
    for char in new_filename:
        if char == '_':
            pyautogui.hotkey('shift', 'underscore')
        elif char == '.':
            pyautogui.press('period')
        else:
            pyautogui.typewrite(char, interval=0.02)
        time.sleep(0.01)
    
    time.sleep(0.5)
    
    # Click Save button (Alt+S)
    pyautogui.hotkey('alt', 's')
    time.sleep(2)
    
    # Check if file was saved
    if os.path.exists(full_path):
        print(f"    ✓ Saved: {new_filename}")
        return True
    else:
        print(f"    ⚠ File not confirmed yet: {new_filename}")
        time.sleep(1)
        return os.path.exists(full_path)

def monitor_for_save_dialog(employee_name, timeout=15):
    """
    Wait for save dialog and handle it
    """
    start_time = time.time()
    dialog_found = False
    
    while time.time() - start_time < timeout:
        hwnd = find_save_dialog()
        if hwnd:
            dialog_found = True
            print(f"  Save dialog detected for {employee_name}")
            return handle_save_dialog_robust(employee_name)
        time.sleep(0.5)
    
    if not dialog_found:
        print(f"  ⚠ Save dialog not found within {timeout}s for {employee_name}")
        return False

def process_employee_with_toast(employee_name, employee_index):
    """
    Complete workflow for one employee:
    1. Go to Toast report
    2. Filter by employee
    3. Click download
    4. Download Excel
    5. Handle save dialog
    """
    print(f"\n{'='*70}")
    print(f"EMPLOYEE {employee_index}/12: {employee_name}")
    print(f"{'='*70}")
    
    try:
        # Step 1: On Toast, find and filter to this employee
        print(f"  Step 1: Finding employee in Toast...")
        
        # Use Ctrl+F to search within the page for employee name
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.5)
        
        # Type employee name in search
        first_name = employee_name.split()[0]
        pyautogui.typewrite(first_name, interval=0.05)
        time.sleep(0.5)
        
        # Press Enter to find
        pyautogui.press('enter')
        time.sleep(0.5)
        
        # Close search (Esc)
        pyautogui.press('escape')
        time.sleep(0.5)
        
        print(f"  Step 2: Clicking download button...")
        # The download button should be visible
        # Try keyboard navigation: Tab to download button area
        pyautogui.hotkey('alt', 'tab')  # Make sure Toast is focused
        time.sleep(0.3)
        
        # Try to find and click download button
        # Look for download icon (use coordinates or visual search)
        # Approximate location based on typical Toast layout
        pyautogui.click(1050, 180)  # Download button approximate position
        time.sleep(0.8)
        
        print(f"  Step 3: Selecting 'Download Excel File'...")
        # Wait for menu to appear
        time.sleep(0.5)
        
        # Press down arrow to select "Download Excel File"
        pyautogui.press('down')
        time.sleep(0.2)
        
        # Press Enter to select
        pyautogui.press('enter')
        time.sleep(1)
        
        print(f"  Step 4: Waiting for save dialog...")
        # Monitor and handle save dialog
        success = monitor_for_save_dialog(employee_name, timeout=15)
        
        if success:
            print(f"  ✓ COMPLETED: {employee_name}")
        else:
            print(f"  ✗ FAILED: {employee_name}")
        
        return success
        
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False

def verify_downloaded_files():
    """Check what files were actually saved"""
    print(f"\n{'='*70}")
    print("VERIFICATION: Files in target folder")
    print(f"{'='*70}")
    
    if not os.path.exists(TARGET_FOLDER):
        print(f"Target folder does not exist: {TARGET_FOLDER}")
        return
    
    files = []
    for filename in os.listdir(TARGET_FOLDER):
        if filename.endswith('.xlsx') and '_' in filename:
            files.append(filename)
    
    if files:
        print(f"Found {len(files)} sales summary files:\n")
        for file in sorted(files):
            filepath = os.path.join(TARGET_FOLDER, file)
            size = os.path.getsize(filepath) / 1024  # KB
            print(f"  ✓ {file:<50} ({size:.1f} KB)")
    else:
        print("No sales summary files found yet.")
    
    return files

def main():
    """Main automation loop"""
    Path(TARGET_FOLDER).mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*70)
    print("TOAST SALES SUMMARY - AUTOMATED DOWNLOAD")
    print("="*70)
    print(f"Target: {TARGET_FOLDER}")
    print(f"Date: {REPORT_DATE}")
    print(f"Employees: {len(EMPLOYEES)}")
    print("="*70)
    
    input("\nPress ENTER to start automation (Toast page should be visible)...")
    
    successful = []
    failed = []
    
    for index, employee_name in enumerate(EMPLOYEES, 1):
        try:
            if process_employee_with_toast(employee_name, index):
                successful.append(employee_name)
            else:
                failed.append(employee_name)
            
            # Delay between employees
            if index < len(EMPLOYEES):
                print(f"\n  Waiting before next employee...")
                time.sleep(3)
        
        except KeyboardInterrupt:
            print("\n\n⚠ INTERRUPTED BY USER")
            break
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            failed.append(employee_name)
    
    # Summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"✓ Successful: {len(successful)}/{len(EMPLOYEES)}")
    print(f"✗ Failed: {len(failed)}/{len(EMPLOYEES)}")
    
    if successful:
        print(f"\nSuccessful employees:")
        for name in successful:
            print(f"  ✓ {name}")
    
    if failed:
        print(f"\nFailed employees:")
        for name in failed:
            print(f"  ✗ {name}")
    
    print(f"\n{'='*70}")
    verify_downloaded_files()
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
