from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


DATE_PREFIX = re.compile(r"^(\d{4})(\d{2})(\d{2})\d+\.csv$", re.IGNORECASE)


def build_new_name(path: Path, location: str, seen_per_day: dict[str, int]) -> str | None:
    match = DATE_PREFIX.match(path.name)
    if not match:
        return None

    yyyy, mm, dd = match.group(1), match.group(2), match.group(3)
    date_key = f"{yyyy}-{mm}-{dd}"
    seen_per_day[date_key] = seen_per_day.get(date_key, 0) + 1
    suffix = "" if seen_per_day[date_key] == 1 else f"_part{seen_per_day[date_key]}"
    return f"{location}_{date_key}_order{suffix}.csv"


def plan_renames(folder: Path, location: str) -> list[tuple[str, str]]:
    planned: list[tuple[str, str]] = []
    seen_per_day: dict[str, int] = {}

    for path in sorted(folder.glob("*.csv")):
        new_name = build_new_name(path, location, seen_per_day)
        if not new_name or new_name == path.name:
            continue

        target = path.with_name(new_name)
        counter = 1
        while target.exists() and target.name != path.name:
            stem = Path(new_name).stem
            suffix = Path(new_name).suffix
            target = path.with_name(f"{stem}_{counter}{suffix}")
            counter += 1

        planned.append((path.name, target.name))

    return planned


def apply_renames(folder: Path, planned: list[tuple[str, str]]) -> int:
    renamed = 0
    for old_name, new_name in planned:
        source = folder / old_name
        target = folder / new_name
        if not source.exists():
            continue
        source.rename(target)
        renamed += 1
    return renamed


class OrderCsvRenamerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("IC3 Order CSV Renamer")
        self.geometry("900x620")

        self.folder_var = tk.StringVar()
        self.location_var = tk.StringVar(value="Alice")
        self.status_var = tk.StringVar(value="Choose a folder to preview renames.")
        self.current_plan: list[tuple[str, str]] = []

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="Inventory Control 3 Order CSV Renamer", font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            main,
            text="Renames timestamp-style CSV files like 2026042321051311079.csv into readable order filenames.",
        )
        subtitle.pack(anchor="w", pady=(0, 12))

        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=(0, 10))

        ttk.Label(controls, text="Folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.folder_var, width=70).grid(row=0, column=1, padx=8, sticky="ew")
        ttk.Button(controls, text="Browse", command=self.browse_folder).grid(row=0, column=2, sticky="w")

        ttk.Label(controls, text="Location:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(
            controls,
            textvariable=self.location_var,
            values=["Alice", "Kingsville"],
            width=20,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=8, pady=(10, 0))

        controls.columnconfigure(1, weight=1)

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(0, 10))
        ttk.Button(buttons, text="Preview Renames", command=self.preview_renames).pack(side="left")
        ttk.Button(buttons, text="Apply Renames", command=self.rename_now).pack(side="left", padx=8)
        ttk.Button(buttons, text="Clear", command=self.clear_output).pack(side="left")

        self.output = tk.Text(main, height=26, wrap="none")
        self.output.pack(fill="both", expand=True)

        x_scroll = ttk.Scrollbar(main, orient="horizontal", command=self.output.xview)
        x_scroll.pack(fill="x")
        self.output.configure(xscrollcommand=x_scroll.set)

        status = ttk.Label(main, textvariable=self.status_var)
        status.pack(fill="x", pady=(10, 0))

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder with timestamp CSV files")
        if folder:
            self.folder_var.set(folder)

    def _resolve_folder(self) -> Path | None:
        folder = Path(self.folder_var.get().strip())
        if not folder.exists() or not folder.is_dir():
            messagebox.showerror("Folder not found", f"Folder not found:\n{folder}")
            return None
        return folder

    def preview_renames(self) -> None:
        folder = self._resolve_folder()
        if folder is None:
            return

        location = self.location_var.get().strip() or "Alice"
        planned = plan_renames(folder, location)
        self.current_plan = planned

        self.output.delete("1.0", tk.END)
        if not planned:
            self.output.insert(tk.END, "No matching timestamp CSV files found to rename.\n")
            self.status_var.set("No matching files found.")
            return

        for old_name, new_name in planned:
            self.output.insert(tk.END, f"{old_name} -> {new_name}\n")

        self.status_var.set(f"Preview ready: {len(planned)} files can be renamed.")

    def rename_now(self) -> None:
        folder = self._resolve_folder()
        if folder is None:
            return

        if not self.current_plan:
            self.preview_renames()
            if not self.current_plan:
                return

        if not messagebox.askyesno(
            "Confirm Rename",
            f"Rename {len(self.current_plan)} CSV files in\n{folder}\n\nContinue?",
        ):
            return

        renamed = apply_renames(folder, self.current_plan)
        self.status_var.set(f"Renamed {renamed} files.")
        self.preview_renames()
        if renamed:
            messagebox.showinfo("Rename Complete", f"Renamed {renamed} files.")

    def clear_output(self) -> None:
        self.current_plan = []
        self.output.delete("1.0", tk.END)
        self.status_var.set("Cleared.")


if __name__ == "__main__":
    app = OrderCsvRenamerApp()
    app.mainloop()
