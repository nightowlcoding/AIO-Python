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
        self.title("Daily Log")
        self.geometry("360x800")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)
        
        # Create canvas with scrollbar for scrollable content
        canvas = tk.Canvas(self, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#f0f0f0")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.canvas = canvas
        self.main_frame = self.scrollable_frame
        
        self._build_header()
        self._build_audit_section()
        self._build_deposits_section()
        self._build_employee_section()
        self._build_summary_section()
        self._build_actions()
        
        self._update_totals()
        
        # Enable mousewheel scrolling
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)
    
    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        if event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
    
    def _build_header(self):
        """Build compact mobile header"""
        header_frame = tk.Frame(self.main_frame, bg="#2c2c2c", height=100)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="Daily Log",
            font=("Arial", 18, "bold"),
            bg="#2c2c2c",
            fg="white"
        )
        title_label.pack(pady=(5, 5))
        
        # Date selectors
        date_frame = tk.Frame(header_frame, bg="#2c2c2c")
        date_frame.pack(pady=2)
        
        tk.Label(date_frame, text="Date:", bg="#2c2c2c", fg="white", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.month_var = tk.StringVar(value=str(datetime.now().month).zfill(2))
        month_menu = tk.OptionMenu(date_frame, self.month_var, *[f"{i:02d}" for i in range(1, 13)])
        month_menu.config(width=2, font=("Arial", 8), bg="#3a3a3a", fg="white", activebackground="#1a1a1a")
        month_menu.pack(side="left", padx=1)
        
        tk.Label(date_frame, text="/", bg="#2c2c2c", fg="white", font=("Arial", 9)).pack(side="left")
        
        self.day_var = tk.StringVar(value=str(datetime.now().day).zfill(2))
        day_menu = tk.OptionMenu(date_frame, self.day_var, *[f"{i:02d}" for i in range(1, 32)])
        day_menu.config(width=2, font=("Arial", 8), bg="#3a3a3a", fg="white", activebackground="#1a1a1a")
        day_menu.pack(side="left", padx=1)
        
        tk.Label(date_frame, text="/", bg="#2c2c2c", fg="white", font=("Arial", 9)).pack(side="left")
        
        current_year = datetime.now().year
        self.year_var = tk.StringVar(value=str(current_year))
        year_menu = tk.OptionMenu(date_frame, self.year_var, *[str(year) for year in range(current_year-5, current_year+2)])
        year_menu.config(width=4, font=("Arial", 8), bg="#3a3a3a", fg="white", activebackground="#1a1a1a")
        year_menu.pack(side="left", padx=1)
        
        # Shift and notes
        controls_frame = tk.Frame(header_frame, bg="#2c2c2c")
        controls_frame.pack(pady=2)
        
        tk.Label(controls_frame, text="Shift:", bg="#2c2c2c", fg="white", font=("Arial", 9)).pack(side="left", padx=2)
        self.shift_var = tk.StringVar(value="Day")
        shift_menu = tk.OptionMenu(controls_frame, self.shift_var, "Day", "Night")
        shift_menu.config(width=5, font=("Arial", 8), bg="#3a3a3a", fg="white", activebackground="#1a1a1a")
        shift_menu.pack(side="left", padx=2)
        
        tk.Label(controls_frame, text="Notes:", bg="#2c2c2c", fg="white", font=("Arial", 9)).pack(side="left", padx=2)
        self.notes_var = tk.StringVar()
        notes_entry = tk.Entry(controls_frame, textvariable=self.notes_var, width=18, font=("Arial", 8))
        notes_entry.pack(side="left", padx=2)
    
    def _build_audit_section(self):
        """Build compact cash audit section"""
        audit_frame = ttk.LabelFrame(self.main_frame, text="Cash Audit", padding="5")
        audit_frame.pack(fill="x", padx=5, pady=3)
        
        self.audit_vars = {}
        audit_labels = ["Beginning:", "Mid Shift:", "Closing:"]
        
        for i, label in enumerate(audit_labels):
            row_frame = tk.Frame(audit_frame, bg="white")
            row_frame.pack(fill="x", pady=1)
            
            tk.Label(row_frame, text=label, font=("Arial", 9), bg="white", width=12, anchor="w").pack(side="left", padx=2)
            self.audit_vars[label] = tk.StringVar()
            entry = tk.Entry(row_frame, textvariable=self.audit_vars[label], width=12, font=("Arial", 9))
            entry.pack(side="left", padx=2)
    
    def _build_deposits_section(self):
        """Build compact deposits section"""
        deposits_frame = ttk.LabelFrame(self.main_frame, text="Deposits", padding="5")
        deposits_frame.pack(fill="x", padx=5, pady=3)
        
        self.deposits_vars = {}
        deposit_labels = ["Opening:", "Closing:"]
        
        for i, label in enumerate(deposit_labels):
            row_frame = tk.Frame(deposits_frame, bg="white")
            row_frame.pack(fill="x", pady=1)
            
            tk.Label(row_frame, text=label, font=("Arial", 9), bg="white", width=12, anchor="w").pack(side="left", padx=2)
            self.deposits_vars[label] = tk.StringVar()
            entry = tk.Entry(row_frame, textvariable=self.deposits_vars[label], width=12, font=("Arial", 9))
            entry.pack(side="left", padx=2)
    
    def _build_employee_section(self):
        """Build mobile-optimized employee section with tabbed interface"""
        emp_frame = ttk.LabelFrame(self.main_frame, text="Employees", padding="5")
        emp_frame.pack(fill="x", padx=5, pady=3)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(emp_frame)
        notebook.pack(fill="x", pady=2)
        
        # Tab 1: Basic Info
        basic_tab = tk.Frame(notebook, bg="white")
        notebook.add(basic_tab, text="Basic")
        
        tk.Label(basic_tab, text="Name:", font=("Arial", 9), bg="white").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.name_var = tk.StringVar()
        tk.Entry(basic_tab, textvariable=self.name_var, width=25, font=("Arial", 9)).grid(row=0, column=1, padx=2, pady=2)
        
        tk.Label(basic_tab, text="Area:", font=("Arial", 9), bg="white").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.area_var = tk.StringVar(value="Dining")
        ttk.Combobox(basic_tab, textvariable=self.area_var, values=["Dining", "Bar", "To Out"], 
                    width=23, state="readonly", font=("Arial", 9)).grid(row=1, column=1, padx=2, pady=2)
        
        tk.Label(basic_tab, text="Cash:", font=("Arial", 9), bg="white").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.cash_var = tk.StringVar(value="0.00")
        tk.Entry(basic_tab, textvariable=self.cash_var, width=25, font=("Arial", 9)).grid(row=2, column=1, padx=2, pady=2)
        
        # Tab 2: Credit/CC
        credit_tab = tk.Frame(notebook, bg="white")
        notebook.add(credit_tab, text="Credit")
        
        tk.Label(credit_tab, text="Credit Total:", font=("Arial", 9), bg="white").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.credit_var = tk.StringVar(value="0.00")
        tk.Entry(credit_tab, textvariable=self.credit_var, width=25, font=("Arial", 9)).grid(row=0, column=1, padx=2, pady=2)
        
        tk.Label(credit_tab, text="CC Received:", font=("Arial", 9), bg="white").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.cc_var = tk.StringVar(value="0.00")
        tk.Entry(credit_tab, textvariable=self.cc_var, width=25, font=("Arial", 9)).grid(row=1, column=1, padx=2, pady=2)
        
        tk.Label(credit_tab, text="Voids:", font=("Arial", 9), bg="white").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.voids_var = tk.StringVar(value="0.00")
        tk.Entry(credit_tab, textvariable=self.voids_var, width=25, font=("Arial", 9)).grid(row=2, column=1, padx=2, pady=2)
        
        # Tab 3: Sales
        sales_tab = tk.Frame(notebook, bg="white")
        notebook.add(sales_tab, text="Sales")
        
        tk.Label(sales_tab, text="Beer:", font=("Arial", 9), bg="white").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.beer_var = tk.StringVar(value="0.00")
        tk.Entry(sales_tab, textvariable=self.beer_var, width=25, font=("Arial", 9)).grid(row=0, column=1, padx=2, pady=2)
        
        tk.Label(sales_tab, text="Liquor:", font=("Arial", 9), bg="white").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.liquor_var = tk.StringVar(value="0.00")
        tk.Entry(sales_tab, textvariable=self.liquor_var, width=25, font=("Arial", 9)).grid(row=1, column=1, padx=2, pady=2)
        
        tk.Label(sales_tab, text="Wine:", font=("Arial", 9), bg="white").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.wine_var = tk.StringVar(value="0.00")
        tk.Entry(sales_tab, textvariable=self.wine_var, width=25, font=("Arial", 9)).grid(row=2, column=1, padx=2, pady=2)
        
        tk.Label(sales_tab, text="Food:", font=("Arial", 9), bg="white").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.food_var = tk.StringVar(value="0.00")
        tk.Entry(sales_tab, textvariable=self.food_var, width=25, font=("Arial", 9)).grid(row=3, column=1, padx=2, pady=2)
        
        # Buttons
        btn_frame = tk.Frame(emp_frame, bg="white")
        btn_frame.pack(fill="x", pady=5)
        
        add_btn = tk.Button(btn_frame, text="Add", command=self._add_employee,
                          bg="#3a3a3a", fg="white", font=("Arial", 9, "bold"),
                          relief="flat", padx=10, pady=3, cursor="hand2",
                          activebackground="#1a1a1a", activeforeground="white", width=8)
        add_btn.pack(side="left", padx=2)
        
        remove_btn = tk.Button(btn_frame, text="Remove", command=self._remove_selected,
                             bg="#4a4a4a", fg="white", font=("Arial", 9),
                             relief="flat", padx=10, pady=3, cursor="hand2",
                             activebackground="#2a2a2a", activeforeground="white", width=8)
        remove_btn.pack(side="left", padx=2)
        
        clear_btn = tk.Button(btn_frame, text="Clear", command=self._clear_all,
                            bg="#4a4a4a", fg="white", font=("Arial", 9),
                            relief="flat", padx=10, pady=3, cursor="hand2",
                            activebackground="#2a2a2a", activeforeground="white", width=8)
        clear_btn.pack(side="left", padx=2)
        
        # Employee list (compact display)
        list_frame = tk.Frame(emp_frame, bg="white")
        list_frame.pack(fill="x", pady=5)
        
        tk.Label(list_frame, text="Entries:", font=("Arial", 9, "bold"), bg="white").pack(anchor="w", padx=2)
        
        # Store employee data
        self.employees = []
        
        # Listbox for compact view
        self.employee_listbox = tk.Listbox(list_frame, height=6, font=("Courier", 8), bg="white")
        self.employee_listbox.pack(fill="x", padx=2, pady=2)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.employee_listbox.yview)
        self.employee_listbox.configure(yscrollcommand=scrollbar.set)
    
    def _build_summary_section(self):
        """Build compact summary section"""
        summary_frame = ttk.LabelFrame(self.main_frame, text="Totals", padding="5")
        summary_frame.pack(fill="x", padx=5, pady=3)
        
        self.totals_text = tk.Text(summary_frame, height=8, width=40, font=("Courier", 7), 
                                   bg="white", relief="flat", state="disabled", wrap="none")
        self.totals_text.pack(fill="x")
        
        # Add horizontal scrollbar for totals
        h_scroll = ttk.Scrollbar(summary_frame, orient="horizontal", command=self.totals_text.xview)
        self.totals_text.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(fill="x")
    
    def _build_actions(self):
        """Build compact action buttons"""
        action_frame = tk.Frame(self.main_frame, bg="#f0f0f0")
        action_frame.pack(fill="x", padx=5, pady=10)
        
        save_btn = tk.Button(action_frame, text="Save Log", command=self._save_log,
                           bg="#3a3a3a", fg="white", font=("Arial", 10, "bold"),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#1a1a1a", activeforeground="white")
        save_btn.pack(fill="x", pady=2)
        
        export_btn = tk.Button(action_frame, text="Export CSV", command=self._export_csv,
                             bg="#4a4a4a", fg="white", font=("Arial", 10),
                             relief="flat", padx=15, pady=8, cursor="hand2",
                             activebackground="#2a2a2a", activeforeground="white")
        export_btn.pack(fill="x", pady=2)
        
        clear_day_btn = tk.Button(action_frame, text="Clear Day", command=self._clear_day,
                                bg="#4a4a4a", fg="white", font=("Arial", 10),
                                relief="flat", padx=15, pady=8, cursor="hand2",
                                activebackground="#2a2a2a", activeforeground="white")
        clear_day_btn.pack(fill="x", pady=2)
    
    def _add_employee(self):
        """Add employee entry"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Input Error", "Please enter employee name")
            return
        
        employee_data = {
            "name": name,
            "area": self.area_var.get(),
            "cash": self.cash_var.get(),
            "credit": self.credit_var.get(),
            "cc": self.cc_var.get(),
            "voids": self.voids_var.get(),
            "beer": self.beer_var.get(),
            "liquor": self.liquor_var.get(),
            "wine": self.wine_var.get(),
            "food": self.food_var.get()
        }
        
        self.employees.append(employee_data)
        
        # Display in listbox (compact format)
        display_text = f"{name[:15]:15} {employee_data['area'][:6]:6} ${float(employee_data['cash']):6.2f}"
        self.employee_listbox.insert("end", display_text)
        
        # Clear fields
        self.name_var.set("")
        self.cash_var.set("0.00")
        self.credit_var.set("0.00")
        self.cc_var.set("0.00")
        self.voids_var.set("0.00")
        self.beer_var.set("0.00")
        self.liquor_var.set("0.00")
        self.wine_var.set("0.00")
        self.food_var.set("0.00")
        
        self._update_totals()
    
    def _remove_selected(self):
        """Remove selected entry"""
        selection = self.employee_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select an entry to remove")
            return
        
        index = selection[0]
        self.employee_listbox.delete(index)
        del self.employees[index]
        
        self._update_totals()
    
    def _clear_all(self):
        """Clear all entries"""
        if messagebox.askyesno("Confirm", "Clear all employee entries?"):
            self.employee_listbox.delete(0, "end")
            self.employees = []
            self._update_totals()
    
    def _update_totals(self):
        """Update running totals display"""
        areas = {}
        
        for emp in self.employees:
            area = emp["area"]
            
            if area not in areas:
                areas[area] = {
                    "cash": 0.0, "credit": 0.0, "cc": 0.0, "voids": 0.0,
                    "beer": 0.0, "liquor": 0.0, "wine": 0.0, "food": 0.0
                }
            
            try:
                areas[area]["cash"] += float(emp["cash"])
                areas[area]["credit"] += float(emp["credit"])
                areas[area]["cc"] += float(emp["cc"])
                areas[area]["voids"] += float(emp["voids"])
                areas[area]["beer"] += float(emp["beer"])
                areas[area]["liquor"] += float(emp["liquor"])
                areas[area]["wine"] += float(emp["wine"])
                areas[area]["food"] += float(emp["food"])
            except ValueError:
                pass
        
        # Display totals
        self.totals_text.config(state="normal")
        self.totals_text.delete("1.0", "end")
        
        if not areas:
            self.totals_text.insert("end", "No entries yet")
        else:
            for area, totals in areas.items():
                self.totals_text.insert("end", f"{area}:\n")
                self.totals_text.insert("end", f"  Cash:   ${totals['cash']:8.2f}\n")
                self.totals_text.insert("end", f"  Credit: ${totals['credit']:8.2f}\n")
                self.totals_text.insert("end", f"  CC:     ${totals['cc']:8.2f}\n")
                self.totals_text.insert("end", f"  Voids:  ${totals['voids']:8.2f}\n")
                self.totals_text.insert("end", f"  Beer:   ${totals['beer']:8.2f}\n")
                self.totals_text.insert("end", f"  Liquor: ${totals['liquor']:8.2f}\n")
                self.totals_text.insert("end", f"  Wine:   ${totals['wine']:8.2f}\n")
                self.totals_text.insert("end", f"  Food:   ${totals['food']:8.2f}\n")
                self.totals_text.insert("end", "\n")
        
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
            
            for emp in self.employees:
                writer.writerow([
                    emp["name"], emp["area"], emp["cash"], emp["credit"],
                    emp["cc"], emp["voids"], emp["beer"], emp["liquor"],
                    emp["wine"], emp["food"]
                ])
        
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
                
                for emp in self.employees:
                    writer.writerow([
                        emp["name"], emp["area"], emp["cash"], emp["credit"],
                        emp["cc"], emp["voids"], emp["beer"], emp["liquor"],
                        emp["wine"], emp["food"]
                    ])
            
            messagebox.showinfo("Success", f"Data exported to:\n{filename}")
    
    def _clear_day(self):
        """Clear all day data"""
        if messagebox.askyesno("Confirm", "Clear all data for this day?"):
            for var in self.audit_vars.values():
                var.set("")
            for var in self.deposits_vars.values():
                var.set("")
            self.employee_listbox.delete(0, "end")
            self.employees = []
            self.notes_var.set("")
            self._update_totals()


if __name__ == "__main__":
    app = DailyLogApp()
    app.mainloop()
