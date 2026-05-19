import csv
import io
import os
import platform
import shutil
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText


class NightOwlTuningApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Night Owl Tuning")
        self.root.geometry("980x760")
        self.root.minsize(900, 680)

        self.style = ttk.Style()
        self.style.theme_use("clam")

        self._build_ui()
        self.refresh_disk_space()

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(14, 12))
        header.pack(fill="x")

        title = ttk.Label(header, text="Night Owl Tuning", font=("Segoe UI", 20, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            header,
            text=(
                "Windows performance toolkit: updates, startup control, storage cleanup, "
                "security checks, and system tuning helpers."
            ),
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.system_tab = ttk.Frame(self.notebook, padding=12)
        self.storage_tab = ttk.Frame(self.notebook, padding=12)
        self.hardware_tab = ttk.Frame(self.notebook, padding=12)
        self.security_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.system_tab, text="System")
        self.notebook.add(self.storage_tab, text="Storage")
        self.notebook.add(self.hardware_tab, text="Hardware")
        self.notebook.add(self.security_tab, text="Security")

        self._build_system_tab()
        self._build_storage_tab()
        self._build_hardware_tab()
        self._build_security_tab()

        log_wrap = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.log_box = ScrolledText(log_wrap, height=10, font=("Consolas", 10), state="disabled")
        self.log_box.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(12, 0, 12, 10))
        status.pack(fill="x")

    def _build_system_tab(self):
        grid = ttk.Frame(self.system_tab)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        left = ttk.LabelFrame(grid, text="Software and Startup", padding=10)
        right = ttk.LabelFrame(grid, text="Performance Controls", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))

        self._action_button(left, "Open Windows Update", self.open_windows_update)
        self._action_button(left, "Upgrade Installed Apps (winget)", self.upgrade_with_winget)
        self._action_button(left, "Open GPU Driver Pages", self.open_gpu_driver_pages)
        self._action_button(left, "Open Startup Apps Manager", self.open_startup_manager)
        self._action_button(left, "Open Uninstall Apps", self.open_uninstall_apps)
        self._action_button(left, "Background Process Manager", self.open_process_manager)

        self._action_button(right, "Apply Best Performance Visual Effects", self.apply_visual_effects)
        self._action_button(right, "Enable Game Mode", self.enable_game_mode)
        self._action_button(right, "Set High Performance Power Plan", self.set_high_performance)
        self._action_button(right, "Open Control Panel", self.open_control_panel)

        note = ttk.Label(
            self.system_tab,
            text=(
                "Tip: driver updates are hardware-specific, so this app opens the correct vendor pages "
                "while also giving you Windows Update and winget upgrade controls."
            ),
            foreground="#555555",
            wraplength=900,
        )
        note.pack(anchor="w", pady=(4, 0))

    def _build_storage_tab(self):
        wrap = ttk.Frame(self.storage_tab)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.columnconfigure(1, weight=1)

        left = ttk.LabelFrame(wrap, text="Cleanup", padding=10)
        right = ttk.LabelFrame(wrap, text="Drive Health", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))

        self._action_button(left, "Run Disk Cleanup", self.run_disk_cleanup)
        self._action_button(left, "Enable Storage Sense", self.enable_storage_sense)
        self._action_button(left, "Open Storage Settings", self.open_storage_settings)
        self._action_button(left, "Optimize Drives", self.optimize_drives)

        self.disk_label_var = tk.StringVar(value="C: drive free space: checking...")
        ttk.Label(right, textvariable=self.disk_label_var, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 12))

        self._action_button(right, "Refresh Disk Space Status", self.refresh_disk_space)

        self.disk_hint_var = tk.StringVar(value="Goal: keep at least 15-20% free space on C: for best performance.")
        ttk.Label(right, textvariable=self.disk_hint_var, wraplength=380, foreground="#444444").pack(anchor="w")

    def _build_hardware_tab(self):
        card = ttk.LabelFrame(self.hardware_tab, text="Hardware and Environmental", padding=12)
        card.pack(fill="both", expand=True)

        ttk.Label(
            card,
            text=(
                "This section covers tasks that cannot be fully automated by software, "
                "plus one-click launchers for required Windows pages."
            ),
            wraplength=840,
        ).pack(anchor="w", pady=(0, 10))

        self._action_button(card, "Open Power Options", self.open_power_options)
        self._action_button(card, "Set High Performance Power Plan", self.set_high_performance)
        self._action_button(card, "Dust Cleaning Checklist", self.show_dust_checklist)

    def _build_security_tab(self):
        card = ttk.LabelFrame(self.security_tab, text="Security and Stability", padding=12)
        card.pack(fill="both", expand=True)

        self._action_button(card, "Run Windows Defender Quick Scan", self.run_defender_quick_scan)
        self._action_button(card, "Open Windows Security", self.open_windows_security)
        self._action_button(card, "Restart Computer (10s delay)", self.restart_computer)

        ttk.Label(
            card,
            text=(
                "Regular restarts clear stale memory and stuck background tasks. "
                "Use the restart action when you have saved your work."
            ),
            wraplength=840,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 0))

    def _action_button(self, parent, text, command):
        btn = ttk.Button(parent, text=text, command=lambda: self._run_async(text, command))
        btn.pack(fill="x", pady=4)
        return btn

    def _run_async(self, action_name, action):
        def worker():
            self._set_status(f"Running: {action_name}")
            self._log(f"[START] {action_name}")
            action_status = "success"
            action_error = ""
            try:
                result = action()
                if result:
                    self._log(f"[OK] {result}")
                else:
                    self._log("[OK] Done.")
            except Exception as exc:
                action_status = "error"
                action_error = str(exc)
                self._log(f"[ERROR] {exc}")
                messagebox.showerror("Night Owl Tuning", f"Action failed:\n{exc}")
            finally:
                try:
                    report_paths = self.export_health_report(action_name, action_status, action_error)
                    self._log(f"[REPORT] TXT: {report_paths['txt']}")
                    self._log(f"[REPORT] CSV: {report_paths['csv']}")
                except Exception as rep_exc:
                    self._log(f"[REPORT-ERROR] Could not export health report: {rep_exc}")
                self._set_status("Ready")

        threading.Thread(target=worker, daemon=True).start()

    def _log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text):
        self.status_var.set(text)

    def _run_cmd(self, cmd, shell=False):
        proc = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            msg = err or out or f"Command failed with exit code {proc.returncode}"
            raise RuntimeError(msg)
        return out

    def _run_cmd_no_raise(self, cmd, shell=False):
        proc = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return f"ERROR: {err or out or f'exit code {proc.returncode}'}"
        return out

    def _get_top_processes(self, limit=15):
        output = self._run_cmd_no_raise(["tasklist", "/FO", "CSV", "/NH"])
        if output.startswith("ERROR:"):
            return []

        rows = []
        reader = csv.reader(io.StringIO(output))
        for parts in reader:
            if len(parts) < 5:
                continue
            name, pid, _, _, mem = parts
            mem_num = int(mem.replace(",", "").replace(" K", "").strip()) if "K" in mem else 0
            rows.append((name, pid, mem, mem_num))
        rows.sort(key=lambda r: r[3], reverse=True)
        return rows[:limit]

    def _get_startup_count(self):
        ps_cmd = (
            "(Get-CimInstance Win32_StartupCommand | Measure-Object).Count"
        )
        out = self._run_cmd_no_raise([
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_cmd,
        ])
        return out if out else "Unknown"

    def _get_uptime(self):
        ps_cmd = (
            "$os=Get-CimInstance Win32_OperatingSystem;"
            "$boot=$os.LastBootUpTime;"
            "$ts=(Get-Date)-$boot;"
            "'{0}d {1}h {2}m' -f $ts.Days,$ts.Hours,$ts.Minutes"
        )
        return self._run_cmd_no_raise([
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_cmd,
        ])

    def export_health_report(self, action_name, action_status, action_error):
        timestamp = datetime.now()
        stamp = timestamp.strftime("%Y%m%d_%H%M%S")

        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        report_dir = os.path.join(workspace_root, "reports", "night_owl_tuning")
        os.makedirs(report_dir, exist_ok=True)

        txt_path = os.path.join(report_dir, f"night_owl_report_{stamp}.txt")
        csv_path = os.path.join(report_dir, f"night_owl_report_{stamp}.csv")

        total, used, free = shutil.disk_usage("C:\\")
        free_pct = (free / total) * 100

        power_plan = self._run_cmd_no_raise(["powercfg", "/GETACTIVESCHEME"])
        game_mode = self._run_cmd_no_raise([
            "reg",
            "query",
            r"HKCU\Software\Microsoft\GameBar",
            "/v",
            "AutoGameModeEnabled",
        ])
        defender_realtime = self._run_cmd_no_raise([
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-MpComputerStatus).RealTimeProtectionEnabled",
        ])
        startup_count = self._get_startup_count()
        uptime = self._get_uptime()
        top_procs = self._get_top_processes(limit=15)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("Night Owl Tuning - Health Report\n")
            f.write("=" * 44 + "\n")
            f.write(f"Timestamp: {timestamp.isoformat()}\n")
            f.write(f"Action: {action_name}\n")
            f.write(f"Action status: {action_status}\n")
            if action_error:
                f.write(f"Action error: {action_error}\n")
            f.write("\n")
            f.write("System\n")
            f.write("-" * 44 + "\n")
            f.write(f"Hostname: {platform.node()}\n")
            f.write(f"OS: {platform.platform()}\n")
            f.write(f"Uptime: {uptime}\n")
            f.write("\n")
            f.write("Storage\n")
            f.write("-" * 44 + "\n")
            f.write(f"C: Total GB: {total / (1024 ** 3):.2f}\n")
            f.write(f"C: Used GB: {used / (1024 ** 3):.2f}\n")
            f.write(f"C: Free GB: {free / (1024 ** 3):.2f}\n")
            f.write(f"C: Free %: {free_pct:.2f}\n")
            f.write("\n")
            f.write("Tuning Status\n")
            f.write("-" * 44 + "\n")
            f.write(f"Power plan query: {power_plan}\n")
            f.write(f"Game mode query: {game_mode}\n")
            f.write(f"Defender realtime protection: {defender_realtime}\n")
            f.write(f"Startup item count: {startup_count}\n")
            f.write("\n")
            f.write("Top Processes by Memory\n")
            f.write("-" * 44 + "\n")
            for name, pid, mem, _ in top_procs:
                f.write(f"{name:30} PID={pid:>6}  MEM={mem}\n")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["section", "key", "value"])
            writer.writerow(["meta", "timestamp", timestamp.isoformat()])
            writer.writerow(["meta", "action", action_name])
            writer.writerow(["meta", "action_status", action_status])
            writer.writerow(["meta", "action_error", action_error])

            writer.writerow(["system", "hostname", platform.node()])
            writer.writerow(["system", "os", platform.platform()])
            writer.writerow(["system", "uptime", uptime])

            writer.writerow(["storage", "c_total_gb", f"{total / (1024 ** 3):.2f}"])
            writer.writerow(["storage", "c_used_gb", f"{used / (1024 ** 3):.2f}"])
            writer.writerow(["storage", "c_free_gb", f"{free / (1024 ** 3):.2f}"])
            writer.writerow(["storage", "c_free_pct", f"{free_pct:.2f}"])

            writer.writerow(["tuning", "power_plan", power_plan])
            writer.writerow(["tuning", "game_mode", game_mode])
            writer.writerow(["tuning", "defender_realtime_protection", defender_realtime])
            writer.writerow(["tuning", "startup_count", startup_count])

            writer.writerow(["process", "name", "pid", "memory"])
            for name, pid, mem, _ in top_procs:
                writer.writerow(["process", name, pid, mem])

        return {"txt": txt_path, "csv": csv_path}

    def _open_uri(self, uri):
        os.startfile(uri)
        return f"Opened: {uri}"

    def open_windows_update(self):
        self._open_uri("ms-settings:windowsupdate")
        return "Windows Update opened."

    def upgrade_with_winget(self):
        out = self._run_cmd([
            "winget",
            "upgrade",
            "--all",
            "--include-unknown",
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ])
        return out or "winget upgrades finished."

    def open_gpu_driver_pages(self):
        import webbrowser

        webbrowser.open("https://www.nvidia.com/Download/index.aspx")
        webbrowser.open("https://www.amd.com/en/support")
        webbrowser.open("https://www.intel.com/content/www/us/en/download-center/home.html")
        return "Opened Nvidia, AMD, and Intel driver pages in your browser."

    def open_startup_manager(self):
        self._open_uri("ms-settings:startupapps")
        return "Startup Apps settings opened. Disable non-essential startup entries there."

    def open_uninstall_apps(self):
        self._open_uri("ms-settings:appsfeatures")
        return "Apps and Features opened for uninstalling unused software."

    def open_process_manager(self):
        ProcessManagerWindow(self.root, self._log)
        return "Opened background process manager."

    def apply_visual_effects(self):
        self._run_cmd([
            "reg",
            "add",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
            "/v",
            "VisualFXSetting",
            "/t",
            "REG_DWORD",
            "/d",
            "2",
            "/f",
        ])
        return "Set visual effects to Best performance. Sign out/restart may be needed for full effect."

    def enable_game_mode(self):
        self._run_cmd([
            "reg",
            "add",
            r"HKCU\Software\Microsoft\GameBar",
            "/v",
            "AutoGameModeEnabled",
            "/t",
            "REG_DWORD",
            "/d",
            "1",
            "/f",
        ])
        self._run_cmd([
            "reg",
            "add",
            r"HKCU\Software\Microsoft\GameBar",
            "/v",
            "AllowAutoGameMode",
            "/t",
            "REG_DWORD",
            "/d",
            "1",
            "/f",
        ])
        return "Game Mode enabled in registry."

    def run_disk_cleanup(self):
        self._run_cmd(["cleanmgr", "/verylowdisk"])
        return "Disk Cleanup completed."

    def enable_storage_sense(self):
        self._run_cmd([
            "reg",
            "add",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy",
            "/v",
            "01",
            "/t",
            "REG_DWORD",
            "/d",
            "1",
            "/f",
        ])
        self._open_uri("ms-settings:storagesense")
        return "Storage Sense enabled and settings page opened."

    def open_storage_settings(self):
        self._open_uri("ms-settings:storagesense")
        return "Storage settings opened."

    def optimize_drives(self):
        out = self._run_cmd(["defrag", "C:", "/O", "/U", "/V"])
        return out or "Optimize drives completed."

    def refresh_disk_space(self):
        total, used, free = shutil.disk_usage("C:\\")
        free_pct = (free / total) * 100
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)

        self.disk_label_var.set(f"C: drive free space: {free_gb:.1f} GB / {total_gb:.1f} GB ({free_pct:.1f}% free)")

        if free_pct < 15:
            self.disk_hint_var.set("Warning: below 15% free. Cleanup is strongly recommended.")
        elif free_pct < 20:
            self.disk_hint_var.set("Caution: below 20% free. More free space can improve performance.")
        else:
            self.disk_hint_var.set("Healthy: free space is within the recommended range.")

        self._log("Disk space status refreshed.")
        return "Disk space check complete."

    def set_high_performance(self):
        self._run_cmd(["powercfg", "/SETACTIVE", "SCHEME_MIN"])
        return "Power plan set to High performance."

    def open_control_panel(self):
        self._run_cmd(["control"])
        return "Control Panel opened."

    def open_power_options(self):
        self._run_cmd(["control", "/name", "Microsoft.PowerOptions"])
        return "Power Options opened."

    def show_dust_checklist(self):
        message = (
            "Dust Cleaning Checklist:\n\n"
            "1) Shut down and unplug the PC.\n"
            "2) Ground yourself to avoid static discharge.\n"
            "3) Use compressed air on fans, heatsinks, vents, and PSU intake.\n"
            "4) Hold fan blades in place while blowing air.\n"
            "5) Reconnect and boot; monitor temperatures afterward."
        )
        messagebox.showinfo("Night Owl Tuning", message)
        return "Displayed dust cleaning checklist."

    def run_defender_quick_scan(self):
        out = self._run_cmd([
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Start-MpScan -ScanType QuickScan",
        ])
        return out or "Windows Defender quick scan started."

    def open_windows_security(self):
        self._open_uri("windowsdefender:")
        return "Windows Security opened."

    def restart_computer(self):
        confirmed = messagebox.askyesno(
            "Night Owl Tuning",
            "Restart the computer in 10 seconds? Save any open work first.",
        )
        if not confirmed:
            return "Restart canceled by user."
        self._run_cmd(["shutdown", "/r", "/t", "10"])
        return "Restart scheduled in 10 seconds."


class ProcessManagerWindow:
    def __init__(self, parent, logger):
        self.logger = logger
        self.win = tk.Toplevel(parent)
        self.win.title("Background Process Manager")
        self.win.geometry("780x500")

        top = ttk.Frame(self.win, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="End Selected Process", command=self.kill_selected).pack(side="left")

        self.tree = ttk.Treeview(self.win, columns=("name", "pid", "mem"), show="headings")
        self.tree.heading("name", text="Process")
        self.tree.heading("pid", text="PID")
        self.tree.heading("mem", text="Memory")
        self.tree.column("name", width=420)
        self.tree.column("pid", width=100, anchor="center")
        self.tree.column("mem", width=180, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.refresh()

    def _read_tasklist(self):
        output = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, encoding="utf-8", errors="ignore")
        rows = []
        reader = csv.reader(io.StringIO(output))
        for parts in reader:
            if len(parts) < 5:
                continue
            name, pid, _, _, mem = parts
            mem_num = int(mem.replace(",", "").replace(" K", "").strip()) if "K" in mem else 0
            rows.append((name, pid, mem, mem_num))
        rows.sort(key=lambda r: r[3], reverse=True)
        return rows

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for name, pid, mem, _ in self._read_tasklist()[:250]:
                self.tree.insert("", "end", values=(name, pid, mem))
            self.logger("Process list refreshed.")
        except Exception as exc:
            messagebox.showerror("Night Owl Tuning", f"Could not read process list:\n{exc}")

    def kill_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Night Owl Tuning", "Select a process first.")
            return

        row = self.tree.item(selected[0], "values")
        name, pid, _ = row
        ok = messagebox.askyesno("Night Owl Tuning", f"End process {name} (PID {pid})?")
        if not ok:
            return

        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True, capture_output=True, text=True)
            self.logger(f"Ended process: {name} (PID {pid})")
            self.refresh()
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or str(exc)).strip()
            messagebox.showerror("Night Owl Tuning", f"Could not end process:\n{err}")


def main():
    root = tk.Tk()
    app = NightOwlTuningApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
