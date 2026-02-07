# ...existing code...
import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date

# Simple restaurant daily log GUI
# Features:
# - Select date and shift (Day/Night)
# - Cash drawer audits: beginning, mid, closing
# - Shift deposits: opening shift, closing shift
# - Add/remove employee entries (Name, Area, Cash, Credit Total, CC Received, Voids, Beer, Liquor, Wine, Food)
# - View running totals by Area and Period
# - Save per-day CSV in ~/Documents/AIO Python/daily_logs/

OUT_DIR = os.path.expanduser(
    "~/Documents/AIO Python/daily_logs"
)
os.makedirs(OUT_DIR, exist_ok=True)


class DailyLogApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Restaurant Daily Log")
        self.geometry("1100x750")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)

        self._build_header()
        self._build_audit_section()
        self._build_deposits_section()
        self._build_employee_section()
        self._build_summary_section()
        self._build_actions()

        self._update_totals()

    def _build_header(self):
        """Build modern header section"""
        header_frame = tk.Frame(self.main_frame, bg="#2c2c2c", height=80)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="Daily Log",
            font=("Arial", 24, "bold"),
            bg="#2c2c2c",
            fg="white"
        )
        title_label.pack(side="top", pady=(10, 5))
        
        # Date and shift selectors row
        date_frame = tk.Frame(header_frame, bg="#2c2c2c")
        date_frame.pack(side="top", pady=5)
        
        tk.Label(date_frame, text="Date:", bg="#2c2c2c", fg="white", font=("Arial", 10)).pack(side="left", padx=5)
        
        # Month dropdown
        self.month_var = tk.StringVar(value=str(datetime.now().month).zfill(2))
        month_menu = tk.OptionMenu(date_frame, self.month_var, *[f"{i:02d}" for i in range(1, 13)])
        month_menu.config(width=3, font=("Arial", 10))
        month_menu.pack(side="left")
        
        tk.Label(date_frame, text="/", bg="#2c2c2c", fg="white", font=("Arial", 10)).pack(side="left")
        
        # Day dropdown
        self.day_var = tk.StringVar(value=str(datetime.now().day).zfill(2))
        day_menu = tk.OptionMenu(date_frame, self.day_var, *[f"{i:02d}" for i in range(1, 32)])
        day_menu.config(width=3, font=("Arial", 10))
        day_menu.pack(side="left")
        
        tk.Label(date_frame, text="/", bg="#2c2c2c", fg="white", font=("Arial", 10)).pack(side="left")
        
        # Year dropdown
        current_year = datetime.now().year
        self.year_var = tk.StringVar(value=str(current_year))
        year_menu = tk.OptionMenu(date_frame, self.year_var, *[str(year) for year in range(current_year-5, current_year+2)])
        year_menu.config(width=5, font=("Arial", 10))
        year_menu.pack(side="left")
        
        tk.Label(date_frame, text="Shift:", bg="#2c2c2c", fg="white", font=("Arial", 10)).pack(side="left", padx=(15, 5))
        self.shift_var = tk.StringVar(value="Day")
        shift_menu = tk.OptionMenu(date_frame, self.shift_var, "Day", "Night")
        shift_menu.config(width=6, font=("Arial", 10))
        shift_menu.pack(side="left")
        
        tk.Label(date_frame, text="Notes:", bg="#2c2c2c", fg="white", font=("Arial", 10)).pack(side="left", padx=(15, 5))
        self.notes_var = tk.StringVar()
        notes_entry = tk.Entry(date_frame, textvariable=self.notes_var, width=30, font=("Arial", 10))
        notes_entry.pack(side="left", padx=5)

    def _build_audit_section(self):
        """Build modern cash audit section"""
        audit_frame = ttk.LabelFrame(self.main_frame, text="Cash Audit", padding="10")
        audit_frame.pack(fill="x", padx=10, pady=5)
        
        self.audit_vars = {}
        audit_labels = ["Beginning of Shift:", "Mid Shift:", "Closing:"]
        for i, label in enumerate(audit_labels):
            tk.Label(audit_frame, text=label, font=("Arial", 10)).grid(row=i, column=0, sticky="w", padx=5, pady=3)
            self.audit_vars[label] = tk.StringVar()
            entry = tk.Entry(audit_frame, textvariable=self.audit_vars[label], width=15, font=("Arial", 10))
            entry.grid(row=i, column=1, padx=5, pady=3)

    def _build_deposits_section(self):
        lab = tk.LabelFrame(self, text="Deposits",
                           bg="white", fg="#333333",
                           font=("Helvetica", 10, "bold"),
                           relief="solid", bd=1)
        lab.pack(fill="x", padx=5, pady=3)

        container = tk.Frame(lab, bg="white")
        container.pack(fill="x", padx=5, pady=5)

        tk.Label(container, text="Opening:", bg="white", fg="#666666",
                font=("Helvetica", 8)).grid(row=0, column=0, sticky="w", padx=2, pady=1)
        self.open_deposit_var = tk.StringVar(value="0.00")
        ttk.Entry(container, textvariable=self.open_deposit_var, width=10,
                 font=("Helvetica", 8)).grid(row=0, column=1, padx=2)

        tk.Label(container, text="Closing:", bg="white", fg="#666666",
                font=("Helvetica", 8)).grid(row=1, column=0, sticky="w", padx=2, pady=1)
        self.close_deposit_var = tk.StringVar(value="0.00")
        ttk.Entry(container, textvariable=self.close_deposit_var, width=10,
                 font=("Helvetica", 8)).grid(row=1, column=1, padx=2)

    def _build_employee_section(self):
        lab = tk.LabelFrame(self, text="Employees",
                           bg="white", fg="#333333",
                           font=("Helvetica", 10, "bold"),
                           relief="solid", bd=1)
        lab.pack(fill="both", expand=True, padx=5, pady=3)

        # Simplified form for mobile - key fields only
        form_frame = tk.Frame(lab, bg="white")
        form_frame.pack(fill="x", padx=5, pady=5)

        # Name
        tk.Label(form_frame, text="Name:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.name_var, width=20, 
                 font=("Helvetica", 8)).grid(row=0, column=1, columnspan=2, sticky="ew", padx=2, pady=2)
        
        # Area and Cash
        tk.Label(form_frame, text="Area:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.area_var = tk.StringVar(value="Dining")
        ttk.Combobox(form_frame, textvariable=self.area_var, values=["Dining", "Bar", "To Out"],
                    width=8, state="readonly", font=("Helvetica", 8)).grid(row=1, column=1, padx=2, pady=2)
        
        tk.Label(form_frame, text="Cash:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=1, column=2, sticky="w", padx=2, pady=2)
        self.cash_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.cash_var, width=8,
                 font=("Helvetica", 8)).grid(row=1, column=3, padx=2, pady=2)
        
        # Credit and CC
        tk.Label(form_frame, text="Credit:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.credit_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.credit_var, width=8,
                 font=("Helvetica", 8)).grid(row=2, column=1, padx=2, pady=2)
        
        tk.Label(form_frame, text="CC:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=2, column=2, sticky="w", padx=2, pady=2)
        self.cc_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.cc_var, width=8,
                 font=("Helvetica", 8)).grid(row=2, column=3, padx=2, pady=2)
        
        # Voids and Food
        tk.Label(form_frame, text="Voids:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.voids_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.voids_var, width=8,
                 font=("Helvetica", 8)).grid(row=3, column=1, padx=2, pady=2)
        
        tk.Label(form_frame, text="Food:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=3, column=2, sticky="w", padx=2, pady=2)
        self.food_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.food_var, width=8,
                 font=("Helvetica", 8)).grid(row=3, column=3, padx=2, pady=2)
        
        # Drinks row
        tk.Label(form_frame, text="Beer:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=4, column=0, sticky="w", padx=2, pady=2)
        self.beer_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.beer_var, width=6,
                 font=("Helvetica", 8)).grid(row=4, column=1, padx=2, pady=2)
        
        tk.Label(form_frame, text="Liq:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=4, column=2, sticky="w", padx=2, pady=2)
        self.liquor_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.liquor_var, width=6,
                 font=("Helvetica", 8)).grid(row=4, column=3, padx=2, pady=2)
        
        tk.Label(form_frame, text="Wine:", bg="white", fg="#666666",
                font=("Helvetica", 8, "bold")).grid(row=5, column=0, sticky="w", padx=2, pady=2)
        self.wine_var = tk.StringVar(value="0.00")
        ttk.Entry(form_frame, textvariable=self.wine_var, width=8,
                 font=("Helvetica", 8)).grid(row=5, column=1, padx=2, pady=2)
        
        # Store entry vars for compatibility
        self.entry_vars = {
            "name": self.name_var,
            "area": self.area_var,
            "cash": self.cash_var,
            "credit_total": self.credit_var,
            "cc_received": self.cc_var,
            "voids": self.voids_var,
            "beer": self.beer_var,
            "liquor": self.liquor_var,
            "wine": self.wine_var,
            "food": self.food_var,
        }

        btn_frame = tk.Frame(lab, bg="white")
        btn_frame.pack(fill="x", padx=5, pady=5)
        
        add_btn = tk.Button(btn_frame, text="Add", command=self._add_employee,
                           bg="#3a3a3a", fg="white", font=("Helvetica", 8, "bold"),
                           activebackground="#1a1a1a", activeforeground="white",
                           relief="flat", cursor="hand2", padx=10, pady=3)
        add_btn.pack(side="left", padx=2)
        
        remove_btn = tk.Button(btn_frame, text="Remove", command=self._remove_selected,
                              bg="#4a4a4a", fg="white", font=("Helvetica", 8, "bold"),
                              activebackground="#2a2a2a", activeforeground="white",
                              relief="flat", cursor="hand2", padx=10, pady=3)
        remove_btn.pack(side="left", padx=2)
        
        clear_btn = tk.Button(btn_frame, text="Clear", command=self._clear_all,
                             bg="#5a5a5a", fg="white", font=("Helvetica", 8, "bold"),
                             activebackground="#3a3a3a", activeforeground="white",
                             relief="flat", cursor="hand2", padx=10, pady=3)
        clear_btn.pack(side="left", padx=2)

        # Simplified list view
        list_frame = tk.Frame(lab, bg="white")
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tk.Label(list_frame, text="Entries:", bg="white", fg="#333333",
                font=("Helvetica", 8, "bold")).pack(anchor="w")
        
        # Simple listbox instead of treeview for mobile
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.entries_listbox = tk.Listbox(list_frame, font=("Courier", 7),
                                          yscrollcommand=scrollbar.set,
                                          height=6, bg="#f9f9f9")
        self.entries_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.entries_listbox.yview)
        
        # Keep tree data structure for compatibility
        class SimpleTree:
            def __init__(self):
                self.items = []
            
            def insert(self, pos, where, values=None):
                self.items.append(values)
                return len(self.items) - 1
            
            def get_children(self):
                return range(len(self.items))
            
            def item(self, iid):
                return {"values": self.items[iid]}
            
            def delete(self, iid):
                if 0 <= iid < len(self.items):
                    del self.items[iid]
            
            def selection(self):
                return []
        
        self.tree = SimpleTree()
        self.entries_listbox.bind("<<ListboxSelect>>", lambda e: self._update_totals())

    def _build_summary_section(self):
        lab = tk.LabelFrame(self, text="Totals / Summary",
                           bg="white", fg="#333333",
                           font=("Helvetica", 11, "bold"),
                           relief="solid", bd=1)
        lab.pack(fill="x", padx=10, pady=8)
        container = tk.Frame(lab, bg="white")
        container.pack(fill="x", padx=10, pady=10)

        tk.Label(container, text="Totals by Area:", bg="white", fg="#333333",
                font=("Helvetica", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.totals_text = tk.Text(container, height=6, width=80, state="disabled",
                                   bg="#f9f9f9", font=("Helvetica", 9))
        self.totals_text.grid(row=1, column=0, padx=4, pady=4)

    def _build_actions(self):
        fr = tk.Frame(self, bg="#f0f0f0")
        fr.pack(fill="x", padx=10, pady=10)
        
        save_btn = tk.Button(fr, text="Save Day Log", command=self._save_csv,
                            bg="#3a3a3a", fg="white", font=("Helvetica", 11, "bold"),
                            activebackground="#1a1a1a", activeforeground="white",
                            relief="flat", cursor="hand2", padx=20, pady=8)
        save_btn.pack(side="left", padx=6)
        
        export_btn = tk.Button(fr, text="Export As...", command=self._export_as,
                              bg="#4a4a4a", fg="white", font=("Helvetica", 11, "bold"),
                              activebackground="#2a2a2a", activeforeground="white",
                              relief="flat", cursor="hand2", padx=20, pady=8)
        export_btn.pack(side="left", padx=6)
        
        totals_btn = tk.Button(fr, text="Compute Totals", command=self._update_totals,
                              bg="#5a5a5a", fg="white", font=("Helvetica", 11, "bold"),
                              activebackground="#3a3a3a", activeforeground="white",
                              relief="flat", cursor="hand2", padx=20, pady=8)
        totals_btn.pack(side="left", padx=6)
        
        quit_btn = tk.Button(fr, text="Quit", command=self.destroy,
                            bg="#2c2c2c", fg="white", font=("Helvetica", 11, "bold"),
                            activebackground="#0c0c0c", activeforeground="white",
                            relief="flat", cursor="hand2", padx=20, pady=8)
        quit_btn.pack(side="right", padx=6)

    def _add_employee(self):
        name = self.entry_vars["name"].get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Employee name required.")
            return
        values = []
        for key in ["name", "area", "cash", "credit_total", "cc_received", "voids", "beer", "liquor", "wine", "food"]:
            v = self.entry_vars[key].get()
            if key != "name" and key != "area":
                v = self._safe_number(v)
            values.append(v)
        self.tree.insert("", "end", values=values)
        # clear numeric fields but keep name perhaps
        for k in ["cash", "credit_total", "cc_received", "voids", "beer", "liquor", "wine", "food"]:
            self.entry_vars[k].set("0.00")
        self._update_totals()

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        for s in sel:
            self.tree.delete(s)
        self._update_totals()

    def _clear_all(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        self._update_totals()

    def _safe_number(self, txt):
        try:
            # allow commas and currency symbols
            clean = str(txt).replace(",", "").replace("$", "").strip()
            val = float(clean) if clean != "" else 0.0
        except Exception:
            val = 0.0
        return round(val, 2)

    def _gather_rows(self):
        rows = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid)["values"]
            # ensure numeric columns are floats
            row = {
                "name": vals[0],
                "area": vals[1],
                "cash": float(vals[2]) if vals[2] != "" else 0.0,
                "credit_total": float(vals[3]) if vals[3] != "" else 0.0,
                "cc_received": float(vals[4]) if vals[4] != "" else 0.0,
                "voids": float(vals[5]) if vals[5] != "" else 0.0,
                "beer": float(vals[6]) if vals[6] != "" else 0.0,
                "liquor": float(vals[7]) if vals[7] != "" else 0.0,
                "wine": float(vals[8]) if vals[8] != "" else 0.0,
                "food": float(vals[9]) if vals[9] != "" else 0.0,
            }
            rows.append(row)
        return rows

    def _update_totals(self):
        rows = self._gather_rows()
        totals = {}
        overall = {
            "cash": 0.0, "credit_total": 0.0, "cc_received": 0.0,
            "voids": 0.0, "beer": 0.0, "liquor": 0.0, "wine": 0.0, "food": 0.0
        }
        for r in rows:
            area = r["area"]
            a = totals.setdefault(area, {k: 0.0 for k in overall.keys()})
            for k in overall.keys():
                a[k] += r[k]
                overall[k] += r[k]

        # display in totals_text
        out_lines = []
        for area, sums in totals.items():
            out_lines.append(f"{area}:")
            out_lines.append("  " + ", ".join([f"{k}: ${sums[k]:,.2f}" for k in sums]))
        out_lines.append("Overall Totals:")
        out_lines.append("  " + ", ".join([f"{k}: ${overall[k]:,.2f}" for k in overall]))
        self.totals_text.config(state="normal")
        self.totals_text.delete("1.0", "end")
        self.totals_text.insert("1.0", "\n".join(out_lines))
        self.totals_text.config(state="disabled")

    def _save_csv(self):
        # save to default location with date and shift
        try:
            year = int(self.year_var.get())
            month = int(self.month_var.get())
            day = int(self.day_var.get())
            selected_date = date(year, month, day)
            dstr = selected_date.isoformat()
        except ValueError as e:
            messagebox.showerror("Invalid Date", f"Invalid date selected: {e}")
            return
        except Exception:
            messagebox.showerror("Invalid Date", "Please select a valid date.")
            return
        fname = f"dailylog_{dstr}_{self.shift_var.get().lower()}.csv"
        path = os.path.join(OUT_DIR, fname)
        self._write_csv(path)
        messagebox.showinfo("Saved", f"Daily log saved to:\n{path}")

    def _export_as(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
            initialdir=OUT_DIR,
            title="Export daily log as..."
        )
        if not p:
            return
        self._write_csv(p)
        messagebox.showinfo("Exported", f"Exported to:\n{p}")

    def _write_csv(self, path):
        rows = self._gather_rows()
        # Format date from dropdowns
        date_str = f"{self.year_var.get()}-{self.month_var.get().zfill(2)}-{self.day_var.get().zfill(2)}"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            # header
            writer.writerow(["Date", date_str])
            writer.writerow(["Shift", self.shift_var.get().strip()])
            writer.writerow(["Notes", self.notes_var.get().strip()])
            writer.writerow([])
            writer.writerow(["Audits"])
            writer.writerow(["When", "Cash Drawer"])
            for when in ["Beginning", "Mid", "Closing"]:
                writer.writerow([when, self._safe_number(self.audit_vars[when].get())])
            writer.writerow([])
            writer.writerow(["Deposits"])
            writer.writerow(["Opening Deposit", self._safe_number(self.open_deposit_var.get())])
            writer.writerow(["Closing Deposit", self._safe_number(self.close_deposit_var.get())])
            writer.writerow([])
            writer.writerow(["Employee Entries"])
            writer.writerow(["Name", "Area", "Cash", "Credit Total", "CC Received", "Voids", "Beer", "Liquor", "Wine", "Food"])
            for r in rows:
                writer.writerow([
                    r["name"], r["area"],
                    f"{r['cash']:.2f}", f"{r['credit_total']:.2f}", f"{r['cc_received']:.2f}",
                    f"{r['voids']:.2f}", f"{r['beer']:.2f}", f"{r['liquor']:.2f}", f"{r['wine']:.2f}", f"{r['food']:.2f}"
                ])
            writer.writerow([])
            # summary
            writer.writerow(["Summary"])
            self._update_totals()
            # Recompute summary for file
            tot_rows = self._gather_rows()
            totals = {}
            overall = {k: 0.0 for k in ["cash", "credit_total", "cc_received", "voids", "beer", "liquor", "wine", "food"]}
            for r in tot_rows:
                area = r["area"]
                a = totals.setdefault(area, {k: 0.0 for k in overall.keys()})
                for k in overall.keys():
                    a[k] += r[k]
                    overall[k] += r[k]
            writer.writerow(["Totals by Area"])
            writer.writerow(["Area"] + list(overall.keys()))
            for area, sums in totals.items():
                writer.writerow([area] + [f"{sums[k]:.2f}" for k in overall.keys()])
            writer.writerow(["Overall"] + [f"{overall[k]:.2f}" for k in overall.keys()])

        # Optionally could also save a simple summary JSON or database later

def main():
    app = DailyLogApp()
    app.mainloop()


if __name__ == "__main__":
    main()
# ...existing code...