import argparse
import time
from pywinauto import Desktop
from pywinauto.keyboard import send_keys


def find_save_dialog(timeout_seconds: int = 25):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        windows = Desktop(backend="uia").windows(class_name="#32770")
        for w in windows:
            try:
                if not w.is_visible():
                    continue
                title = (w.window_text() or "").strip()
                # Toast save windows often show blob:https://... instead of "Save As"
                if title and ("save" in title.lower() or "blob:" in title.lower() or "toasttab" in title.lower()):
                    return w
                # Fallback: if common file dialog has Save button
                if w.child_window(title="Save", control_type="Button").exists(timeout=0.2):
                    return w
            except Exception:
                continue
        time.sleep(0.2)
    return None


def set_folder(dialog, folder_path: str):
    # Focus dialog and use address bar shortcut
    dialog.set_focus()
    send_keys("^l")
    time.sleep(0.2)
    send_keys("^a")
    time.sleep(0.05)
    send_keys(folder_path, with_spaces=True)
    send_keys("{ENTER}")
    time.sleep(0.7)


def set_filename_and_save(dialog, file_name: str):
    # Try direct file-name edit first
    try:
        edit = dialog.child_window(auto_id="1001", control_type="Edit")
        if edit.exists(timeout=0.5):
            edit.set_edit_text(file_name)
        else:
            raise RuntimeError("File edit control by auto_id not found")
    except Exception:
        # Keyboard fallback: Alt+N goes to File name field in many save dialogs
        dialog.set_focus()
        send_keys("%n")
        time.sleep(0.15)
        send_keys("^a")
        time.sleep(0.05)
        send_keys(file_name, with_spaces=True)

    # Click Save
    try:
        save_btn = dialog.child_window(title="Save", control_type="Button")
        save_btn.click_input()
    except Exception:
        dialog.set_focus()
        send_keys("%s")

    time.sleep(0.7)

    # If overwrite prompt appears, confirm replace
    try:
        overwrite = Desktop(backend="uia").window(title_re=".*Confirm Save As|.*Replace or Skip Files|.*already exists.*")
        if overwrite.exists(timeout=0.5):
            try:
                overwrite.child_window(title_re="Yes|Replace", control_type="Button").click_input()
            except Exception:
                overwrite.set_focus()
                send_keys("%y")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Handle Windows Save dialog for Toast exports")
    parser.add_argument("--folder", required=True, help="Target folder path")
    parser.add_argument("--filename", required=True, help="Target file name including .xlsx")
    parser.add_argument("--timeout", type=int, default=25, help="Seconds to wait for save dialog")
    args = parser.parse_args()

    dialog = find_save_dialog(timeout_seconds=args.timeout)
    if dialog is None:
        print("ERROR: Save dialog not found")
        raise SystemExit(1)

    set_folder(dialog, args.folder)
    set_filename_and_save(dialog, args.filename)
    print(f"OK: Saved as {args.filename} in {args.folder}")


if __name__ == "__main__":
    main()
