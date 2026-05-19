from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent
APP_FILE = ROOT / "app.py"
APP_URL = "http://127.0.0.1:5003"
CHECK_INTERVAL_SECONDS = 0.5
STARTUP_TIMEOUT_SECONDS = 45
ICON_CANDIDATES = (
    ROOT / "favicon.ico",
    ROOT / "ic3_icon.png",
    ROOT / "icon.png",
    ROOT / "ic3_icon.ico",
    ROOT / "icon.ico",
    ROOT / "favicon.png",
)


def _server_is_ready(url: str = APP_URL) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1):
            return True
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _start_server() -> subprocess.Popen[str]:
    if not APP_FILE.exists():
        raise FileNotFoundError(f"Missing app entrypoint: {APP_FILE}")

    return subprocess.Popen(
        [sys.executable, str(APP_FILE)],
        cwd=str(ROOT),
    )


def _find_icon_file() -> Path | None:
    for candidate in ICON_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


class SplashScreen:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Inventory Control 3")
        self.root.geometry("520x220")
        self.root.resizable(False, False)
        self.root.configure(bg="#1f2937")
        self.icon_image: tk.PhotoImage | None = None
        self._apply_window_icon()

        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        title = tk.Label(
            self.root,
            text="Inventory Control 3",
            font=("Segoe UI", 20, "bold"),
            fg="white",
            bg="#1f2937",
        )
        title.pack(pady=(28, 12))

        self.status_var = tk.StringVar(value="Starting server...")
        self.status_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 11),
            fg="#d1d5db",
            bg="#1f2937",
        )
        self.status_label.pack(pady=(0, 16))

        self.progress = ttk.Progressbar(self.root, mode="determinate", length=420)
        self.progress.pack()
        self.progress["maximum"] = 100
        self.progress["value"] = 5

        self.server_process: subprocess.Popen[str] | None = None
        self.error_message: str | None = None
        self.ready = False

    def _apply_window_icon(self) -> None:
        icon_file = _find_icon_file()
        if not icon_file:
            return

        try:
            if icon_file.suffix.lower() == ".ico":
                self.root.iconbitmap(str(icon_file))
                return

            self.icon_image = tk.PhotoImage(file=str(icon_file))
            self.root.iconphoto(True, self.icon_image)
        except Exception:
            pass

    def set_status(self, message: str, progress: float) -> None:
        self.status_var.set(message)
        self.progress["value"] = max(0, min(100, progress))
        self.root.update_idletasks()

    def _startup_worker(self) -> None:
        try:
            if _server_is_ready():
                self.set_status("Server already running. Opening app...", 90)
                self.ready = True
                return

            self.server_process = _start_server()
            start_time = time.time()

            while time.time() - start_time < STARTUP_TIMEOUT_SECONDS:
                elapsed = time.time() - start_time
                progress = 10 + (elapsed / STARTUP_TIMEOUT_SECONDS) * 75
                self.set_status("Waiting for app to become ready...", progress)
                if _server_is_ready():
                    self.ready = True
                    return
                time.sleep(CHECK_INTERVAL_SECONDS)

            self.error_message = (
                f"Timed out after {STARTUP_TIMEOUT_SECONDS} seconds while waiting for the app."
            )
        except Exception as exc:
            self.error_message = str(exc)

    def run(self) -> None:
        worker = threading.Thread(target=self._startup_worker, daemon=True)
        worker.start()
        self._poll_worker(worker)
        self.root.mainloop()

    def _poll_worker(self, worker: threading.Thread) -> None:
        if worker.is_alive():
            self.root.after(100, lambda: self._poll_worker(worker))
            return

        if self.ready:
            self.set_status("Opening app in browser...", 100)
            webbrowser.open(APP_URL)
            self.root.after(350, self.root.destroy)
            return

        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()

        messagebox.showerror(
            "Startup Error",
            self.error_message or "Unable to start Inventory Control 3.",
        )
        self.root.destroy()


def main() -> None:
    splash = SplashScreen()
    splash.run()


if __name__ == "__main__":
    main()
