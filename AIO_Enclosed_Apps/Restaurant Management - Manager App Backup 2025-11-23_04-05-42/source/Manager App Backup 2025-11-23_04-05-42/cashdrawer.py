import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import sys

OUT_DIR = os.path.expanduser("~/Documents/AIO Python/daily_logs")
os.makedirs(OUT_DIR, exist_ok=True)

class CashDrawerApp(tk.Tk):
    def __init__(self, initial_date=None):
        super().__init__()
        self.title("Cash Drawer Counter")
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
        
        # Currency denominations
        self.denominations = [
            ("Pennies", 0.01),
            ("Nickels", 0.05),
            ("Dimes", 0.10),
            ("Quarters", 0.25),
            ("$1", 1.00),
            ("$5", 5.00),
            ("$10", 10.00),
            ("$20", 20.00),
            ("$50", 50.00),
            ("$100", 100.00)
        ]
        
        self._build_header()
        self._build_shift_selector()
        self._build_count_section()
        self._build_total_section()
        self._build_actions()
        
        # Auto-load counts for the initial date if file exists
        if initial_date:
            self._auto_load_counts()
        
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
        self._date_change_job = self.after(500, self._auto_load_counts)
    
    def _on_shift_change(self, *args):
        """Called when shift selection changes - load that shift's data"""
        self._highlight_selected_shift()
        self._load_current_shift()
    
    def _highlight_selected_shift(self):
        """Highlight the currently selected shift button"""
        current_shift = self.shift_var.get()
        
        # Reset all buttons to default style
        for btn in self.shift_buttons.values():
            btn.config(bg="white", fg="black", relief="solid", bd=2)
        
        # Highlight selected button
        if current_shift in self.shift_buttons:
            self.shift_buttons[current_shift].config(bg="#2c2c2c", fg="black", relief="solid", bd=3)
    
    def _build_header(self):
        """Build compact mobile header"""
        header_frame = tk.Frame(self.main_frame, bg="#2c2c2c", height=80)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="Cash Drawer Counter",
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
    
    def _build_shift_selector(self):
        """Build shift/time selector"""
        shift_frame = ttk.LabelFrame(self.main_frame, text="Select Count Session", padding="10")
        shift_frame.pack(fill="x", padx=5, pady=5)
        
        self.shift_var = tk.StringVar(value="Day Starting")
        self.shift_var.trace_add("write", self._on_shift_change)
        
        # Create button grid - centered
        button_frame = tk.Frame(shift_frame, bg="white")
        button_frame.pack()
        
        # Configure grid to center content
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(3, weight=1)
        
        # Day row label
        tk.Label(button_frame, text="Day", font=("Arial", 9, "bold"), bg="white", fg="black", anchor="e").grid(row=0, column=1, padx=2, pady=2, sticky="e")
        
        # Day buttons
        self.day_open_btn = tk.Button(button_frame, text="Starting", command=lambda: self.shift_var.set("Day Starting"),
                                      bg="white", fg="black", font=("Arial", 9),
                                      relief="solid", bd=2, padx=5, pady=3, cursor="hand2",
                                      activebackground="#e0e0e0", activeforeground="black", width=10)
        self.day_open_btn.grid(row=1, column=1, padx=2, pady=2)
        
        self.day_close_btn = tk.Button(button_frame, text="Ending", command=lambda: self.shift_var.set("Day Ending"),
                                       bg="white", fg="black", font=("Arial", 9),
                                       relief="solid", bd=2, padx=5, pady=3, cursor="hand2",
                                       activebackground="#e0e0e0", activeforeground="black", width=10)
        self.day_close_btn.grid(row=1, column=2, padx=2, pady=2)
        
        # Night row label
        tk.Label(button_frame, text="Night", font=("Arial", 9, "bold"), bg="white", fg="black", anchor="e").grid(row=2, column=1, padx=2, pady=2, sticky="e")
        
        # Night buttons
        self.night_open_btn = tk.Button(button_frame, text="Starting", command=lambda: self.shift_var.set("Night Starting"),
                                        bg="white", fg="black", font=("Arial", 9),
                                        relief="solid", bd=2, padx=5, pady=3, cursor="hand2",
                                        activebackground="#e0e0e0", activeforeground="black", width=10)
        self.night_open_btn.grid(row=3, column=1, padx=2, pady=2)
        
        self.night_close_btn = tk.Button(button_frame, text="Ending", command=lambda: self.shift_var.set("Night Ending"),
                                         bg="white", fg="black", font=("Arial", 9),
                                         relief="solid", bd=2, padx=5, pady=3, cursor="hand2",
                                         activebackground="#e0e0e0", activeforeground="black", width=10)
        self.night_close_btn.grid(row=3, column=2, padx=2, pady=2)
        
        # Store buttons for highlighting
        self.shift_buttons = {
            "Day Starting": self.day_open_btn,
            "Day Ending": self.day_close_btn,
            "Night Starting": self.night_open_btn,
            "Night Ending": self.night_close_btn
        }
        
        # Highlight initial selection
        self._highlight_selected_shift()
    
    def _build_count_section(self):
        """Build cash counting section"""
        count_frame = ttk.LabelFrame(self.main_frame, text="Count Cash", padding="10")
        count_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Container frame to center the grid
        grid_container = tk.Frame(count_frame, bg="white")
        grid_container.pack(anchor="center")
        
        # Create entry fields for each denomination
        self.count_vars = {}
        self.amount_labels = {}
        
        # Header
        tk.Label(grid_container, text="Unit", font=("Arial", 11, "bold"), bg="white", fg="black", width=12, anchor="center").grid(row=0, column=0, padx=5, pady=5)
        tk.Label(grid_container, text="Quantity", font=("Arial", 11, "bold"), bg="white", fg="black", width=6, anchor="center").grid(row=0, column=1, padx=5, pady=5)
        tk.Label(grid_container, text="Amount", font=("Arial", 11, "bold"), bg="white", fg="black", width=6, anchor="center").grid(row=0, column=2, padx=5, pady=5)
        
        row = 1
        for denom_name, denom_value in self.denominations:
            # Denomination label - centered with larger font
            tk.Label(grid_container, text=denom_name, font=("Arial", 12), bg="white", fg="black", anchor="center", width=12).grid(row=row, column=0, padx=5, pady=2)
            
            # Quantity entry - centered
            var = tk.StringVar(value="0")
            var.trace_add("write", lambda *args: self._update_total())
            entry = tk.Entry(grid_container, textvariable=var, width=6, font=("Arial", 12), fg="black", bg="white", justify="center")
            entry.grid(row=row, column=1, padx=5, pady=2)
            self.count_vars[denom_name] = var
            
            # Amount label - centered, matching quantity width
            amount_label = tk.Label(grid_container, text="$0.00", font=("Arial", 12), bg="white", fg="black", anchor="center", width=6)
            amount_label.grid(row=row, column=2, padx=5, pady=2)
            self.amount_labels[denom_name] = amount_label
            
            row += 1
        
        # Clear counts button
        clear_btn = tk.Button(grid_container, text="Clear All Counts", command=self._clear_counts,
                            bg="white", fg="black", font=("Arial", 9),
                            relief="solid", bd=1, padx=10, pady=3, cursor="hand2",
                            activebackground="#e0e0e0", activeforeground="black")
        clear_btn.grid(row=row, column=0, columnspan=3, pady=10)
    
    def _build_total_section(self):
        """Build total section"""
        total_frame = ttk.LabelFrame(self.main_frame, text="Total", padding="10")
        total_frame.pack(fill="x", padx=5, pady=5)
        
        # Total display (highlighted)
        total_display_frame = tk.Frame(total_frame, bg="#2c2c2c", relief="solid", bd=2)
        total_display_frame.pack(fill="x", pady=5)
        
        shift_label = tk.Label(total_display_frame, text="", font=("Arial", 9, "bold"), bg="#2c2c2c", fg="black", anchor="w")
        shift_label.pack(side="top", padx=10, pady=(10, 0))
        self.shift_label = shift_label
        
        tk.Label(total_display_frame, text="TOTAL IN DRAWER:", font=("Arial", 11, "bold"), bg="#2c2c2c", fg="black", anchor="w").pack(side="left", padx=10, pady=10)
        self.total_var = tk.StringVar(value="$0.00")
        tk.Label(total_display_frame, textvariable=self.total_var, font=("Arial", 11, "bold"), bg="#2c2c2c", fg="black", anchor="e").pack(side="right", padx=10, pady=10)
        
        # All drawer counts summary
        summary_frame = tk.Frame(total_frame, bg="white", relief="solid", bd=1)
        summary_frame.pack(fill="x", pady=5)
        
        tk.Label(summary_frame, text="Drawer Counts Summary", font=("Arial", 9, "bold"), bg="white", fg="black").pack(pady=(5, 2))
        
        # Day and Night headers
        headers_frame = tk.Frame(summary_frame, bg="white")
        headers_frame.pack(fill="x", padx=10, pady=2)
        
        tk.Label(headers_frame, text="Day", font=("Arial", 9, "bold"), bg="white", fg="black", width=20).pack(side="left")
        tk.Label(headers_frame, text="Night", font=("Arial", 9, "bold"), bg="white", fg="black", width=20).pack(side="left")
        
        # Totals display
        totals_frame = tk.Frame(summary_frame, bg="white")
        totals_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        # Day column
        day_frame = tk.Frame(totals_frame, bg="white")
        day_frame.pack(side="left", fill="x", expand=True)
        
        self.day_open_total_var = tk.StringVar(value="O: $0.00")
        tk.Label(day_frame, textvariable=self.day_open_total_var, font=("Arial", 8), bg="white", fg="black", anchor="w").pack(anchor="w")
        
        self.day_close_total_var = tk.StringVar(value="C: $0.00")
        tk.Label(day_frame, textvariable=self.day_close_total_var, font=("Arial", 8), bg="white", fg="black", anchor="w").pack(anchor="w")
        
        # Night column
        night_frame = tk.Frame(totals_frame, bg="white")
        night_frame.pack(side="left", fill="x", expand=True)
        
        self.night_open_total_var = tk.StringVar(value="O: $0.00")
        tk.Label(night_frame, textvariable=self.night_open_total_var, font=("Arial", 8), bg="white", fg="black", anchor="w").pack(anchor="w")
        
        self.night_close_total_var = tk.StringVar(value="C: $0.00")
        tk.Label(night_frame, textvariable=self.night_close_total_var, font=("Arial", 8), bg="white", fg="black", anchor="w").pack(anchor="w")
    
    def _build_actions(self):
        """Build action buttons"""
        action_frame = tk.Frame(self.main_frame, bg="#f0f0f0")
        action_frame.pack(fill="x", padx=5, pady=10)
        
        back_btn = tk.Button(action_frame, text="← Back to Daily Log", command=self._back_to_dailylog,
                           bg="#3a3a3a", fg="black", font=("Arial", 10, "bold"),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#1a1a1a", activeforeground="black")
        back_btn.pack(fill="x", pady=2)
        
        save_btn = tk.Button(action_frame, text="Save Count", command=self._save_counts,
                           bg="#3a3a3a", fg="black", font=("Arial", 10, "bold"),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#1a1a1a", activeforeground="black")
        save_btn.pack(fill="x", pady=2)
        
        load_btn = tk.Button(action_frame, text="Load Counts", command=self._load_counts,
                           bg="#4a4a4a", fg="black", font=("Arial", 10),
                           relief="flat", padx=15, pady=8, cursor="hand2",
                           activebackground="#2a2a2a", activeforeground="black")
        load_btn.pack(fill="x", pady=2)
    
    def _clear_counts(self):
        """Clear all count fields"""
        for var in self.count_vars.values():
            var.set("0")
        self._update_total()
    
    def _update_total(self):
        """Update total and individual amounts"""
        total = 0.0
        
        for denom_name, denom_value in self.denominations:
            try:
                count = int(self.count_vars[denom_name].get() or "0")
                amount = count * denom_value
                total += amount
                self.amount_labels[denom_name].config(text=f"${amount:.2f}")
            except ValueError:
                self.amount_labels[denom_name].config(text="$0.00")
        
        self.total_var.set(f"${total:.2f}")
        
        # Update shift label
        self.shift_label.config(text=f"{self.shift_var.get()}")
        
        # Update all shift totals summary
        self._update_all_shift_totals()
    
    def _update_all_shift_totals(self):
        """Update the summary of all shift totals"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDrawer.csv")
        
        # Initialize totals
        shift_totals = {
            "Day Starting": 0.0,
            "Day Ending": 0.0,
            "Night Starting": 0.0,
            "Night Ending": 0.0
        }
        
        # If current shift has unsaved data, use it
        current_shift = self.shift_var.get()
        current_total = 0.0
        for denom_name, denom_value in self.denominations:
            try:
                count = int(self.count_vars[denom_name].get() or "0")
                current_total += count * denom_value
            except ValueError:
                pass
        shift_totals[current_shift] = current_total
        
        # Load saved data for other shifts
        if os.path.exists(filename):
            try:
                with open(filename, "r", newline="") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    
                    current_read_shift = None
                    for row in rows:
                        if not row:
                            continue
                        if row[0] in shift_totals.keys():
                            current_read_shift = row[0]
                        elif current_read_shift and row[0] == "Total" and len(row) >= 3:
                            # Only update if not the current shift (we already have current shift's live data)
                            if current_read_shift != current_shift:
                                try:
                                    amount_str = row[2].replace("$", "").replace(",", "")
                                    shift_totals[current_read_shift] = float(amount_str)
                                except:
                                    pass
            except Exception as e:
                print(f"Error reading shift totals: {e}")
        
        # Update the display
        self.day_open_total_var.set(f"O: ${shift_totals['Day Starting']:.2f}")
        self.day_close_total_var.set(f"C: ${shift_totals['Day Ending']:.2f}")
        self.night_open_total_var.set(f"O: ${shift_totals['Night Starting']:.2f}")
        self.night_close_total_var.set(f"C: ${shift_totals['Night Ending']:.2f}")
    
    def _save_counts(self):
        """Save cash drawer counts to CSV file"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDrawer.csv")
        
        # Load existing data if file exists
        all_counts = {
            "Day Starting": {},
            "Day Ending": {},
            "Night Starting": {},
            "Night Ending": {}
        }
        
        if os.path.exists(filename):
            try:
                with open(filename, "r", newline="") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    
                    current_shift = None
                    for row in rows:
                        if not row:
                            continue
                        if row[0] in all_counts.keys():
                            current_shift = row[0]
                        elif current_shift and len(row) >= 2 and row[0] != "Denomination":
                            all_counts[current_shift][row[0]] = row[1]
            except Exception as e:
                print(f"Error loading existing counts: {e}")
        
        # Update current shift data
        current_shift = self.shift_var.get()
        all_counts[current_shift] = {}
        for denom_name in self.count_vars.keys():
            all_counts[current_shift][denom_name] = self.count_vars[denom_name].get()
        
        # Save all data
        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", date_str])
                writer.writerow([])
                
                for shift in ["Day Starting", "Day Ending", "Night Starting", "Night Ending"]:
                    writer.writerow([shift])
                    writer.writerow(["Denomination", "Quantity", "Amount"])
                    
                    total = 0.0
                    for denom_name, denom_value in self.denominations:
                        count = all_counts[shift].get(denom_name, "0")
                        try:
                            amount = int(count) * denom_value
                            total += amount
                            writer.writerow([denom_name, count, f"${amount:.2f}"])
                        except:
                            writer.writerow([denom_name, "0", "$0.00"])
                    
                    writer.writerow(["Total", "", f"${total:.2f}"])
                    writer.writerow([])
            
            messagebox.showinfo("Success", f"Cash drawer counts saved!\n\nShift: {current_shift}\nDate: {date_str}")
            
            # Update the summary after saving
            self._update_all_shift_totals()
        
        except Exception as e:
            messagebox.showerror("Error", f"Error saving counts:\n{str(e)}")
    
    def _load_counts(self):
        """Load cash drawer counts from CSV file"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDrawer.csv")
        
        if not os.path.exists(filename):
            messagebox.showwarning("Not Found", f"No saved counts found for:\n{date_str}")
            return
        
        try:
            with open(filename, "r", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                current_shift = None
                shift_data = {
                    "Day Starting": {},
                    "Day Ending": {},
                    "Night Starting": {},
                    "Night Ending": {}
                }
                
                for row in rows:
                    if not row:
                        continue
                    if row[0] in shift_data.keys():
                        current_shift = row[0]
                    elif current_shift and len(row) >= 2 and row[0] != "Denomination" and row[0] != "Total":
                        shift_data[current_shift][row[0]] = row[1]
                
                # Load the current shift's data
                selected_shift = self.shift_var.get()
                for denom_name in self.count_vars.keys():
                    count = shift_data[selected_shift].get(denom_name, "0")
                    self.count_vars[denom_name].set(count)
                
                self._update_total()
                messagebox.showinfo("Success", f"Loaded counts for:\n{selected_shift}\nDate: {date_str}")
                
                # Update the summary after loading
                self._update_all_shift_totals()
        
        except Exception as e:
            messagebox.showerror("Error", f"Error loading counts:\n{str(e)}")
    
    def _load_current_shift(self):
        """Load the currently selected shift's data"""
        date_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
        filename = os.path.join(OUT_DIR, f"{date_str}_CashDrawer.csv")
        
        if not os.path.exists(filename):
            self._clear_counts()
            return
        
        try:
            with open(filename, "r", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                current_shift = None
                shift_data = {
                    "Day Starting": {},
                    "Day Ending": {},
                    "Night Starting": {},
                    "Night Ending": {}
                }
                
                for row in rows:
                    if not row:
                        continue
                    if row[0] in shift_data.keys():
                        current_shift = row[0]
                    elif current_shift and len(row) >= 2 and row[0] != "Denomination" and row[0] != "Total":
                        shift_data[current_shift][row[0]] = row[1]
                
                # Load the current shift's data
                selected_shift = self.shift_var.get()
                for denom_name in self.count_vars.keys():
                    count = shift_data[selected_shift].get(denom_name, "0")
                    self.count_vars[denom_name].set(count)
                
                self._update_total()
        
        except Exception as e:
            print(f"Error loading shift data: {e}")
            self._clear_counts()
    
    def _auto_load_counts(self):
        """Automatically load counts when date changes"""
        self._load_current_shift()
    
    def _back_to_dailylog(self):
        """Close this window and return to daily log"""
        self.destroy()


if __name__ == "__main__":
    # Check if date was passed as command-line argument
    initial_date = sys.argv[1] if len(sys.argv) > 1 else None
    app = CashDrawerApp(initial_date)
    app.mainloop()
