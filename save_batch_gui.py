"""
GUI wrapper for save_batch.py — Toast Product Mix downloader/decoder.
Run: python save_batch_gui.py
"""
import datetime as dt
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ── Import the core logic from save_batch ──────────────────────────────────────
import save_batch

# ── Constants ─────────────────────────────────────────────────────────────────
LOCATIONS = sorted(save_batch.LOCATION_PRESETS.keys())
TODAY = dt.date.today()
WEEK_AGO = TODAY - dt.timedelta(days=6)
PAD = {"padx": 8, "pady": 4}


# ── Redirected stdout → queue ──────────────────────────────────────────────────
class _QueueWriter:
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, text: str):
        if text:
            self._q.put(text)

    def flush(self):
        pass


# ── Main application ───────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Toast Product Mix Downloader")
        self.resizable(True, True)
        self.minsize(640, 520)
        self._log_queue: queue.Queue = queue.Queue()
        self._build_ui()
        self._poll_log()

    # ── UI construction ────────────────────────────────────────────────────────
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", **PAD)

        ttk.Label(top, text="Location:").pack(side="left")
        self.location_var = tk.StringVar(value=LOCATIONS[0])
        ttk.Combobox(
            top,
            textvariable=self.location_var,
            values=LOCATIONS,
            state="readonly",
            width=14,
        ).pack(side="left", padx=(4, 16))

        ttk.Label(top, text="Output folder:").pack(side="left")
        self.out_dir_var = tk.StringVar()
        self._update_out_dir()
        self.location_var.trace_add("write", lambda *_: self._update_out_dir())
        out_entry = ttk.Entry(top, textvariable=self.out_dir_var, width=38)
        out_entry.pack(side="left", padx=(4, 2))
        ttk.Button(top, text="…", width=3, command=self._browse_out_dir).pack(side="left")

        # ── Notebook (mode tabs) ───────────────────────────────────────────────
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, **PAD)

        self._build_download_tab(nb)
        self._build_decode_tab(nb)

        # ── Log area ──────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=True, **PAD)
        self.log_box = scrolledtext.ScrolledText(
            log_frame, height=10, state="disabled", wrap="word",
            font=("Consolas", 9),
        )
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", **PAD)
        ttk.Button(btn_row, text="Clear log", command=self._clear_log).pack(side="right")

        self._nb = nb

    def _build_download_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Download from Toast")
        frame.columnconfigure(1, weight=1)

        fields = [
            ("Start date (YYYY-MM-DD):", "start_date_var", WEEK_AGO.isoformat()),
            ("End date (YYYY-MM-DD):", "end_date_var", TODAY.isoformat()),
            ("Authorization (Bearer …):", "auth_var", ""),
            ("Management set GUID:", "mgmt_guid_var", ""),
            ("Restaurant set GUID:", "rest_set_guid_var", ""),
            ("Restaurant external ID\n(leave blank = location GUID):", "rest_ext_var", ""),
        ]
        for row_idx, (label, attr, default) in enumerate(fields):
            ttk.Label(frame, text=label, justify="right").grid(
                row=row_idx, column=0, sticky="e", **PAD
            )
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            show = "*" if "auth" in attr.lower() else ""
            entry = ttk.Entry(frame, textvariable=var, show=show, width=48)
            entry.grid(row=row_idx, column=1, sticky="ew", **PAD)
            # Toggle visibility for auth field
            if show:
                def _toggle(e=entry, v=var, original=[""]):
                    if e.cget("show") == "*":
                        e.config(show="")
                    else:
                        e.config(show="*")
                ttk.Button(frame, text="👁", width=3, command=_toggle).grid(
                    row=row_idx, column=2, **PAD
                )

        self.skip_existing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame, text="Skip already-downloaded dates", variable=self.skip_existing_var
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", **PAD)

        run_btn = ttk.Button(
            frame, text="▶  Download", command=self._run_download
        )
        run_btn.grid(row=len(fields) + 1, column=0, columnspan=3, pady=10)

    def _build_decode_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Decode captured file")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Captured JSON file:").grid(
            row=0, column=0, sticky="e", **PAD
        )
        self.json_path_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.json_path_var, width=48).grid(
            row=0, column=1, sticky="ew", **PAD
        )
        ttk.Button(frame, text="…", width=3, command=self._browse_json).grid(
            row=0, column=2, **PAD
        )

        ttk.Label(
            frame,
            text=(
                "Select the captured tool-result file\n"
                "(starts with 'Result: ...' or is a plain JSON array)."
            ),
            foreground="grey",
        ).grid(row=1, column=0, columnspan=3, sticky="w", **PAD)

        run_btn = ttk.Button(
            frame, text="▶  Decode & Save", command=self._run_decode
        )
        run_btn.grid(row=2, column=0, columnspan=3, pady=10)

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _update_out_dir(self):
        preset = save_batch.LOCATION_PRESETS.get(self.location_var.get(), {})
        self.out_dir_var.set(preset.get("output_dir", ""))

    def _browse_out_dir(self):
        path = filedialog.askdirectory(initialdir=self.out_dir_var.get() or os.path.expanduser("~"))
        if path:
            self.out_dir_var.set(path)

    def _browse_json(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON / Text files", "*.json *.txt"), ("All files", "*.*")]
        )
        if path:
            self.json_path_var.set(path)

    # ── Log helpers ────────────────────────────────────────────────────────────
    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _poll_log(self):
        try:
            while True:
                text = self._log_queue.get_nowait()
                self._log(text)
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    # ── Run helpers ────────────────────────────────────────────────────────────
    def _run_in_thread(self, fn):
        """Run *fn* in a background thread, redirecting stdout to the log."""
        def wrapper():
            old_stdout = sys.stdout
            sys.stdout = _QueueWriter(self._log_queue)
            try:
                fn()
            except Exception as exc:  # pylint: disable=broad-except
                self._log_queue.put(f"\nERROR: {exc}\n")
            finally:
                sys.stdout = old_stdout

        threading.Thread(target=wrapper, daemon=True).start()

    def _run_download(self):
        location = self.location_var.get()
        out_dir = self.out_dir_var.get().strip()
        start = self.start_date_var.get().strip()
        end = self.end_date_var.get().strip()
        auth = self.auth_var.get().strip()
        mgmt = self.mgmt_guid_var.get().strip()
        rest_set = self.rest_set_guid_var.get().strip()
        rest_ext = self.rest_ext_var.get().strip() or None
        skip = self.skip_existing_var.get()

        # Basic validation
        if not all([start, end, auth, mgmt, rest_set]):
            messagebox.showerror(
                "Missing fields",
                "Start date, end date, authorization, management set GUID, and restaurant set GUID are all required.",
            )
            return

        preset = save_batch.LOCATION_PRESETS[location]
        location_guid = preset["location_guid"]
        effective_out = out_dir or preset["output_dir"]
        save_batch.ensure_output_dir(effective_out)

        class _Args:
            pass

        args = _Args()
        args.start_date = start
        args.end_date = end
        args.authorization = auth
        args.management_set_guid = mgmt
        args.restaurant_set_guid = rest_set
        args.restaurant_external_id = rest_ext
        args.skip_existing = skip

        self._log(f"\n── Download: {location}  {start} → {end} ──\n")
        self._run_in_thread(
            lambda: save_batch.download_files(args, location_guid, effective_out)
        )

    def _run_decode(self):
        location = self.location_var.get()
        out_dir = self.out_dir_var.get().strip()
        json_path = self.json_path_var.get().strip()

        if not json_path:
            messagebox.showerror("Missing field", "Please select a captured JSON file.")
            return
        if not os.path.isfile(json_path):
            messagebox.showerror("File not found", f"Cannot find:\n{json_path}")
            return

        preset = save_batch.LOCATION_PRESETS[location]
        effective_out = out_dir or preset["output_dir"]
        save_batch.ensure_output_dir(effective_out)

        self._log(f"\n── Decode: {location}  →  {effective_out} ──\n")
        self._run_in_thread(
            lambda: save_batch.save_decoded_files(json_path, effective_out)
        )


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
