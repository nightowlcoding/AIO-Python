import argparse
import time
from pywinauto import Desktop


def is_toast_save_dialog(win) -> bool:
    try:
        if not win.is_visible():
            return False
        title = (win.window_text() or "").strip().lower()
        cls = (win.class_name() or "").strip()

        # Toast downloads often open standard dialogs with blob:https titles.
        title_match = (
            "blob:https://www.toasttab.com" in title
            or "save as" in title
            or "toasttab" in title
        )

        # Common Windows file dialog class.
        class_match = cls == "#32770"

        if not (title_match or class_match):
            return False

        # Extra safety: ensure it looks like a Save dialog by checking for Save button.
        has_save = win.child_window(title="Save", control_type="Button").exists(timeout=0.1)
        has_cancel = win.child_window(title="Cancel", control_type="Button").exists(timeout=0.1)
        return has_save or has_cancel
    except Exception:
        return False


def close_dialog(win) -> bool:
    try:
        win.close()
        return True
    except Exception:
        try:
            win.child_window(title="Cancel", control_type="Button").click_input()
            return True
        except Exception:
            return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-close Toast Save As popup dialogs")
    parser.add_argument("--seconds", type=int, default=180, help="How long to monitor in seconds")
    parser.add_argument("--interval", type=float, default=0.4, help="Polling interval in seconds")
    args = parser.parse_args()

    end_time = time.time() + args.seconds
    closed = 0

    while time.time() < end_time:
        try:
            for win in Desktop(backend="uia").windows():
                if is_toast_save_dialog(win):
                    if close_dialog(win):
                        closed += 1
        except Exception:
            pass
        time.sleep(args.interval)

    print(f"Popup guard finished. Closed dialogs: {closed}")


if __name__ == "__main__":
    main()
