import os
import tkinter as tk
from tkinter import filedialog, messagebox

from Sorter import (
    DEFAULT_EXTENSION_RULES,
    DESKTOP_DIR,
    DOCUMENTS_DIR,
    DOWNLOADS_DIR,
    audio,
    build_dest_folders,
    csv,
    d3_printer,
    doc,
    excel,
    finished_project,
    img,
    organize_files,
    pdf,
    ps,
    video,
    zip,
)


class SorterGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simple Folder Sorter")
        self.geometry("700x500")

        self.source_dirs = []
        self.documents_dir = tk.StringVar(value=DOCUMENTS_DIR)
        self.custom_rules = {k: tuple(v) for k, v in DEFAULT_EXTENSION_RULES.items()}

        self._build_ui()
        self.load_default_sources()

    def _build_ui(self):
        top_frame = tk.Frame(self)
        top_frame.pack(fill="x", padx=12, pady=10)

        tk.Label(top_frame, text="Sort Into Documents Folder:").grid(row=0, column=0, sticky="w")
        tk.Entry(top_frame, textvariable=self.documents_dir, width=70).grid(row=1, column=0, sticky="we", pady=4)
        tk.Button(top_frame, text="Choose Documents", command=self.choose_documents).grid(row=1, column=1, padx=8)

        src_frame = tk.Frame(self)
        src_frame.pack(fill="both", expand=True, padx=12, pady=8)

        tk.Label(src_frame, text="Folders To Sort:").pack(anchor="w")

        self.listbox = tk.Listbox(src_frame, selectmode=tk.EXTENDED)
        self.listbox.pack(fill="both", expand=True, pady=6)

        btn_row = tk.Frame(src_frame)
        btn_row.pack(fill="x")

        tk.Button(btn_row, text="Add Folder", command=self.add_folder).pack(side="left")
        tk.Button(btn_row, text="Remove Selected", command=self.remove_selected).pack(side="left", padx=8)
        tk.Button(btn_row, text="Clear All", command=self.clear_all).pack(side="left")
        tk.Button(btn_row, text="Use Desktop + Downloads", command=self.load_default_sources).pack(side="left", padx=8)
        tk.Button(btn_row, text="Edit Rules", command=self.open_rules_editor).pack(side="left", padx=8)

        rules_frame = tk.LabelFrame(self, text="Current Sorting Rules")
        rules_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.rules_text = tk.Text(rules_frame, height=12, wrap="word")
        self.rules_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.rules_text.configure(state="disabled")

        self.extension_map = {
            "Audio": audio,
            "Videos": video,
            "PDF": pdf,
            "Excel": excel,
            "CSV": csv,
            "Document": doc,
            "zips": zip,
            "Photoshop": ps,
            "Images": img,
            "3D printer": d3_printer,
            "Finished Projects": finished_project,
        }
        self.default_rules_text = self._rules_to_text(self.extension_map)

        bottom = tk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=10)

        tk.Button(bottom, text="Run Sort", command=self.run_sort, bg="#2e7d32", fg="white").pack(side="right")

        self.status_var = tk.StringVar(value="Add folders and click Run Sort.")
        tk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12, pady=(0, 10))

    def choose_documents(self):
        folder = filedialog.askdirectory(title="Choose Documents Folder")
        if folder:
            self.documents_dir.set(folder)
            self.refresh_rules_preview()

    def add_folder(self):
        folder = filedialog.askdirectory(title="Choose Folder To Sort")
        if not folder:
            return
        if folder not in self.source_dirs:
            self.source_dirs.append(folder)
            self.listbox.insert(tk.END, folder)

    def remove_selected(self):
        selected = list(self.listbox.curselection())
        if not selected:
            return
        for idx in reversed(selected):
            folder = self.listbox.get(idx)
            self.listbox.delete(idx)
            if folder in self.source_dirs:
                self.source_dirs.remove(folder)

    def clear_all(self):
        self.source_dirs.clear()
        self.listbox.delete(0, tk.END)

    def load_default_sources(self):
        self.clear_all()
        for folder in [DESKTOP_DIR, DOWNLOADS_DIR]:
            if os.path.isdir(folder):
                self.source_dirs.append(folder)
                self.listbox.insert(tk.END, folder)
        self.status_var.set("Default sources loaded: Desktop + Downloads")
        self.refresh_rules_preview()

    def refresh_rules_preview(self):
        documents_dir = self.documents_dir.get().strip()
        if not documents_dir:
            return

        dest_folders = build_dest_folders(documents_dir)
        lines = []
        lines.append("Destination folders inside Documents:")
        for category, folder in dest_folders.items():
            lines.append(f"- {category} -> {folder}")

        lines.append("")
        lines.append("Active extension rules:")
        for category, exts in self.custom_rules.items():
            lines.append(f"- {category}: {', '.join(exts)}")

        lines.append("")
        lines.append("Note: Image files with 'screenshot' in the name go to Screenshots.")
        lines.append("Other unmatched files go to: untitled folder")

        self.rules_text.configure(state="normal")
        self.rules_text.delete("1.0", tk.END)
        self.rules_text.insert(tk.END, "\n".join(lines))
        self.rules_text.configure(state="disabled")

    def _rules_to_text(self, rules):
        lines = []
        for category, exts in rules.items():
            lines.append(f"{category}={','.join(exts)}")
        return "\n".join(lines)

    def _parse_rules_text(self, raw_text):
        parsed = {}
        valid_categories = set(self.extension_map.keys())

        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "=" not in stripped:
                raise ValueError(f"Invalid line (missing '='): {stripped}")
            category, exts_part = stripped.split("=", 1)
            category = category.strip()
            if category not in valid_categories:
                raise ValueError(f"Unknown category: {category}")

            exts = []
            for ext in exts_part.split(","):
                cleaned = ext.strip().lower()
                if not cleaned:
                    continue
                if not cleaned.startswith("."):
                    cleaned = f".{cleaned}"
                exts.append(cleaned)
            parsed[category] = tuple(exts)

        for category in self.extension_map.keys():
            parsed.setdefault(category, tuple())

        return parsed

    def open_rules_editor(self):
        editor = tk.Toplevel(self)
        editor.title("Edit Extension Rules")
        editor.geometry("700x500")

        info = (
            "Use format: Category=.ext1,.ext2\n"
            "Example: Audio=.mp3,.wav\n"
            "Keep category names exactly as shown."
        )
        tk.Label(editor, text=info, justify="left").pack(anchor="w", padx=10, pady=(10, 4))

        text = tk.Text(editor, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=6)
        text.insert("1.0", self._rules_to_text(self.custom_rules))

        buttons = tk.Frame(editor)
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def reset_defaults():
            text.delete("1.0", tk.END)
            text.insert("1.0", self.default_rules_text)

        def save_rules():
            try:
                parsed = self._parse_rules_text(text.get("1.0", tk.END))
            except ValueError as exc:
                messagebox.showerror("Invalid Rules", str(exc), parent=editor)
                return

            self.custom_rules = parsed
            self.refresh_rules_preview()
            self.status_var.set("Custom rules updated.")
            editor.destroy()

        tk.Button(buttons, text="Reset Defaults", command=reset_defaults).pack(side="left")
        tk.Button(buttons, text="Save Rules", command=save_rules, bg="#1565c0", fg="white").pack(side="right")

    def run_sort(self):
        documents_dir = self.documents_dir.get().strip()

        if not documents_dir:
            messagebox.showerror("Missing Folder", "Please choose a Documents folder.")
            return

        if not os.path.isdir(documents_dir):
            messagebox.showerror("Invalid Folder", "The selected Documents folder does not exist.")
            return

        if not self.source_dirs:
            messagebox.showerror("No Source Folders", "Please add at least one folder to sort.")
            return

        self.status_var.set("Sorting files...")
        self.update_idletasks()

        move_counts, errors = organize_files(self.source_dirs, documents_dir, extension_rules=self.custom_rules)
        total_moved = sum(move_counts.values())

        lines = [f"Total files moved: {total_moved}"]
        for key, count in move_counts.items():
            lines.append(f"{key}: {count}")

        if errors:
            lines.append("")
            lines.append(f"Errors: {len(errors)}")
            lines.extend(errors[:10])
            if len(errors) > 10:
                lines.append("(Showing first 10 errors)")

        summary = "\n".join(lines)
        self.status_var.set(f"Done. Moved {total_moved} files.")
        messagebox.showinfo("Sort Complete", summary)


if __name__ == "__main__":
    app = SorterGui()
    app.refresh_rules_preview()
    app.mainloop()
