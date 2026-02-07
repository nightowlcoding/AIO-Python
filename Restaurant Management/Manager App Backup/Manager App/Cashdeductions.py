import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import sys

OUT_DIR = os.path.expanduser("~/Documents/AIO Python/daily_logs")
os.makedirs(OUT_DIR, exist_ok=True)

class CashDeductionsApp(tk.Tk):
    def __init__(self, initial_date=None):
        super().__init__()
        self.title("Cash Deductions")
        self.geometry("360x800")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)
        
        # Parse initial date if provided
        if initial_date:
            try:
                parts = initial_date.split('-')
                if len(parts) == 3:
                    self.initial_year = parts[0]
                    self.initial_month = parts[1]
                    self.initial_day = parts[2]
                else:
                    self.initial_year = str(datetime.now().year)
                    self.initial_month = str(datetime.now().month).zfill(2)
                    self.initial_day = str(datetime.now().day).zfill(2)
            except:
                self.initial_year = str(datetime.now().year)
                self.initial_month = str(datetime.now().month).zfill(2)
                self.initial_day = str(datetime.now().day).zfill(2)
        else:
            self.initial_year = str(datetime.now().year)
            self.initial_month = str(datetime.now().month).zfill(2)
            self.initial_day = str(datetime.now().day).zfill(2)
        
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
        self._build_entry_section()
        self._build_deductions_list()
        self._build_total_section()
        self._build_actions()
        
        # Auto-load deductions for the initial date if file exists
        if initial_date:
            self._auto_load_deductions()
        
        self._update_total()
        
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
    
    def _on_date_change(self, *args):
        """Called when date selection changes - auto-load data"""
        # Use after() to avoid multiple rapid calls
        if hasattr(self, '_date_change_job'):
            self.after_cancel(self._date_change_job)
        self._date_change_job = self.after(500, self._auto_load_deductions)
    
    def _build_header(self):
        """Build compact mobile header"""
        header_frame = tk.Frame(self.main_frame, bg="#2c2c2c", height=80)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="Cash Deductions",
            font=("Arial", 18, "bold"),
            bg="#2c2c2c",
            fg="black"
        )
        title_label.pack(pady=(10, 5))
        
        # Date selectors
        date_frame = tk.Frame(header_frame, bg="#2c2c2c")
        date_frame.pack(pady=2)
        
        tk.Label(date_frame, text="Date:", bg="#2c2c2c", fg="black", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.month_var = tk.StringVar(value=self.initial_month)
        self.month_var.trace_add("write", self._on_date_change)
        month_menu = tk.OptionMenu(date_frame, self.month_var, *[f"{i:02d}" for i in range(1, 13)])
        month_menu.config(width=2, font=("Arial", 8), bg="white", fg="black", activebackground="#e0e0e0", activeforeground="black")
        month_menu["menu"].config(bg="white", fg="black")
        month_menu.pack(side="left", padx=1)
        
        tk.Label(date_frame, text="/", bg="#2c2c2c", fg="black", font=("Arial", 9)).pack(side="left")
        
        self.day_var = tk.StringVar(value=self.initial_day)
        self.day_var.trace_add("write", self._on_date_change)
        day_menu = tk.OptionMenu(date_frame, self.day_var, *[f"{i:02d}" for i in range(1, 32)])
        day_menu.config(width=2, font=("Arial", 8), bg="white", fg="black", activebackground="#e0e0e0", activeforeground="black")
        day_menu["menu"].config(bg="white", fg="black")
        day_menu.pack(side="left", padx=1)
        
        tk.Label(date_frame, text="/", bg="#2c2c2c", fg="black", font=("Arial", 9)).pack(side="left")
        
        current_year = datetime.now().year
        self.year_var = tk.StringVar(value=self.initial_year)
        self.year_var.trace_add("write", self._on_date_change)
        year_menu = tk.OptionMenu(date_frame, self.year_var, *[str(year) for year in range(current_year-5, current_year+2)])
        year_menu.config(width=4, font=("Arial", 8), bg="white", fg="black", activebackground="#e0e0e0", activeforeground="black")
        year_menu["menu"].config(bg="white", fg="black")
        year_menu.pack(side="left", padx=1)
    
    def _build_entry_section(self):
        """Build entry section for cash deductions"""
        entry_frame = ttk.LabelFrame(self.main_frame, text="Add Cash Deduction", padding="10")
        entry_frame.pack(fill="x", padx=5, pady=5)
        
        # Items Purchased
        tk.Label(entry_frame, text="Items Purchased:", font=("Arial", 9, "bold"), bg="white", fg="black").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.items_var = tk.StringVar()
        tk.Entry(entry_frame, textvariable=self.items_var, width=30, font=("Arial", 9), fg="black", bg="white").grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Purchase Location
        tk.Label(entry_frame, text="Purchase Location:", font=("Arial", 9, "bold"), bg="white", fg="black").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.location_var = tk.StringVar()
        tk.Entry(entry_frame, textvariable=self.location_var, width=30, font=("Arial", 9), fg="black", bg="white").grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # Amount
        tk.Label(entry_frame, text="$ Amount:", font=("Arial", 9, "bold"), bg="white", fg="black").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.amount_var = tk.StringVar(value="0.00")
        tk.Entry(entry_frame, textvariable=self.amount_var, width=30, font=("Arial", 9), fg="black", bg="white").grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Configure column weights
        entry_frame.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = tk.Frame(entry_frame, bg="white")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        add_btn = tk.Button(btn_frame, text="Add Deduction", command=self._add_deduction,
                          bg="white", fg="black", font=("Arial", 9, "bold"),
                          relief="solid", bd=1, padx=10, pady=3, cursor="hand2",
                          activebackground="#e0e0e0", activeforeground="black", width=12)
        add_btn.pack(side="left", padx=5)
        
        clear_btn = tk.Button(btn_frame, text="Clear Fields", command=self._clear_fields,
                            bg="white", fg="black", font=("Arial", 9),
                            relief="solid", bd=1, padx=10, pady=3, cursor="hand2",
                            activebackground="#e0e0e0", activeforeground="black", width=12)
        clear_btn.pack(side="left", padx=5)
    
    def _build_deductions_list(self):
        """Build list of deductions"""
        list_frame = ttk.LabelFrame(self.main_frame, text="Cash Deductions List", padding="10")
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Store deductions data
        self.deductions = []
        
        # Listbox for deductions
        self.deductions_listbox = tk.Listbox(list_frame, height=10, font=("Courier", 8), bg="white", fg="black")
        self.deductions_listbox.pack(fill="both", expand=True, pady=5)
        self.deductions_listbox.bind("<Double-Button-1>", self._edit_deduction)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.deductions_listbox.yview)
        self.deductions_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # Remove button
        remove_btn = tk.Button(list_frame, text="Remove Selected", command=self._remove_selected,
                             bg="white", fg="black", font=("Arial", 9),
                             relief="solid", bd=1, padx=10, pady=3, cursor="hand2",
                             activebackground="#e0e0e0", activeforeground="black")
        remove_btn.pack(pady=5)
    
    def _build_total_section(self):
        """Build total section"""
        total_frame = ttk.LabelFrame(self.main_frame, text="Total", padding="10")
        total_frame.pack(fill="x", padx=5, pady=5)
        
        # Total display (highlighted)
        total_display_frame = tk.Frame(total_frame, bg="#2c2c2c", relief="solid", bd=2)
        total_display_frame.pack(fill="x", pady=5)
        
        tk.Label(total_display_frame, text="TOTAL CASH DEDUCTIONS:", font=("Arial", 11, "bold"), bg="#2c2c2c", fg="black", anchor="w").pack(side="left", padx=10, pady=10)
        self.total_var = tk.StringVar(value="$0.00")
        tk.Label(total_display_frame, textvariable=self.total_var, font=("Arial", 11, "bold"), bg="#2c2c2c", fg="black", anchor="e").pack(side="right", padx=10, pady=10)
    
    def _build_actions(self):
        """Build action buttons"""
        action_frame = tk.Frame(self.main_frame, bg="#f0f0f0")
        action_frame.pack(fill="x", padx=5, pady=10)
        
        back_btn = tk.Button(action_frame, text="← Back to Daily Log", command=self._back_to_dailylog,
                           bg="#3a3a3a", fg="black", font=("Arial", 10, "bold"),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#1a1a1a", activeforeground="black")
        back_btn.pack(fill="x", pady=2)
        
        save_btn = tk.Button(action_frame, text="Save Deductions", command=self._save_deductions,
                           bg="#3a3a3a", fg="black", font=("Arial", 10, "bold"),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#1a1a1a", activeforeground="black")
        save_btn.pack(fill="x", pady=2)
        
        load_btn = tk.Button(action_frame, text="Load Deductions", command=self._load_deductions,
                           bg="#4a4a4a", fg="black", font=("Arial", 10),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#2a2a2a", activeforeground="black")
        load_btn.pack(fill="x", pady=2)
        
        clear_all_btn = tk.Button(action_frame, text="Clear All", command=self._clear_all,
                                bg="#4a4a4a", fg="black", font=("Arial", 10),
                                relief="flat", padx=15, pady=8, cursor="hand2",
                                activebackground="#2a2a2a", activeforeground="black")
        clear_all_btn.pack(fill="x", pady=2)
    
    def _add_deduction(self):
        """Add a deduction entry"""
        items = self.items_var.get().strip()
        location = self.location_var.get().strip()
        amount = self.amount_var.get().strip()
        
        if not items:
            messagebox.showwarning("Input Error", "Please enter items purchased")
            return
        
        if not location:
            messagebox.showwarning("Input Error", "Please enter purchase location")
            return
        
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                messagebox.showwarning("Input Error", "Amount must be greater than 0")
                return
        except ValueError:
            messagebox.showwarning("Input Error", "Please enter a valid amount")
            return
        
        deduction_data = {
            "items": items,
            "location": location,
            "amount": amount
        }
        
        self.deductions.append(deduction_data)
        self._update_display()
        self._update_total()
        self._clear_fields()
    
    def _clear_fields(self):
        """Clear input fields"""
        self.items_var.set("")
        self.location_var.set("")
        self.amount_var.set("0.00")
    
    def _update_display(self):
        """Update the listbox display"""
        self.deductions_listbox.delete(0, "end")
        for ded in self.deductions:
            # Format: Items (truncated) | Location (truncated) | $Amount
            items_short = ded["items"][:15] if len(ded["items"]) <= 15 else ded["items"][:12] + "..."
            location_short = ded["location"][:15] if len(ded["location"]) <= 15 else ded["location"][:12] + "..."
            display_text = f"{items_short:15} | {location_short:15} | ${float(ded['amount']):7.2f}"
            self.deductions_listbox.insert("end", display_text)
    
    def _edit_deduction(self, event):
        """Edit selected deduction by double-clicking"""
        selection = self.deductions_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        ded = self.deductions[index]
        
        # Load deduction data into form fields
        self.items_var.set(ded["items"])
        self.location_var.set(ded["location"])
        self.amount_var.set(ded["amount"])
        
        # Remove the old entry
        del self.deductions[index]
        self._update_display()
        self._update_total()
    
    def _remove_selected(self):
        """Remove selected deduction"""
        selection = self.deductions_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select a deduction to remove")
            return
        
        index = selection[0]
        del self.deductions[index]
        self._update_display()
        self._update_total()
    
    def _update_total(self):
        """Update total cash deductions"""
        total = 0.0
        for ded in self.deductions:
            try:
                total += float(ded["amount"])
            except ValueError:
                pass
        
        self.total_var.set(f"${total:.2f}")
    
    def _save_deductions(self):
        """Save cash deductions to file"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDeductions.csv")
        
        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", date_str])
                writer.writerow([])
                writer.writerow(["Cash Deductions"])
                writer.writerow(["Items Purchased", "Purchase Location", "Amount"])
                
                for ded in self.deductions:
                    writer.writerow([ded["items"], ded["location"], ded["amount"]])
                
                writer.writerow([])
                writer.writerow(["Total", "", self.total_var.get()])
            
            messagebox.showinfo("Success", f"Cash deductions saved to:\n{filename}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Error saving deductions:\n{str(e)}")
    
    def _load_deductions(self):
        """Load cash deductions from file"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDeductions.csv")
        
        if not os.path.exists(filename):
            messagebox.showwarning("Not Found", f"No saved deductions found for:\n{date_str}")
            return
        
        try:
            self.deductions = []
            
            with open(filename, "r", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                # Parse the CSV
                section = None
                for i, row in enumerate(rows):
                    if not row:
                        continue
                    
                    if row[0] == "Cash Deductions":
                        section = "deductions"
                        continue
                    elif section == "deductions" and row[0] != "Items Purchased" and row[0] != "Total":
                        if len(row) >= 3:
                            deduction_data = {
                                "items": row[0],
                                "location": row[1],
                                "amount": row[2]
                            }
                            self.deductions.append(deduction_data)
            
            self._update_display()
            self._update_total()
            
            messagebox.showinfo("Success", f"Loaded {len(self.deductions)} cash deductions from:\n{date_str}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Error loading deductions:\n{str(e)}")
    
    def _clear_all(self):
        """Clear all deductions"""
        if messagebox.askyesno("Confirm", "Clear all cash deductions?"):
            self.deductions = []
            self._update_display()
            self._update_total()
    
    def _back_to_dailylog(self):
        """Return to Daily Log application"""
        self.destroy()
    
    def _auto_load_deductions(self):
        """Automatically load deductions for the current date without showing message"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDeductions.csv")
        
        if not os.path.exists(filename):
            return
        
        try:
            self.deductions = []
            
            with open(filename, "r", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                # Parse the CSV
                section = None
                for i, row in enumerate(rows):
                    if not row:
                        continue
                    
                    if row[0] == "Cash Deductions":
                        section = "deductions"
                        continue
                    elif section == "deductions" and row[0] != "Items Purchased" and row[0] != "Total":
                        if len(row) >= 3:
                            deduction_data = {
                                "items": row[0],
                                "location": row[1],
                                "amount": row[2]
                            }
                            self.deductions.append(deduction_data)
            
            self._update_display()
            self._update_total()
        
        except Exception as e:
            print(f"Error auto-loading deductions: {e}")


if __name__ == "__main__":
    # Check if date argument was passed
    initial_date = sys.argv[1] if len(sys.argv) > 1 else None
    app = CashDeductionsApp(initial_date)
    app.mainloop()
