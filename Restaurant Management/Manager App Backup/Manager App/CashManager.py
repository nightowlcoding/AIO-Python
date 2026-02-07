"""
Consolidated Cash Manager - Combines Cash Drawer and Cash Deductions
"""
import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import sys
from utils import validate_number, format_currency
from auto_save import AutoSaveManager, get_backup_manager
from app_config import create_button, create_header, COLORS, FONTS

OUT_DIR = os.path.expanduser("~/Documents/AIO Python/daily_logs")
os.makedirs(OUT_DIR, exist_ok=True)

# Initialize backup manager
backup_manager = get_backup_manager(OUT_DIR)


class CashManagerApp(tk.Tk):
    def __init__(self, initial_date=None):
        super().__init__()
        self.title("Cash Manager")
        self.geometry("380x820")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)
        
        # Parse initial date if provided
        if initial_date:
            try:
                parts = initial_date.split('-')
                if len(parts) == 3:
                    self.initial_year = int(parts[0])
                    self.initial_month = int(parts[1])
                    self.initial_day = int(parts[2])
                else:
                    self.initial_year = datetime.now().year
                    self.initial_month = datetime.now().month
                    self.initial_day = datetime.now().day
            except:
                self.initial_year = datetime.now().year
                self.initial_month = datetime.now().month
                self.initial_day = datetime.now().day
        else:
            self.initial_year = datetime.now().year
            self.initial_month = datetime.now().month
            self.initial_day = datetime.now().day
        
        # Initialize auto-save
        self.auto_save = AutoSaveManager(
            self, 
            self._auto_save_data,
            interval_seconds=300
        )
        self.auto_save_label = None
        
        # Create main container with tabs
        self._build_ui()
        
        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Start auto-save
        self.auto_save.start()
    
    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts"""
        self.bind('<Control-s>', lambda e: self._save_current_tab())
        self.bind('<Control-n>', lambda e: self._clear_current_tab())
        self.bind('<Escape>', lambda e: self.destroy())
    
    def _build_ui(self):
        """Build the main UI with tabbed interface"""
        # Header
        header_frame = tk.Frame(self, bg=COLORS['primary'], height=80)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="💰 Cash Manager",
            font=FONTS['header'],
            bg=COLORS['primary'],
            fg="white"
        )
        title_label.pack(pady=(10, 5))
        
        # Date selector
        date_frame = tk.Frame(header_frame, bg=COLORS['primary'])
        date_frame.pack(pady=2)
        
        tk.Label(date_frame, text="Date:", bg=COLORS['primary'], fg="white", 
                font=FONTS['label']).pack(side="left", padx=2)
        
        self.month_var = tk.IntVar(value=self.initial_month)
        month_spin = tk.Spinbox(
            date_frame, from_=1, to=12, textvariable=self.month_var,
            width=3, font=FONTS['entry'], wrap=True
        )
        month_spin.pack(side="left", padx=1)
        
        tk.Label(date_frame, text="/", bg=COLORS['primary'], fg="white").pack(side="left")
        
        self.day_var = tk.IntVar(value=self.initial_day)
        day_spin = tk.Spinbox(
            date_frame, from_=1, to=31, textvariable=self.day_var,
            width=3, font=FONTS['entry'], wrap=True
        )
        day_spin.pack(side="left", padx=1)
        
        tk.Label(date_frame, text="/", bg=COLORS['primary'], fg="white").pack(side="left")
        
        self.year_var = tk.IntVar(value=self.initial_year)
        year_spin = tk.Spinbox(
            date_frame, from_=self.initial_year-5, to=self.initial_year+2,
            textvariable=self.year_var, width=5, font=FONTS['entry'], wrap=True
        )
        year_spin.pack(side="left", padx=1)
        
        # Tabbed interface
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: Cash Drawer
        self.drawer_frame = tk.Frame(self.notebook, bg="#f0f0f0")
        self.notebook.add(self.drawer_frame, text="💵 Cash Drawer")
        self._build_drawer_tab()
        
        # Tab 2: Cash Deductions
        self.deductions_frame = tk.Frame(self.notebook, bg="#f0f0f0")
        self.notebook.add(self.deductions_frame, text="📝 Deductions")
        self._build_deductions_tab()
        
        # Status bar
        self._build_status_bar()
    
    def _build_drawer_tab(self):
        """Build Cash Drawer tab"""
        # Create scrollable content
        canvas = tk.Canvas(self.drawer_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.drawer_frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#f0f0f0")
        
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bill counts
        bills_frame = ttk.LabelFrame(scrollable, text="Bills", padding="10")
        bills_frame.pack(fill="x", padx=5, pady=5)
        
        self.drawer_vars = {}
        bills = [
            ("$100", 100), ("$50", 50), ("$20", 20), ("$10", 10),
            ("$5", 5), ("$2", 2), ("$1", 1)
        ]
        
        for i, (label, value) in enumerate(bills):
            row_frame = tk.Frame(bills_frame, bg="white")
            row_frame.pack(fill="x", pady=2)
            
            tk.Label(row_frame, text=label, width=8, font=FONTS['label'],
                    bg="white", fg="black", anchor="w").pack(side="left", padx=5)
            
            var = tk.StringVar(value="0")
            self.drawer_vars[f"bill_{value}"] = var
            entry = tk.Entry(row_frame, textvariable=var, width=10, font=FONTS['entry'])
            entry.pack(side="left", padx=5)
            entry.bind("<KeyRelease>", lambda e: (self._update_drawer_total(), self.auto_save.mark_dirty()))
            
            total_var = tk.StringVar(value="$0.00")
            self.drawer_vars[f"bill_{value}_total"] = total_var
            tk.Label(row_frame, textvariable=total_var, width=12, font=FONTS['label'],
                    bg="white", fg="black", anchor="e").pack(side="right", padx=5)
        
        # Coins
        coins_frame = ttk.LabelFrame(scrollable, text="Coins", padding="10")
        coins_frame.pack(fill="x", padx=5, pady=5)
        
        coins = [
            ("Quarters", 0.25), ("Dimes", 0.10), ("Nickels", 0.05), ("Pennies", 0.01)
        ]
        
        for label, value in coins:
            row_frame = tk.Frame(coins_frame, bg="white")
            row_frame.pack(fill="x", pady=2)
            
            tk.Label(row_frame, text=label, width=8, font=FONTS['label'],
                    bg="white", fg="black", anchor="w").pack(side="left", padx=5)
            
            var = tk.StringVar(value="0")
            self.drawer_vars[f"coin_{label.lower()}"] = var
            entry = tk.Entry(row_frame, textvariable=var, width=10, font=FONTS['entry'])
            entry.pack(side="left", padx=5)
            entry.bind("<KeyRelease>", lambda e: (self._update_drawer_total(), self.auto_save.mark_dirty()))
            
            total_var = tk.StringVar(value="$0.00")
            self.drawer_vars[f"coin_{label.lower()}_total"] = total_var
            tk.Label(row_frame, textvariable=total_var, width=12, font=FONTS['label'],
                    bg="white", fg="black", anchor="e").pack(side="right", padx=5)
        
        # Total
        total_frame = tk.Frame(scrollable, bg=COLORS['primary'], relief="solid", bd=2)
        total_frame.pack(fill="x", padx=5, pady=10)
        
        tk.Label(total_frame, text="TOTAL CASH:", font=(FONTS['button'][0], 12, 'bold'),
                bg=COLORS['primary'], fg="white").pack(side="left", padx=10, pady=10)
        
        self.drawer_total_var = tk.StringVar(value="$0.00")
        tk.Label(total_frame, textvariable=self.drawer_total_var, 
                font=(FONTS['button'][0], 12, 'bold'),
                bg=COLORS['primary'], fg="white").pack(side="right", padx=10, pady=10)
        
        # Buttons
        btn_frame = tk.Frame(scrollable, bg="#f0f0f0")
        btn_frame.pack(fill="x", padx=5, pady=5)
        
        create_button(btn_frame, "💾 Save Drawer", self._save_drawer, style="primary").pack(fill="x", pady=2)
        create_button(btn_frame, "📂 Load Drawer", self._load_drawer, style="secondary").pack(fill="x", pady=2)
        create_button(btn_frame, "🗑️ Clear Drawer", self._clear_drawer, style="neutral").pack(fill="x", pady=2)
    
    def _build_deductions_tab(self):
        """Build Cash Deductions tab"""
        # Create scrollable content
        canvas = tk.Canvas(self.deductions_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.deductions_frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#f0f0f0")
        
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Deduction entry
        entry_frame = ttk.LabelFrame(scrollable, text="Add Deduction", padding="10")
        entry_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(entry_frame, text="Item:", font=FONTS['label'], bg="white", fg="black").grid(
            row=0, column=0, sticky="w", padx=5, pady=5)
        self.deduction_item_var = tk.StringVar()
        tk.Entry(entry_frame, textvariable=self.deduction_item_var, width=20, 
                font=FONTS['entry']).grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(entry_frame, text="Amount:", font=FONTS['label'], bg="white", fg="black").grid(
            row=1, column=0, sticky="w", padx=5, pady=5)
        self.deduction_amount_var = tk.StringVar(value="0.00")
        tk.Entry(entry_frame, textvariable=self.deduction_amount_var, width=20, 
                font=FONTS['entry']).grid(row=1, column=1, padx=5, pady=5)
        
        create_button(entry_frame, "➕ Add", self._add_deduction, style="secondary").grid(
            row=2, column=0, columnspan=2, pady=5, sticky="ew", padx=5)
        
        # Deductions list
        list_frame = ttk.LabelFrame(scrollable, text="Deductions List", padding="10")
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.deductions = []
        self.deductions_listbox = tk.Listbox(list_frame, height=12, font=("Courier", 10))
        self.deductions_listbox.pack(fill="both", expand=True, pady=5)
        
        btn_remove = create_button(list_frame, "🗑️ Remove Selected", 
                                   self._remove_deduction, style="danger")
        btn_remove.pack(fill="x", pady=2)
        
        # Total
        total_frame = tk.Frame(scrollable, bg=COLORS['accent'], relief="solid", bd=2)
        total_frame.pack(fill="x", padx=5, pady=10)
        
        tk.Label(total_frame, text="TOTAL DEDUCTIONS:", font=(FONTS['button'][0], 12, 'bold'),
                bg=COLORS['accent'], fg="white").pack(side="left", padx=10, pady=10)
        
        self.deductions_total_var = tk.StringVar(value="$0.00")
        tk.Label(total_frame, textvariable=self.deductions_total_var,
                font=(FONTS['button'][0], 12, 'bold'),
                bg=COLORS['accent'], fg="white").pack(side="right", padx=10, pady=10)
        
        # Buttons
        btn_frame = tk.Frame(scrollable, bg="#f0f0f0")
        btn_frame.pack(fill="x", padx=5, pady=5)
        
        create_button(btn_frame, "💾 Save Deductions", self._save_deductions, 
                     style="primary").pack(fill="x", pady=2)
        create_button(btn_frame, "📂 Load Deductions", self._load_deductions, 
                     style="secondary").pack(fill="x", pady=2)
        create_button(btn_frame, "🗑️ Clear All", self._clear_deductions, 
                     style="neutral").pack(fill="x", pady=2)
    
    def _build_status_bar(self):
        """Build status bar"""
        status_frame = tk.Frame(self, bg="#f0f0f0", relief="sunken", bd=1)
        status_frame.pack(fill="x", side="bottom")
        
        self.auto_save_label = tk.Label(
            status_frame, text="Auto-save: Ready",
            font=("Arial", 8), fg="#666666", bg="#f0f0f0"
        )
        self.auto_save_label.pack(side="left", padx=5, pady=2)
        
        shortcuts_label = tk.Label(
            status_frame, text="Ctrl+S: Save | Ctrl+N: Clear | Esc: Exit",
            font=("Arial", 8), fg="#666666", bg="#f0f0f0"
        )
        shortcuts_label.pack(side="right", padx=5, pady=2)
    
    def _update_drawer_total(self):
        """Calculate and update drawer total"""
        total = 0.0
        
        # Bills
        bills = [(100, 100), (50, 50), (20, 20), (10, 10), (5, 5), (2, 2), (1, 1)]
        for value, multiplier in bills:
            count = validate_number(self.drawer_vars[f"bill_{value}"].get(), default=0.0)
            subtotal = count * multiplier
            total += subtotal
            self.drawer_vars[f"bill_{value}_total"].set(format_currency(subtotal))
        
        # Coins
        coins = [("quarters", 0.25), ("dimes", 0.10), ("nickels", 0.05), ("pennies", 0.01)]
        for name, value in coins:
            count = validate_number(self.drawer_vars[f"coin_{name}"].get(), default=0.0)
            subtotal = count * value
            total += subtotal
            self.drawer_vars[f"coin_{name}_total"].set(format_currency(subtotal))
        
        self.drawer_total_var.set(format_currency(total))
    
    def _update_deductions_total(self):
        """Calculate and update deductions total"""
        total = sum(validate_number(ded['amount'], default=0.0) for ded in self.deductions)
        self.deductions_total_var.set(format_currency(total))
    
    def _add_deduction(self):
        """Add a deduction"""
        item = self.deduction_item_var.get().strip()
        amount = self.deduction_amount_var.get().strip()
        
        if not item:
            messagebox.showwarning("Input Error", "Please enter an item name")
            return
        
        if not validate_number(amount):
            messagebox.showwarning("Input Error", "Please enter a valid amount")
            return
        
        self.deductions.append({"item": item, "amount": amount})
        self._update_deductions_display()
        
        # Clear inputs
        self.deduction_item_var.set("")
        self.deduction_amount_var.set("0.00")
        self.auto_save.mark_dirty()
    
    def _remove_deduction(self):
        """Remove selected deduction"""
        selection = self.deductions_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select a deduction to remove")
            return
        
        index = selection[0]
        del self.deductions[index]
        self._update_deductions_display()
        self.auto_save.mark_dirty()
    
    def _update_deductions_display(self):
        """Update deductions listbox"""
        self.deductions_listbox.delete(0, tk.END)
        for ded in self.deductions:
            amount = validate_number(ded['amount'], default=0.0)
            self.deductions_listbox.insert(tk.END, f"{ded['item']:<30} ${amount:>8.2f}")
        self._update_deductions_total()
    
    def _save_drawer(self):
        """Save cash drawer count"""
        date_str = f"{self.year_var.get()}-{self.month_var.get():02d}-{self.day_var.get():02d}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDrawer.csv")
        
        # Create backup if file exists
        if os.path.exists(filename):
            backup_manager.create_backup(f"{date_str}_CashDrawer.csv")
        
        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", date_str])
                writer.writerow([])
                writer.writerow(["Denomination", "Count", "Total"])
                
                # Bills
                for value in [100, 50, 20, 10, 5, 2, 1]:
                    count = self.drawer_vars[f"bill_{value}"].get()
                    total = self.drawer_vars[f"bill_{value}_total"].get()
                    writer.writerow([f"${value}", count, total])
                
                # Coins
                for name in ["quarters", "dimes", "nickels", "pennies"]:
                    count = self.drawer_vars[f"coin_{name}"].get()
                    total = self.drawer_vars[f"coin_{name}_total"].get()
                    writer.writerow([name.title(), count, total])
                
                writer.writerow([])
                writer.writerow(["Total Cash", "", self.drawer_total_var.get()])
            
            self.auto_save.mark_clean()
            messagebox.showinfo("Success", f"Cash drawer saved for {date_str}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def _load_drawer(self):
        """Load cash drawer count"""
        date_str = f"{self.year_var.get()}-{self.month_var.get():02d}-{self.day_var.get():02d}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDrawer.csv")
        
        if not os.path.exists(filename):
            messagebox.showwarning("Not Found", f"No drawer count found for {date_str}")
            return
        
        try:
            with open(filename, "r", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                for row in rows:
                    if not row or len(row) < 2:
                        continue
                    
                    # Match bills
                    if row[0] in ["$100", "$50", "$20", "$10", "$5", "$2", "$1"]:
                        value = int(row[0].replace("$", ""))
                        self.drawer_vars[f"bill_{value}"].set(row[1])
                    
                    # Match coins
                    elif row[0].lower() in ["quarters", "dimes", "nickels", "pennies"]:
                        self.drawer_vars[f"coin_{row[0].lower()}"].set(row[1])
            
            self._update_drawer_total()
            messagebox.showinfo("Success", f"Loaded drawer count for {date_str}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")
    
    def _clear_drawer(self):
        """Clear all drawer counts"""
        if messagebox.askyesno("Confirm", "Clear all drawer counts?"):
            for key in self.drawer_vars:
                if not key.endswith("_total"):
                    self.drawer_vars[key].set("0")
            self._update_drawer_total()
            self.auto_save.mark_dirty()
    
    def _save_deductions(self):
        """Save cash deductions"""
        date_str = f"{self.year_var.get()}-{self.month_var.get():02d}-{self.day_var.get():02d}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDeductions.csv")
        
        # Create backup if file exists
        if os.path.exists(filename):
            backup_manager.create_backup(f"{date_str}_CashDeductions.csv")
        
        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", date_str])
                writer.writerow([])
                writer.writerow(["Cash Deductions"])
                writer.writerow(["Items Purchased", "", "Amount"])
                
                for ded in self.deductions:
                    writer.writerow([ded['item'], "", ded['amount']])
                
                writer.writerow([])
                writer.writerow(["Total", "", self.deductions_total_var.get()])
            
            self.auto_save.mark_clean()
            messagebox.showinfo("Success", f"Deductions saved for {date_str}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def _load_deductions(self):
        """Load cash deductions"""
        date_str = f"{self.year_var.get()}-{self.month_var.get():02d}-{self.day_var.get():02d}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDeductions.csv")
        
        if not os.path.exists(filename):
            messagebox.showwarning("Not Found", f"No deductions found for {date_str}")
            return
        
        try:
            self.deductions = []
            with open(filename, "r", newline="") as f:
                reader = csv.reader(f)
                section = None
                
                for row in reader:
                    if not row:
                        continue
                    
                    if row[0] == "Cash Deductions":
                        section = "deductions"
                        continue
                    
                    if section == "deductions" and row[0] not in ["Items Purchased", "Total"]:
                        if len(row) >= 3 and row[2]:
                            self.deductions.append({"item": row[0], "amount": row[2]})
            
            self._update_deductions_display()
            messagebox.showinfo("Success", f"Loaded deductions for {date_str}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")
    
    def _clear_deductions(self):
        """Clear all deductions"""
        if messagebox.askyesno("Confirm", "Clear all deductions?"):
            self.deductions = []
            self._update_deductions_display()
            self.auto_save.mark_dirty()
    
    def _save_current_tab(self):
        """Save current tab's data"""
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            self._save_drawer()
        else:
            self._save_deductions()
    
    def _clear_current_tab(self):
        """Clear current tab's data"""
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            self._clear_drawer()
        else:
            self._clear_deductions()
    
    def _auto_save_data(self):
        """Auto-save callback"""
        try:
            self._save_current_tab()
            if self.auto_save_label:
                now = datetime.now().strftime("%H:%M:%S")
                self.auto_save_label.config(text=f"Auto-saved: {now}")
        except Exception as e:
            print(f"Auto-save failed: {e}")


if __name__ == "__main__":
    initial_date = sys.argv[1] if len(sys.argv) > 1 else None
    app = CashManagerApp(initial_date)
    app.mainloop()
