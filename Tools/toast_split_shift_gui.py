#!/usr/bin/env python3
import calendar
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox


ROOT_DIR = Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python")
TOOLS_DIR = ROOT_DIR / "Tools"
RUNNER_PS1 = TOOLS_DIR / "run_split_shift_exports.ps1"
RUNNER_PY = TOOLS_DIR / "repeat_split_shift_exports.py"
DEFAULT_TOAST_EXPORTS = ROOT_DIR / "Toast Exports"
KNOWN_PYTHON = Path(r"C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe")


def get_python_exe() -> str:
    if KNOWN_PYTHON.exists():
        return str(KNOWN_PYTHON)
    return sys.executable


class DatePicker:
    def __init__(self, parent: tk.Tk, initial_date: datetime) -> None:
        self.parent = parent
        self.selected_date: datetime | None = None
        self.current_year = initial_date.year
        self.current_month = initial_date.month

        self.top = tk.Toplevel(parent)
        self.top.title("Pick Report Date")
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.grab_set()

        header = tk.Frame(self.top)
        header.pack(padx=10, pady=(10, 6), fill="x")

        tk.Button(header, text="<", width=3, command=self.prev_month).pack(side="left")
        self.title_var = tk.StringVar()
        tk.Label(header, textvariable=self.title_var, width=20, anchor="center").pack(side="left", expand=True)
        tk.Button(header, text=">", width=3, command=self.next_month).pack(side="right")

        self.grid_frame = tk.Frame(self.top)
        self.grid_frame.pack(padx=10, pady=6)

        footer = tk.Frame(self.top)
        footer.pack(padx=10, pady=(4, 10), fill="x")
        tk.Button(footer, text="Today", command=self.pick_today).pack(side="left")
        tk.Button(footer, text="Cancel", command=self.cancel).pack(side="right")

        self.render_calendar()

        self.top.bind("<Escape>", lambda _e: self.cancel())
        self.top.wait_window()

    def render_calendar(self) -> None:
        for w in self.grid_frame.winfo_children():
            w.destroy()

        self.title_var.set(f"{calendar.month_name[self.current_month]} {self.current_year}")

        week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for c, name in enumerate(week_days):
            tk.Label(self.grid_frame, text=name, width=4, fg="#444").grid(row=0, column=c, padx=1, pady=1)

        month_matrix = calendar.monthcalendar(self.current_year, self.current_month)
        for r, week in enumerate(month_matrix, start=1):
            for c, day in enumerate(week):
                if day == 0:
                    tk.Label(self.grid_frame, text="", width=4).grid(row=r, column=c, padx=1, pady=1)
                    continue

                tk.Button(
                    self.grid_frame,
                    text=str(day),
                    width=4,
                    command=lambda d=day: self.pick_day(d),
                ).grid(row=r, column=c, padx=1, pady=1)

    def prev_month(self) -> None:
        self.current_month -= 1
        if self.current_month < 1:
            self.current_month = 12
            self.current_year -= 1
        self.render_calendar()

    def next_month(self) -> None:
        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
        self.render_calendar()

    def pick_day(self, day: int) -> None:
        self.selected_date = datetime(self.current_year, self.current_month, day)
        self.top.destroy()

    def pick_today(self) -> None:
        self.selected_date = datetime.now()
        self.top.destroy()

    def cancel(self) -> None:
        self.selected_date = None
        self.top.destroy()


class App:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Toast Split Shift Export Runner")
        self.master.geometry("860x290")

        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.root_var = tk.StringVar(value=str(DEFAULT_TOAST_EXPORTS))
        self.closed_var = tk.StringVar(value="Not searched yet")

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 8}

        tk.Label(self.master, text="Report Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(self.master, textvariable=self.date_var, width=20).grid(row=0, column=1, sticky="w", **pad)
        tk.Button(self.master, text="Pick Date", command=self.pick_date).grid(row=0, column=2, sticky="w", **pad)

        tk.Label(self.master, text="Toast Exports Root:").grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(self.master, textvariable=self.root_var, width=70).grid(row=1, column=1, sticky="w", **pad)
        tk.Button(self.master, text="Browse", command=self.pick_root).grid(row=1, column=2, sticky="w", **pad)

        tk.Label(self.master, text="Closed Shifts CSV:").grid(row=2, column=0, sticky="nw", **pad)
        tk.Label(self.master, textvariable=self.closed_var, wraplength=560, justify="left", anchor="w").grid(
            row=2, column=1, columnspan=2, sticky="w", **pad
        )

        btn_frame = tk.Frame(self.master)
        btn_frame.grid(row=3, column=1, sticky="w", padx=10, pady=12)

        tk.Button(btn_frame, text="Find Closed Shifts", command=self.find_closed_shifts).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Run Export Process", command=self.run_process).pack(side="left", padx=6)
        tk.Button(btn_frame, text="List Jobs Only", command=self.list_only).pack(side="left", padx=6)

        hint = (
            "Run Export Process opens a PowerShell window for step-by-step prompts. "
            "It will auto-start popup guard, auto-find Closed_Shifts for the selected date, and delete old shift files."
        )
        tk.Label(self.master, text=hint, wraplength=740, justify="left", fg="#444").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=10, pady=10
        )

    def pick_root(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.root_var.get() or str(DEFAULT_TOAST_EXPORTS))
        if selected:
            self.root_var.set(selected)

    def pick_date(self) -> None:
        try:
            initial = datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            initial = datetime.now()

        picker = DatePicker(self.master, initial)
        if picker.selected_date is not None:
            self.date_var.set(picker.selected_date.strftime("%Y-%m-%d"))

    def _validate_date(self) -> str:
        value = self.date_var.get().strip()
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return value

    def _build_base_cmd(self) -> list[str]:
        date_value = self._validate_date()
        root_value = self.root_var.get().strip()
        if not root_value:
            raise ValueError("Toast Exports root is required")

        return [
            get_python_exe(),
            str(RUNNER_PY),
            "--auto-find-closed-shifts",
            "--report-date",
            date_value,
            "--toast-exports-root",
            root_value,
            "--delete-old",
        ]

    def find_closed_shifts(self) -> None:
        try:
            cmd = self._build_base_cmd() + ["--list-only", "--no-popup-guard"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = (proc.stdout or "") + (proc.stderr or "")
            marker = "Closed Shifts CSV:"
            closed_line = ""
            for line in output.splitlines():
                if line.startswith(marker):
                    closed_line = line.replace(marker, "").strip()
                    break

            if proc.returncode != 0:
                raise RuntimeError(output.strip() or "Unable to resolve Closed Shifts CSV")

            self.closed_var.set(closed_line if closed_line else "Resolved, check List Jobs output")
            messagebox.showinfo("Found", output.strip() or "Resolved")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def list_only(self) -> None:
        try:
            cmd = self._build_base_cmd() + ["--list-only", "--no-popup-guard"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0:
                raise RuntimeError(output.strip() or "List failed")
            messagebox.showinfo("Jobs", output.strip() or "No output")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_process(self) -> None:
        try:
            self._validate_date()
            root_value = self.root_var.get().strip()
            if not root_value:
                raise ValueError("Toast Exports root is required")

            if not RUNNER_PS1.exists():
                raise FileNotFoundError(f"Missing launcher: {RUNNER_PS1}")

            cmd = [
                "powershell",
                "-NoExit",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(RUNNER_PS1),
                "--auto-find-closed-shifts",
                "--report-date",
                self.date_var.get().strip(),
                "--toast-exports-root",
                root_value,
                "--auto-advance",
            ]

            creationflags = 0
            if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                creationflags = subprocess.CREATE_NEW_CONSOLE

            subprocess.Popen(cmd, creationflags=creationflags)
            messagebox.showinfo("Started", "Export process started in a new PowerShell window.")
        except Exception as e:
            messagebox.showerror("Error", str(e))


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
