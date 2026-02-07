# Remove old iOS device backups (Finder/iTunes)
def clean_ios_backups():
    backups_path = os.path.expanduser('~/Library/Application Support/MobileSync/Backup')
    deleted = clean_folder(backups_path)
    return f"Deleted {deleted} iOS device backup files."

# Clean QuickLook cache
def clean_quicklook_cache():
    ql_cache = os.path.expanduser('~/Library/Caches/com.apple.QuickLook.thumbnailcache')
    deleted = clean_folder(ql_cache)
    return f"Deleted {deleted} QuickLook cache files."

# Clean font caches
def clean_font_caches():
    font_cache_paths = [
        os.path.expanduser('~/Library/Caches/com.apple.FontRegistry'),
        os.path.expanduser('~/Library/Fonts/'),
        '/Library/Caches/com.apple.FontRegistry',
    ]
    deleted = 0
    for path in font_cache_paths:
        deleted += clean_folder(path)
    return f"Deleted {deleted} font cache files."

# Remove old Time Machine local snapshots (requires sudo)
def clean_time_machine_snapshots():
    try:
        result = subprocess.run(['tmutil', 'listlocalsnapshots', '/'], capture_output=True, text=True)
        snapshots = [line for line in result.stdout.splitlines() if line.strip()]
        deleted = 0
        for snap in snapshots:
            snap_name = snap.split('.')[-1]
            del_result = subprocess.run(['tmutil', 'deletelocalsnapshots', snap_name], capture_output=True, text=True)
            if del_result.returncode == 0:
                deleted += 1
        return f"Deleted {deleted} Time Machine local snapshots."
    except Exception as e:
        return f"Could not clean Time Machine snapshots: {e}"

# Remove unused language files (localizations)
def clean_language_files():
    apps_path = '/Applications'
    deleted = 0
    for app in os.listdir(apps_path):
        app_path = os.path.join(apps_path, app, 'Contents', 'Resources')
        if os.path.exists(app_path):
            for item in os.listdir(app_path):
                if item.endswith('.lproj') and not item.startswith('en'):  # Keep English
                    try:
                        full_path = os.path.join(app_path, item)
                        if os.path.isdir(full_path):
                            shutil.rmtree(full_path)
                            deleted += 1
                    except Exception:
                        pass
    return f"Deleted {deleted} unused language files."

import os
import shutil
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


# Function to delete all files in a folder (recursively)
def clean_folder(folder):
    deleted = 0
    if os.path.exists(folder):
        for root, dirs, files in os.walk(folder):
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    deleted += 1
                except Exception:
                    pass
    return deleted


# Empty Trash on macOS
def empty_trash():
    try:
        trash_path = os.path.expanduser("~/.Trash")
        deleted = clean_folder(trash_path)
        return f"Emptied Trash. Deleted {deleted} files."
    except Exception as e:
        return f"Could not empty Trash: {e}"


# Clean browser caches for Chrome, Firefox, Safari (macOS)
def clean_browser_cache():
    user = os.getlogin()
    total = 0
    # Chrome
    chrome_cache = f"/Users/{user}/Library/Caches/Google/Chrome/Default/Cache"
    total += clean_folder(chrome_cache)
    # Firefox
    firefox_profiles = f"/Users/{user}/Library/Application Support/Firefox/Profiles"
    if os.path.exists(firefox_profiles):
        for profile in os.listdir(firefox_profiles):
            cache2 = os.path.join(firefox_profiles, profile, "cache2")
            total += clean_folder(cache2)
    # Safari
    safari_cache = f"/Users/{user}/Library/Caches/com.apple.Safari"
    total += clean_folder(safari_cache)
    return f"Deleted {total} browser cache files."


# Clean temp folders (macOS)
def clean_temp():
    user_temp = f"/Users/{os.getlogin()}/Library/Caches"
    system_temp = "/private/tmp"
    total = clean_folder(user_temp)
    total += clean_folder(system_temp)
    return f"Deleted {total} temp/cache files."


# Remove old system logs (optional)
def clean_system_logs():
    logs_path = "/private/var/log"
    total = clean_folder(logs_path)
    return f"Deleted {total} system log files."


# No direct equivalent for chkdsk or sfc on macOS in a safe, scriptable way


# --- GUI and main logic ---
def run_cleaner(options, output_text):
    output = []
    if options['temp'].get():
        output.append(clean_temp())
    if options['browser'].get():
        output.append(clean_browser_cache())
    if options['trash'].get():
        output.append(empty_trash())
    if options['logs'].get():
        output.append(clean_system_logs())
    if options['ios'].get():
        output.append(clean_ios_backups())
    if options['quicklook'].get():
        output.append(clean_quicklook_cache())
    if options['font'].get():
        output.append(clean_font_caches())
    if options['tm'].get():
        output.append(clean_time_machine_snapshots())
    if options['lang'].get():
        output.append(clean_language_files())
    output_text.config(state='normal')
    output_text.delete(1.0, tk.END)
    output_text.insert(tk.END, '\n\n'.join(output))
    output_text.config(state='disabled')

def main_gui():
    root = tk.Tk()
    root.title("Mac Speedup & Cleaner Tool")
    root.geometry("600x650")

    options = {
        'temp': tk.BooleanVar(value=True),
        'browser': tk.BooleanVar(value=True),
        'trash': tk.BooleanVar(value=True),
        'logs': tk.BooleanVar(value=False),
        'ios': tk.BooleanVar(value=False),
        'quicklook': tk.BooleanVar(value=False),
        'font': tk.BooleanVar(value=False),
        'tm': tk.BooleanVar(value=False),
        'lang': tk.BooleanVar(value=False)
    }

    tk.Label(root, text="Select cleaning options:", font=("Arial", 14)).pack(pady=10)
    tk.Checkbutton(root, text="Clean Temp & Cache Folders", variable=options['temp']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Clean Browser Cache (Chrome, Firefox, Safari)", variable=options['browser']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Empty Trash", variable=options['trash']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Clean System Logs", variable=options['logs']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Remove iOS Device Backups", variable=options['ios']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Clean QuickLook Cache", variable=options['quicklook']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Clean Font Caches", variable=options['font']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Remove Time Machine Local Snapshots", variable=options['tm']).pack(anchor='w', padx=20)
    tk.Checkbutton(root, text="Remove Unused Language Files (non-English)", variable=options['lang']).pack(anchor='w', padx=20)

    output_text = tk.Text(root, height=20, width=70, state='disabled')
    output_text.pack(pady=10)

    tk.Button(root, text="Start Cleaning", font=("Arial", 12, "bold"), command=lambda: run_cleaner(options, output_text)).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    main_gui()
