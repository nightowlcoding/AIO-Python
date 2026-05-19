import ctypes
import csv
import importlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from time import perf_counter
from time import time
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    psutil = importlib.import_module("psutil")
except Exception:
    psutil = None


class AsusG14TuneupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ASUS G14 Tune-Up Tool")
        self.root.geometry("1024x780")
        self.root.minsize(940, 700)

        self.is_windows = platform.system().lower() == "windows"
        self.advanced_preflight_ready = False

        self.report_dir = Path("reports") / "asus_g14_tuning"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._startup_cleanup_summary = self._cleanup_old_session_reports(days=30, max_files=120)
        self.session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_csv = self.report_dir / f"session_{self.session_stamp}.csv"
        self.session_txt = self.report_dir / f"session_{self.session_stamp}.txt"
        self._action_counter = 0
        self._action_lock = threading.Lock()
        self.log_entries = []
        self._init_session_reports()

        self.style = ttk.Style()
        self.style.theme_use("clam")

        self._build_ui()
        self.refresh_health_snapshot()

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(14, 12))
        header.pack(fill="x")

        ttk.Label(header, text="ASUS G14 Tune-Up Tool", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Performance dashboard with safe cleanup, reversible tuning, and guided driver/firmware workflows."
            ),
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 0))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.health_tab = ttk.Frame(self.notebook, padding=12)
        self.cleanup_tab = ttk.Frame(self.notebook, padding=12)
        self.drivers_tab = ttk.Frame(self.notebook, padding=12)
        self.firmware_tab = ttk.Frame(self.notebook, padding=12)
        self.overclock_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.health_tab, text="Health")
        self.notebook.add(self.cleanup_tab, text="Cleanup & Tuning")
        self.notebook.add(self.drivers_tab, text="Drivers")
        self.notebook.add(self.firmware_tab, text="Firmware")
        self.notebook.add(self.overclock_tab, text="Overclocking")

        self._build_health_tab()
        self._build_cleanup_tab()
        self._build_drivers_tab()
        self._build_firmware_tab()
        self._build_overclock_tab()

        controls = ttk.Frame(header)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Relaunch as Administrator", command=self.relaunch_as_admin).pack(side="left")
        ttk.Button(controls, text="Open Reports Folder", command=self.open_reports_folder).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Open Current Activity Log", command=self.open_current_activity_log).pack(
            side="left", padx=(8, 0)
        )

        log_wrap = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        log_controls = ttk.Frame(log_wrap)
        log_controls.pack(fill="x", pady=(0, 6))
        ttk.Label(log_controls, text="Filter:").pack(side="left")
        self.log_filter_var = tk.StringVar(value="All")
        log_filter = ttk.Combobox(
            log_controls,
            textvariable=self.log_filter_var,
            values=["All", "START", "OK", "ERROR", "ADMIN"],
            state="readonly",
            width=12,
        )
        log_filter.pack(side="left", padx=(6, 0))
        log_filter.bind("<<ComboboxSelected>>", lambda _evt: self._refresh_log_view())

        self.log_box = ScrolledText(log_wrap, height=10, font=("Consolas", 10), state="disabled")
        self.log_box.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(12, 0, 12, 10)).pack(fill="x")

        if not self.is_windows:
            self._log("This app is designed for Windows. Some actions are disabled.")
        if self._startup_cleanup_summary:
            self._log(self._startup_cleanup_summary)
        self._log(f"Session log file: {self.session_txt.resolve()}")

    def _build_health_tab(self):
        frame = ttk.Frame(self.health_tab)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        left = ttk.LabelFrame(frame, text="Live System Status", padding=10)
        right = ttk.LabelFrame(frame, text="Top Memory Processes", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))

        self.cpu_var = tk.StringVar(value="CPU: --")
        self.ram_var = tk.StringVar(value="RAM: --")
        self.disk_var = tk.StringVar(value="C: Drive: --")
        self.uptime_var = tk.StringVar(value="Uptime: --")
        self.battery_var = tk.StringVar(value="Battery: --")

        for var in (self.cpu_var, self.ram_var, self.disk_var, self.uptime_var, self.battery_var):
            ttk.Label(left, textvariable=var, font=("Segoe UI", 10)).pack(anchor="w", pady=2)

        self._action_button(left, "Refresh Health Snapshot", self.refresh_health_snapshot)

        self.top_processes_text = tk.StringVar(value="No data yet.")
        ttk.Label(
            right,
            textvariable=self.top_processes_text,
            justify="left",
            anchor="nw",
            font=("Consolas", 10),
        ).pack(fill="both", expand=True)

    def _build_cleanup_tab(self):
        wrap = ttk.Frame(self.cleanup_tab)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.columnconfigure(1, weight=1)

        cleanup_card = ttk.LabelFrame(wrap, text="Temp Cleanup", padding=10)
        tuning_card = ttk.LabelFrame(wrap, text="Reversible Performance Tuning", padding=10)
        cleanup_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        tuning_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))

        self.cleanup_dry_run = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            cleanup_card,
            text="Dry-run mode (preview only)",
            variable=self.cleanup_dry_run,
        ).pack(anchor="w", pady=(0, 8))

        self._action_button(cleanup_card, "Preview Temp Cleanup", self.preview_temp_cleanup)
        self._action_button(cleanup_card, "Run Temp Cleanup", self.run_temp_cleanup)

        ttk.Label(
            cleanup_card,
            text="Targets: user TEMP and Windows Temp. In-use files are skipped safely.",
            wraplength=420,
            foreground="#555555",
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(tuning_card, text="Power Plan", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.power_plan_var = tk.StringVar(value="High performance")
        ttk.Combobox(
            tuning_card,
            textvariable=self.power_plan_var,
            values=["High performance", "Balanced", "Power saver"],
            state="readonly",
            width=26,
        ).pack(anchor="w", pady=(4, 8))

        ttk.Label(tuning_card, text="Visual Effects", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.visual_fx_var = tk.StringVar(value="Best performance")
        ttk.Combobox(
            tuning_card,
            textvariable=self.visual_fx_var,
            values=["Best performance", "Let Windows choose", "Best appearance"],
            state="readonly",
            width=26,
        ).pack(anchor="w", pady=(4, 8))

        self.game_mode_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            tuning_card,
            text="Enable Game Mode",
            variable=self.game_mode_var,
        ).pack(anchor="w", pady=(0, 8))

        self._action_button(tuning_card, "Apply Selected Tuning", self.apply_selected_tuning)

    def _build_drivers_tab(self):
        card = ttk.LabelFrame(self.drivers_tab, text="Guided Driver Workflow", padding=12)
        card.pack(fill="both", expand=True)

        ttk.Label(
            card,
            text=(
                "Guided-only flow: detect versions, then launch trusted update channels. "
                "No silent or forced driver replacement is performed by this app."
            ),
            wraplength=890,
        ).pack(anchor="w", pady=(0, 10))

        self._action_button(card, "Detect Driver Versions", self.detect_driver_versions)
        self._action_button(card, "Open Windows Update (Driver Settings)", self.open_windows_update_drivers)
        self._action_button(card, "Open NVIDIA Driver Download", self.open_nvidia_driver_page)
        self._action_button(card, "Open ASUS Support For This Model", self.open_asus_support_page)

    def _build_firmware_tab(self):
        card = ttk.LabelFrame(self.firmware_tab, text="Guided BIOS/Firmware Workflow", padding=12)
        card.pack(fill="both", expand=True)

        self.model_var = tk.StringVar(value="Model: --")
        self.bios_var = tk.StringVar(value="BIOS Version: --")
        self.bios_date_var = tk.StringVar(value="BIOS Date: --")

        ttk.Label(card, textvariable=self.model_var, font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(card, textvariable=self.bios_var, font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(card, textvariable=self.bios_date_var, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))

        ttk.Label(
            card,
            text=(
                "Safety requirements for advanced workflows: admin privileges, restore point attempt, "
                "registry backup snapshot, AC power connected, and battery above 50%."
            ),
            wraplength=890,
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 10))

        self._action_button(card, "Refresh Firmware Info", self.refresh_firmware_info)
        self._action_button(card, "Run Advanced Safety Preflight", self.run_advanced_safety_preflight)
        self._action_button(card, "Open ASUS BIOS/Firmware Support Page", self.open_asus_firmware_support)

    def _build_overclock_tab(self):
        card = ttk.LabelFrame(self.overclock_tab, text="Guided Overclocking And Power Tuning", padding=12)
        card.pack(fill="both", expand=True)

        ttk.Label(
            card,
            text=(
                "Guided-only area. This tool does not write raw voltage, frequency, or fan-curve values. "
                "Use ASUS-approved controls and profile presets to avoid unstable settings."
            ),
            wraplength=890,
        ).pack(anchor="w", pady=(0, 10))

        self.oc_check_var = tk.StringVar(value="No overclock guidance checks run yet.")
        ttk.Label(card, textvariable=self.oc_check_var, justify="left", anchor="w", font=("Consolas", 10)).pack(
            anchor="w", fill="x", pady=(0, 10)
        )

        self._action_button(card, "Run Overclocking Readiness Check", self.run_overclocking_readiness_check)
        self._action_button(card, "Open ASUS Armoury Crate Download", self.open_armoury_crate_download)
        self._action_button(card, "Open ASUS G14 Support", self.open_asus_support_page)
        self._action_button(card, "Open NVIDIA Performance Tuning Guide", self.open_nvidia_tuning_guide)

    def _action_button(self, parent, text, command):
        btn = ttk.Button(parent, text=text)
        btn.configure(command=lambda: self._run_async(text, command, btn))
        btn.pack(fill="x", pady=4)
        return btn

    def _run_async(self, action_name, action, button=None):
        if button is not None:
            button.configure(state="disabled")

        def worker():
            action_id = self._next_action_id()
            action_tag = f"A{action_id:04d}"
            self._set_status(f"Running: {action_name}")
            self._log(f"[START][{action_tag}] {action_name}")
            started = perf_counter()
            status = "success"
            detail = ""
            try:
                result = action()
                if result:
                    self._log(f"[OK][{action_tag}] {result}")
                    detail = result
                else:
                    self._log(f"[OK][{action_tag}] Done.")
            except Exception as exc:
                status = "error"
                detail = str(exc)
                self._log(f"[ERROR][{action_tag}] {exc}")
                self._show_error("ASUS G14 Tune-Up Tool", f"Action failed:\n{exc}")
            finally:
                elapsed = perf_counter() - started
                self._log(f"[END][{action_tag}] {action_name} ({elapsed:.2f}s)")
                self._append_session_report(action_name, status, detail, action_tag, elapsed)
                self._set_status("Ready")
                if button is not None:
                    self._ui_call(lambda: button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _ui_call(self, fn):
        self.root.after(0, fn)

    def _set_status(self, text):
        self._ui_call(lambda: self.status_var.set(text))

    def _show_info(self, title, text):
        self._ui_call(lambda: messagebox.showinfo(title, text))

    def _show_warning(self, title, text):
        self._ui_call(lambda: messagebox.showwarning(title, text))

    def _show_error(self, title, text):
        self._ui_call(lambda: messagebox.showerror(title, text))

    def _ask_yes_no(self, title, text):
        if threading.current_thread() is threading.main_thread():
            return messagebox.askyesno(title, text)

        result = {"value": False}
        done = threading.Event()

        def ask():
            result["value"] = messagebox.askyesno(title, text)
            done.set()

        self._ui_call(ask)
        done.wait()
        return result["value"]

    def _log(self, text):
        def append():
            stamp = datetime.now().strftime("%H:%M:%S")
            thread_name = threading.current_thread().name
            line = f"[{stamp}][T:{thread_name}] {text}"
            category = self._classify_log_entry(text)
            self.log_entries.append({"line": line, "category": category})
            self._refresh_log_view()
            with self.session_txt.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        self._ui_call(append)

    def _classify_log_entry(self, text):
        upper = text.upper()
        if "[START]" in upper:
            return "START"
        if "[OK]" in upper:
            return "OK"
        if "[ERROR]" in upper:
            return "ERROR"
        if "ADMIN" in upper or "ADMINISTRATOR" in upper:
            return "ADMIN"
        return "INFO"

    def _refresh_log_view(self):
        selected = self.log_filter_var.get().upper() if hasattr(self, "log_filter_var") else "ALL"
        if selected == "":
            selected = "ALL"

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        for entry in self.log_entries:
            if selected != "ALL" and entry["category"] != selected:
                continue
            self.log_box.insert("end", entry["line"] + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _run_cmd(self, cmd):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            raise RuntimeError(err or out or f"Command failed with exit code {proc.returncode}")
        return out

    def _run_cmd_no_raise(self, cmd):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return f"ERROR: {err or out or f'exit code {proc.returncode}'}"
        return out

    def _cleanup_old_session_reports(self, days=30, max_files=120):
        cutoff = time() - (days * 86400)
        removed_by_age = 0
        removed_by_count = 0

        all_logs = [
            path
            for path in self.report_dir.glob("session_*")
            if path.is_file() and path.suffix.lower() in {".txt", ".csv"}
        ]

        for path in all_logs:
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed_by_age += 1
            except OSError:
                continue

        remaining = [
            path
            for path in self.report_dir.glob("session_*")
            if path.is_file() and path.suffix.lower() in {".txt", ".csv"}
        ]
        remaining.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for path in remaining[max_files:]:
            try:
                path.unlink(missing_ok=True)
                removed_by_count += 1
            except OSError:
                continue

        if removed_by_age == 0 and removed_by_count == 0:
            return ""
        return (
            f"Log cleanup completed: removed {removed_by_age} old file(s) and "
            f"{removed_by_count} extra file(s) beyond retention limit."
        )

    def _init_session_reports(self):
        with self.session_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "action_id", "action", "status", "duration_sec", "detail"])
        with self.session_txt.open("w", encoding="utf-8") as handle:
            handle.write(f"ASUS G14 Tune-Up Session {self.session_stamp}\n")

    def _append_session_report(self, action, status, detail, action_id="", duration_sec=None):
        with self.session_csv.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            duration_text = f"{duration_sec:.2f}" if isinstance(duration_sec, (int, float)) else ""
            writer.writerow([datetime.now().isoformat(timespec="seconds"), action_id, action, status, duration_text, detail])

    def _next_action_id(self):
        with self._action_lock:
            self._action_counter += 1
            return self._action_counter

    def _is_admin(self):
        if not self.is_windows:
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _require_admin(self, feature_name):
        if self._is_admin():
            return True
        self._show_warning(
            "Administrator Required",
            f"{feature_name} requires Administrator privileges. Relaunch this app as Administrator.",
        )
        return False

    def relaunch_as_admin(self):
        if not self.is_windows:
            return "Relaunch as admin is Windows-only."
        if self._is_admin():
            return "Already running as Administrator."

        self._log(f"Admin relaunch requested from: {Path(sys.argv[0]).resolve()}")

        if not self._ask_yes_no(
            "Relaunch As Administrator",
            "Relaunch this app with Administrator privileges now?",
        ):
            return "Admin relaunch cancelled by user."

        script_path = Path(sys.argv[0]).resolve()
        if script_path.suffix.lower() == ".py":
            params = f'"{script_path}"'
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        else:
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(script_path), None, None, 1)

        if result <= 32:
            raise RuntimeError("Could not elevate process through UAC prompt.")

        self.root.after(300, self.root.destroy)
        return "Requested admin relaunch."

    def open_current_activity_log(self):
        log_path = self.session_txt.resolve()
        if self.is_windows:
            subprocess.Popen(["notepad.exe", str(log_path)])
        return f"Opened current activity log: {log_path}"

    def open_reports_folder(self):
        folder = self.report_dir.resolve()
        if self.is_windows:
            subprocess.Popen(["explorer", str(folder)])
        return f"Opened reports folder: {folder}"

    def _get_temp_targets(self):
        return [
            os.environ.get("TEMP"),
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp"),
        ]

    def _scan_temp_targets(self):
        rows = []
        for path in self._get_temp_targets():
            count = 0
            total = 0
            if not path or not os.path.exists(path):
                rows.append((path or "<missing>", 0, 0))
                continue
            for root, _, files in os.walk(path, topdown=True, onerror=lambda _e: None):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        total += os.path.getsize(file_path)
                        count += 1
                    except OSError:
                        continue
            rows.append((path, count, total))
        return rows

    @staticmethod
    def _format_bytes(num_bytes):
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(num_bytes)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{num_bytes} B"

    def _get_drive_free_bytes(self):
        system_drive = os.environ.get("SystemDrive", "C:") + "\\"
        usage = shutil.disk_usage(system_drive)
        return usage.free, usage.total

    def refresh_health_snapshot(self):
        if not self.is_windows:
            return "Health metrics are Windows-focused."
        if psutil is None:
            return "psutil is not available. Install it to enable health metrics."

        cpu = psutil.cpu_percent(interval=0.4)
        mem = psutil.virtual_memory()
        free, total = self._get_drive_free_bytes()

        boot = datetime.fromtimestamp(psutil.boot_time())
        uptime_delta = datetime.now() - boot
        uptime_text = f"{uptime_delta.days}d {uptime_delta.seconds // 3600}h {(uptime_delta.seconds % 3600) // 60}m"

        battery = psutil.sensors_battery()
        if battery is None:
            battery_text = "Battery: unavailable"
        else:
            plug = "plugged in" if battery.power_plugged else "on battery"
            battery_text = f"Battery: {battery.percent:.0f}% ({plug})"

        procs = []
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                mem_bytes = proc.info["memory_info"].rss
                procs.append((proc.info["name"] or "unknown", mem_bytes))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, KeyError):
                continue
        procs.sort(key=lambda item: item[1], reverse=True)
        top_lines = [
            f"{name[:26]:26s} {self._format_bytes(mem_bytes):>10s}"
            for name, mem_bytes in procs[:8]
        ]
        if not top_lines:
            top_lines = ["No process data available."]

        self._ui_call(lambda: self.cpu_var.set(f"CPU: {cpu:.1f}%"))
        self._ui_call(lambda: self.ram_var.set(f"RAM: {mem.percent:.1f}% ({mem.available / (1024**3):.2f} GB available)"))
        self._ui_call(
            lambda: self.disk_var.set(
                f"C: Drive: {self._format_bytes(total - free)} used / {self._format_bytes(total)} total"
            )
        )
        self._ui_call(lambda: self.uptime_var.set(f"Uptime: {uptime_text}"))
        self._ui_call(lambda: self.battery_var.set(battery_text))
        self._ui_call(lambda: self.top_processes_text.set("\n".join(top_lines)))

        return "Health snapshot refreshed."

    def preview_temp_cleanup(self):
        rows = self._scan_temp_targets()
        lines = []
        total_files = 0
        total_bytes = 0
        for path, count, size in rows:
            lines.append(f"- {path}: {count} files, {self._format_bytes(size)}")
            total_files += count
            total_bytes += size

        summary = (
            "Temp cleanup preview:\n"
            + "\n".join(lines)
            + f"\nPotential cleanup: {total_files} files, {self._format_bytes(total_bytes)}"
        )
        self._show_info("Temp Cleanup Preview", summary)
        return f"Preview complete: {total_files} files, {self._format_bytes(total_bytes)} possible."

    def run_temp_cleanup(self):
        rows = self._scan_temp_targets()
        total_files = sum(row[1] for row in rows)
        total_bytes = sum(row[2] for row in rows)

        if self.cleanup_dry_run.get():
            return f"Dry-run enabled. Nothing deleted. Potential: {total_files} files, {self._format_bytes(total_bytes)}."

        if not self._ask_yes_no(
            "Confirm Cleanup",
            "Delete files from user TEMP and Windows Temp? In-use files will be skipped.",
        ):
            return "Cleanup cancelled by user."

        before_free, _ = self._get_drive_free_bytes()

        deleted_files = 0
        deleted_bytes = 0
        failed_items = 0

        for path in self._get_temp_targets():
            if not path or not os.path.exists(path):
                continue
            for entry in os.scandir(path):
                try:
                    if entry.is_file() or entry.is_symlink():
                        try:
                            size = entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            size = 0
                        os.unlink(entry.path)
                        deleted_files += 1
                        deleted_bytes += size
                    elif entry.is_dir(follow_symlinks=False):
                        dir_size = 0
                        for root, _, files in os.walk(entry.path, topdown=True, onerror=lambda _e: None):
                            for name in files:
                                try:
                                    dir_size += os.path.getsize(os.path.join(root, name))
                                except OSError:
                                    continue
                        shutil.rmtree(entry.path)
                        deleted_files += 1
                        deleted_bytes += dir_size
                except Exception:
                    failed_items += 1
                    continue

        after_free, _ = self._get_drive_free_bytes()
        freed_delta = max(0, after_free - before_free)

        return (
            f"Cleanup complete. Deleted entries: {deleted_files}, skipped: {failed_items}, "
            f"estimated removed: {self._format_bytes(deleted_bytes)}, "
            f"C: free-space delta: {self._format_bytes(freed_delta)}."
        )

    def apply_selected_tuning(self):
        if not self.is_windows:
            return "Tuning controls are Windows-only."

        power_map = {
            "High performance": "SCHEME_MIN",
            "Balanced": "SCHEME_BALANCED",
            "Power saver": "SCHEME_MAX",
        }
        visual_map = {
            "Best performance": "2",
            "Let Windows choose": "0",
            "Best appearance": "1",
        }

        selected_plan = self.power_plan_var.get()
        selected_fx = self.visual_fx_var.get()
        game_mode_value = "1" if self.game_mode_var.get() else "0"

        self._run_cmd(["powercfg", "/SETACTIVE", power_map[selected_plan]])
        self._run_cmd(
            [
                "reg",
                "add",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                "/v",
                "VisualFXSetting",
                "/t",
                "REG_DWORD",
                "/d",
                visual_map[selected_fx],
                "/f",
            ]
        )
        self._run_cmd(
            [
                "reg",
                "add",
                r"HKCU\Software\Microsoft\GameBar",
                "/v",
                "AutoGameModeEnabled",
                "/t",
                "REG_DWORD",
                "/d",
                game_mode_value,
                "/f",
            ]
        )

        plan_out = self._run_cmd_no_raise(["powercfg", "/GETACTIVESCHEME"])
        fx_out = self._run_cmd_no_raise(
            [
                "reg",
                "query",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                "/v",
                "VisualFXSetting",
            ]
        )
        game_out = self._run_cmd_no_raise(
            ["reg", "query", r"HKCU\Software\Microsoft\GameBar", "/v", "AutoGameModeEnabled"]
        )

        return "Tuning applied. Read-back checks:\n" + "\n".join([plan_out, fx_out, game_out])

    def detect_driver_versions(self):
        if not self.is_windows:
            return "Driver checks are Windows-only."

        ps_cmd = (
            "$video=Get-CimInstance Win32_VideoController | "
            "Select-Object Name,DriverVersion;"
            "$net=Get-CimInstance Win32_PnPSignedDriver | "
            "Where-Object {$_.DeviceClass -eq 'NET'} | "
            "Select-Object -First 8 DeviceName,DriverVersion,DriverProviderName;"
            "'Display Drivers:';"
            "$video | Format-Table -AutoSize | Out-String;"
            "'Network Drivers:';"
            "$net | Format-Table -AutoSize | Out-String"
        )
        out = self._run_cmd_no_raise(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        )
        if out.startswith("ERROR:"):
            return out

        self._log("Detected current display and network driver versions.")
        self._show_info("Driver Detection", out[:5000])
        return "Driver version detection complete."

    def _require_advanced_ready(self, action_name):
        if not self._require_admin(action_name):
            return False
        if self.advanced_preflight_ready:
            return True
        self._show_warning(
            "Preflight Required",
            "Run 'Advanced Safety Preflight' successfully before advanced driver/firmware actions.",
        )
        return False

    def open_windows_update_drivers(self):
        if not self._require_advanced_ready("Driver update workflow"):
            return "Skipped: preflight or admin requirement not met."
        subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:windowsupdate-advancedoptions"])
        return "Opened Windows Update advanced options."

    def open_nvidia_driver_page(self):
        if not self._require_advanced_ready("Driver update workflow"):
            return "Skipped: preflight or admin requirement not met."
        webbrowser.open("https://www.nvidia.com/Download/index.aspx")
        return "Opened NVIDIA driver download page."

    def _get_system_model(self):
        if not self.is_windows:
            return "Unknown"
        ps_cmd = "(Get-CimInstance Win32_ComputerSystem).Model"
        out = self._run_cmd_no_raise(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        )
        if out.startswith("ERROR:") or not out:
            return "Unknown"
        return out.splitlines()[-1].strip()

    def open_asus_support_page(self):
        if not self._require_advanced_ready("Driver update workflow"):
            return "Skipped: preflight or admin requirement not met."
        model = self._get_system_model()
        query = model.replace(" ", "+") if model and model != "Unknown" else "ROG+Zephyrus+G14"
        webbrowser.open(f"https://www.asus.com/supportonly/{query}/helpdesk_download/")
        return f"Opened ASUS support page lookup for model: {model}."

    def open_armoury_crate_download(self):
        webbrowser.open("https://www.asus.com/supportonly/armoury%20crate/helpdesk_download/")
        return "Opened ASUS Armoury Crate download page."

    def open_nvidia_tuning_guide(self):
        webbrowser.open("https://www.nvidia.com/en-us/geforce/news/nvidia-app-performance-panel-beta/")
        return "Opened NVIDIA performance tuning guidance page."

    def refresh_firmware_info(self):
        if not self.is_windows:
            return "Firmware detection is Windows-only."

        ps_cmd = (
            "$cs=Get-CimInstance Win32_ComputerSystem;"
            "$bios=Get-CimInstance Win32_BIOS;"
            "$date=([Management.ManagementDateTimeConverter]::ToDateTime($bios.ReleaseDate)).ToString('yyyy-MM-dd');"
            "Write-Output ($cs.Model);"
            "Write-Output ($bios.SMBIOSBIOSVersion);"
            "Write-Output ($date)"
        )
        out = self._run_cmd_no_raise(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
        )
        if out.startswith("ERROR:"):
            return out

        lines = [line.strip() for line in out.splitlines() if line.strip()]
        model = lines[0] if len(lines) > 0 else "Unknown"
        bios = lines[1] if len(lines) > 1 else "Unknown"
        rel_date = lines[2] if len(lines) > 2 else "Unknown"

        self._ui_call(lambda: self.model_var.set(f"Model: {model}"))
        self._ui_call(lambda: self.bios_var.set(f"BIOS Version: {bios}"))
        self._ui_call(lambda: self.bios_date_var.set(f"BIOS Date: {rel_date}"))
        return "Firmware info refreshed."

    def _check_ac_and_battery(self):
        if psutil is None:
            return False, "psutil is required for battery checks."
        battery = psutil.sensors_battery()
        if battery is None:
            return False, "Battery details unavailable. Cannot verify AC and battery threshold."
        if not battery.power_plugged:
            return False, "AC adapter is not connected. Connect AC power before firmware workflow."
        if battery.percent < 50:
            return False, f"Battery is {battery.percent:.0f}%. Minimum required is 50%."
        return True, f"Power check passed: {battery.percent:.0f}% and AC connected."

    def _create_restore_point(self):
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Checkpoint-Computer -Description 'ASUSG14Tuneup' -RestorePointType MODIFY_SETTINGS",
        ]
        out = self._run_cmd_no_raise(cmd)
        if out.startswith("ERROR:"):
            return False, out
        return True, "Restore point command completed."

    def _export_registry_backup(self):
        backup_dir = self.report_dir / f"registry_backup_{self.session_stamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        targets = [
            (r"HKCU\Software\Microsoft\GameBar", backup_dir / "gamebar.reg"),
            (
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                backup_dir / "visualeffects.reg",
            ),
        ]

        exported = 0
        for key, path in targets:
            query = self._run_cmd_no_raise(["reg", "query", key])
            if query.startswith("ERROR:"):
                continue
            out = self._run_cmd_no_raise(["reg", "export", key, str(path), "/y"])
            if not out.startswith("ERROR:"):
                exported += 1

        if exported == 0:
            return False, "Could not export required registry keys."
        return True, f"Registry backup created in: {backup_dir}"

    def run_advanced_safety_preflight(self):
        if not self.is_windows:
            return "Preflight is Windows-only."
        if not self._require_admin("Advanced Safety Preflight"):
            self.advanced_preflight_ready = False
            return "Preflight failed: admin privileges are required."

        power_ok, power_msg = self._check_ac_and_battery()
        if not power_ok:
            self.advanced_preflight_ready = False
            return f"Preflight failed: {power_msg}"

        restore_ok, restore_msg = self._create_restore_point()
        if not restore_ok:
            self.advanced_preflight_ready = False
            return f"Preflight failed at restore-point step: {restore_msg}"

        backup_ok, backup_msg = self._export_registry_backup()
        if not backup_ok:
            self.advanced_preflight_ready = False
            return f"Preflight failed at registry-backup step: {backup_msg}"

        self.advanced_preflight_ready = True
        return f"Preflight passed. {power_msg} {restore_msg} {backup_msg}"

    def open_asus_firmware_support(self):
        if not self._require_advanced_ready("Firmware workflow"):
            return "Skipped: preflight or admin requirement not met."

        model = self._get_system_model()
        query = model.replace(" ", "+") if model and model != "Unknown" else "ROG+Zephyrus+G14"
        webbrowser.open(f"https://www.asus.com/supportonly/{query}/helpdesk_bios/")
        self._show_warning(
            "Firmware Guidance",
            "Use only official ASUS BIOS files for your exact model and follow ASUS flashing instructions. "
            "This tool does not perform BIOS flashing directly.",
        )
        return f"Opened ASUS BIOS/Firmware page for model lookup: {model}."

    def run_overclocking_readiness_check(self):
        if not self.is_windows:
            return "Overclocking readiness check is Windows-only."

        model = self._get_system_model()
        active_plan = self._run_cmd_no_raise(["powercfg", "/GETACTIVESCHEME"])
        armoury_service = self._run_cmd_no_raise(["sc", "query", "ArmouryCrateService"])
        nvidia_smi = self._run_cmd_no_raise(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])

        lines = [
            f"Model: {model}",
            f"Power plan: {active_plan.splitlines()[-1] if active_plan else 'Unknown'}",
            f"Armoury Crate Service: {'Detected' if 'RUNNING' in armoury_service or 'STOPPED' in armoury_service else 'Not detected'}",
            f"NVIDIA Telemetry: {nvidia_smi if not nvidia_smi.startswith('ERROR:') else 'nvidia-smi not available'}",
            "Safety checklist:",
            "1) Keep AC connected and battery above 50%.",
            "2) Use profile-based tuning only (Turbo/Performance/Balanced).",
            "3) Stress test after each change and revert if unstable.",
            "4) Avoid BIOS-level frequency/voltage edits unless vendor-documented.",
        ]
        message = "\n".join(lines)
        self._ui_call(lambda: self.oc_check_var.set(message))
        return "Overclocking readiness check complete."


def main():
    root = tk.Tk()
    app = AsusG14TuneupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()