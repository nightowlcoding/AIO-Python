import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

OUT_DIR = os.path.expanduser("~/Documents/AIO Python/daily_logs")
os.makedirs(OUT_DIR, exist_ok=True)

class DailyLogApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Restaurant Daily Log")
        self.geometry("1100x750")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)
        
        main_frame = tk.Frame(self, bg="#f0f0f0")
        main_frame.pack(fill="both", expand=True)
        self.main_frame = main_frame
        
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
        """Build modern deposits section"""
        deposits_frame = ttk.LabelFrame(self.main_frame, text="Deposits", padding="10")
        deposits_frame.pack(fill="x", padx=10, pady=5)
        
        self.deposits_vars = {}
        deposit_labels = ["Opening Deposit:", "Closing Deposit:"]
        for i, label in enumerate(deposit_labels):
            tk.Label(deposits_frame, text=label, font=("Arial", 10)).grid(row=i, column=0, sticky="w", padx=5, pady=3)
            self.deposits_vars[label] = tk.StringVar()
            entry = tk.Entry(deposits_frame, textvariable=self.deposits_vars[label], width=15, font=("Arial", 10))
            entry.grid(row=i, column=1, padx=5, pady=3)
    
    def _build_employee_section(self):
        """Build modern employee entries section"""
        emp_frame = ttk.LabelFrame(self.main_frame, text="Employee Entries", padding="10")
        emp_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Entry form
        form_frame = tk.Frame(emp_frame, bg="white")
        form_frame.pack(fill="x", pady=(0, 5))
        
        labels = ["Name:", "Area:", "Cash:", "Credit Total:", "CC Received:", "Voids:", "Beer:", "Liquor:", "Wine:", "Food:"]
        self.entry_vars = {}
        
        for i, label in enumerate(labels):
            tk.Label(form_frame, text=label, font=("Arial", 9), bg="white").grid(row=0, column=i*2, sticky="e", padx=(5, 2), pady=3)
            var = tk.StringVar(value="0.00" if label != "Name:" and label != "Area:" else ("" if label == "Name:" else "Dining"))
            self.entry_vars[label] = var
            
            if label == "Area:":
                combo = ttk.Combobox(form_frame, textvariable=var, values=["Dining", "Bar", "To Out"], 
                                   width=8, state="readonly", font=("Arial", 9))
                combo.grid(row=0, column=i*2+1, padx=(0, 5), pady=3)
            else:
                width = 15 if label == "Name:" else 8
                entry = tk.Entry(form_frame, textvariable=var, width=width, font=("Arial", 9))
                entry.grid(row=0, column=i*2+1, padx=(0, 5), pady=3)
        
        # Buttons
        btn_frame = tk.Frame(emp_frame, bg="white")
        btn_frame.pack(fill="x", pady=5)
        
        add_btn = tk.Button(btn_frame, text="Add Employee", command=self._add_employee,
                          bg="#3a3a3a", fg="white", font=("Arial", 10, "bold"),
                          relief="flat", padx=15, pady=5, cursor="hand2",
                          activebackground="#1a1a1a", activeforeground="white")
        add_btn.pack(side="left", padx=5)
        
        remove_btn = tk.Button(btn_frame, text="Remove Selected", command=self._remove_selected,
                             bg="#4a4a4a", fg="white", font=("Arial", 10),
                             relief="flat", padx=15, pady=5, cursor="hand2",
                             activebackground="#2a2a2a", activeforeground="white")
        remove_btn.pack(side="left", padx=5)
        
        clear_btn = tk.Button(btn_frame, text="Clear All", command=self._clear_all,
                            bg="#4a4a4a", fg="white", font=("Arial", 10),
                            relief="flat", padx=15, pady=5, cursor="hand2",
                            activebackground="#2a2a2a", activeforeground="white")
        clear_btn.pack(side="left", padx=5)
        
        # Treeview
        tree_frame = tk.Frame(emp_frame, bg="white")
        tree_frame.pack(fill="both", expand=True)
        
        columns = ("name", "area", "cash", "credit", "cc", "voids", "beer", "liquor", "wine", "food")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        
        headings = ["Name", "Area", "Cash", "Credit Total", "CC Received", "Voids", "Beer", "Liquor", "Wine", "Food"]
        widths = [100, 80, 70, 90, 90, 60, 60, 60, 60, 60]
        
        for col, heading, width in zip(columns, headings, widths):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="center")
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def _build_summary_section(self):
        """Build modern summary section"""
        summary_frame = ttk.LabelFrame(self.main_frame, text="Running Totals", padding="10")
        summary_frame.pack(fill="x", padx=10, pady=5)
        
        self.totals_text = tk.Text(summary_frame, height=6, width=120, font=("Courier", 9), 
                                   bg="white", relief="flat", state="disabled")
        self.totals_text.pack(fill="x")
    
    def _build_actions(self):
        """Build modern action buttons"""
        action_frame = tk.Frame(self.main_frame, bg="#f0f0f0")
        action_frame.pack(fill="x", padx=10, pady=10)
        
        save_btn = tk.Button(action_frame, text="Save Daily Log", command=self._save_log,
                           bg="#3a3a3a", fg="white", font=("Arial", 12, "bold"),
                           relief="flat", padx=20, pady=10, cursor="hand2",
                           activebackground="#1a1a1a", activeforeground="white")
        save_btn.pack(side="left", padx=5)
        
        export_btn = tk.Button(action_frame, text="Export CSV", command=self._export_csv,
                             bg="#4a4a4a", fg="white", font=("Arial", 12),
                             relief="flat", padx=20, pady=10, cursor="hand2",
                             activebackground="#2a2a2a", activeforeground="white")
        export_btn.pack(side="left", padx=5)
        
        clear_day_btn = tk.Button(action_frame, text="Clear Day", command=self._clear_day,
                                bg="#4a4a4a", fg="white", font=("Arial", 12),
                                relief="flat", padx=20, pady=10, cursor="hand2",
                                activebackground="#2a2a2a", activeforeground="white")
        clear_day_btn.pack(side="left", padx=5)
    
    def _add_employee(self):
        """Add employee entry to treeview"""
        name = self.entry_vars["Name:"].get().strip()
        if not name:
            messagebox.showwarning("Input Error", "Please enter employee name")
            return
        
        values = []
        for label in ["Name:", "Area:", "Cash:", "Credit Total:", "CC Received:", 
                     "Voids:", "Beer:", "Liquor:", "Wine:", "Food:"]:
            val = self.entry_vars[label].get()
            values.append(val)
        
        self.tree.insert("", "end", values=values)
        
        # Clear numeric fields
        for label in ["Cash:", "Credit Total:", "CC Received:", "Voids:", 
                     "Beer:", "Liquor:", "Wine:", "Food:"]:
            self.entry_vars[label].set("0.00")
        self.entry_vars["Name:"].set("")
        
        self._update_totals()
    
    def _remove_selected(self):
        """Remove selected entry from treeview"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select an entry to remove")
            return
        
        for item in selection:
            self.tree.delete(item)
        
        self._update_totals()
    
    def _clear_all(self):
        """Clear all entries from treeview"""
        if messagebox.askyesno("Confirm", "Clear all employee entries?"):
            for item in self.tree.get_children():
                self.tree.delete(item)
            self._update_totals()
    
    def _update_totals(self):
        """Update running totals display"""
        areas = {}
        
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id)["values"]
            area = values[1]
            
            if area not in areas:
                areas[area] = {
                    "cash": 0.0,
                    "credit": 0.0,
                    "cc": 0.0,
                    "voids": 0.0,
                    "beer": 0.0,
                    "liquor": 0.0,
                    "wine": 0.0,
                    "food": 0.0
                }
            
            try:
                areas[area]["cash"] += float(values[2])
                areas[area]["credit"] += float(values[3])
                areas[area]["cc"] += float(values[4])
                areas[area]["voids"] += float(values[5])
                areas[area]["beer"] += float(values[6])
                areas[area]["liquor"] += float(values[7])
                areas[area]["wine"] += float(values[8])
                areas[area]["food"] += float(values[9])
            except ValueError:
                pass
        
        # Display totals
        self.totals_text.config(state="normal")
        self.totals_text.delete("1.0", "end")
        
        for area, totals in areas.items():
            line = f"{area:10} | Cash: ${totals['cash']:8.2f} | Credit: ${totals['credit']:8.2f} | CC: ${totals['cc']:8.2f} | "
            line += f"Voids: ${totals['voids']:7.2f} | Beer: ${totals['beer']:7.2f} | Liquor: ${totals['liquor']:7.2f} | "
            line += f"Wine: ${totals['wine']:7.2f} | Food: ${totals['food']:7.2f}\n"
            self.totals_text.insert("end", line)
        
        self.totals_text.config(state="disabled")
    
    def _save_log(self):
        """Save daily log to file"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        shift = self.shift_var.get()
        filename = os.path.join(OUT_DIR, f"{date_str}_{shift}.csv")
        
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", date_str])
            writer.writerow(["Shift", shift])
            writer.writerow(["Notes", self.notes_var.get()])
            writer.writerow([])
            
            writer.writerow(["Cash Audits"])
            for label, var in self.audit_vars.items():
                writer.writerow([label, var.get()])
            writer.writerow([])
            
            writer.writerow(["Deposits"])
            for label, var in self.deposits_vars.items():
                writer.writerow([label, var.get()])
            writer.writerow([])
            
            writer.writerow(["Employee Entries"])
            writer.writerow(["Name", "Area", "Cash", "Credit Total", "CC Received", 
                           "Voids", "Beer", "Liquor", "Wine", "Food"])
            
            for item_id in self.tree.get_children():
                values = self.tree.item(item_id)["values"]
                writer.writerow(values)
        
        messagebox.showinfo("Success", f"Log saved to:\n{filename}")
    
    def _export_csv(self):
        """Export current data to CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filename:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Name", "Area", "Cash", "Credit Total", "CC Received", 
                               "Voids", "Beer", "Liquor", "Wine", "Food"])
                
                for item_id in self.tree.get_children():
                    values = self.tree.item(item_id)["values"]
                    writer.writerow(values)
            
            messagebox.showinfo("Success", f"Data exported to:\n{filename}")
    
    def _clear_day(self):
        """Clear all day data"""
        if messagebox.askyesno("Confirm", "Clear all data for this day?"):
            for var in self.audit_vars.values():
                var.set("")
            for var in self.deposits_vars.values():
                var.set("")
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.notes_var.set("")
            self._update_totals()


if __name__ == "__main__":
    app = DailyLogApp()
    app.mainloop()
