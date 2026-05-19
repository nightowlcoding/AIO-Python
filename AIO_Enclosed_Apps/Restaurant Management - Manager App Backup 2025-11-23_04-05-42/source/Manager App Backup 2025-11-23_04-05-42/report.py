import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Scrollbar
from datetime import datetime, timedelta
from tkcalendar import DateEntry

OUT_DIR = os.path.expanduser("~/Documents/AIO Python/daily_logs")

class ReportApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Reports")
        self.geometry("360x800")
        self.configure(bg="white")
        self.resizable(False, False)
        
        # Load available employees
        self.employees = self._load_employees()
        
        # Main container
        main_frame = tk.Frame(self, bg="white")
        main_frame.pack(fill="both", expand=True)
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#2c2c2c", height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="Reports", font=("Helvetica", 24, "bold"),
                bg="#2c2c2c", fg="black").pack(pady=20)
        
        # Scrollable content area
        canvas_frame = tk.Frame(main_frame, bg="white")
        canvas_frame.pack(fill="both", expand=True)
        
        canvas = Canvas(canvas_frame, bg="white", highlightthickness=0)
        scrollbar = Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.content_frame = tk.Frame(canvas, bg="white")
        
        self.content_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.content_frame, anchor="nw", width=320)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y", pady=20, padx=(0, 5))
        
        self.canvas = canvas
        
        # Build UI
        self._build_filters()
        self._build_results_section()
        self._build_action_buttons()
        
        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def _load_employees(self):
        """Load unique employee names from daily log files"""
        employees = set()
        
        if not os.path.exists(OUT_DIR):
            return sorted(list(employees))
        
        for filename in os.listdir(OUT_DIR):
            if filename.endswith('.csv') and not filename.endswith('_CashDeductions.csv'):
                filepath = os.path.join(OUT_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        lines = list(reader)
                        
                        # Find "Employee Entries" section
                        for i, row in enumerate(lines):
                            if row and row[0] == "Employee Entries":
                                # Next row is header, skip it
                                # Following rows are employee data
                                for j in range(i + 2, len(lines)):
                                    if lines[j] and lines[j][0]:
                                        name = lines[j][0].strip()
                                        if name and name != "Name":
                                            employees.add(name)
                                break
                except Exception:
                    pass
        
        return sorted(list(employees))
    
    def _build_filters(self):
        """Build filter section"""
        filter_frame = tk.Frame(self.content_frame, bg="#f5f5f5", relief="solid", bd=1)
        filter_frame.pack(fill="x", pady=(0, 15))
        
        tk.Label(filter_frame, text="Filter Options",
                font=("Helvetica", 14, "bold"),
                bg="#f5f5f5", fg="black").pack(pady=(15, 10))
        
        # Employee filter
        emp_container = tk.Frame(filter_frame, bg="#f5f5f5")
        emp_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(emp_container, text="Employee:",
                font=("Helvetica", 11, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(5, 2))
        
        self.employee_var = tk.StringVar(value="All Employees")
        employee_dropdown = ttk.Combobox(emp_container, textvariable=self.employee_var,
                                        values=["All Employees"] + self.employees,
                                        state="readonly", font=("Helvetica", 10))
        employee_dropdown.pack(fill="x", pady=(0, 5))
        
        # Date range filter
        date_container = tk.Frame(filter_frame, bg="#f5f5f5")
        date_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(date_container, text="Date Range:",
                font=("Helvetica", 11, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(5, 2))
        
        # From date
        from_frame = tk.Frame(date_container, bg="#f5f5f5")
        from_frame.pack(fill="x", pady=2)
        
        tk.Label(from_frame, text="From:", font=("Helvetica", 10),
                bg="#f5f5f5", fg="black").pack(side="left", padx=(0, 5))
        
        self.from_date = DateEntry(from_frame, width=18, background='#3a3a3a',
                                   foreground='white', borderwidth=2,
                                   font=("Helvetica", 10),
                                   date_pattern='yyyy-mm-dd')
        self.from_date.pack(side="left")
        
        # To date
        to_frame = tk.Frame(date_container, bg="#f5f5f5")
        to_frame.pack(fill="x", pady=2)
        
        tk.Label(to_frame, text="To:", font=("Helvetica", 10),
                bg="#f5f5f5", fg="black").pack(side="left", padx=(0, 5))
        
        self.to_date = DateEntry(to_frame, width=18, background='#3a3a3a',
                                foreground='white', borderwidth=2,
                                font=("Helvetica", 10),
                                date_pattern='yyyy-mm-dd')
        self.to_date.pack(side="left")
        
        # Shift filter
        shift_container = tk.Frame(filter_frame, bg="#f5f5f5")
        shift_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(shift_container, text="Shift:",
                font=("Helvetica", 11, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(5, 2))
        
        self.shift_var = tk.StringVar(value="All Shifts")
        shift_dropdown = ttk.Combobox(shift_container, textvariable=self.shift_var,
                                     values=["All Shifts", "Day", "Night"],
                                     state="readonly", font=("Helvetica", 10))
        shift_dropdown.pack(fill="x", pady=(0, 5))
        
        # Generate report button
        generate_btn = tk.Button(filter_frame, text="Generate Report",
                                command=self._generate_report,
                                bg="#3a3a3a", fg="black",
                                activebackground="#1a1a1a", activeforeground="black",
                                font=("Helvetica", 12, "bold"),
                                relief="flat", cursor="hand2", height=2)
        generate_btn.pack(pady=15, padx=15, fill="x")
        generate_btn.bind("<Enter>", lambda e: generate_btn.config(bg="#4a4a4a"))
        generate_btn.bind("<Leave>", lambda e: generate_btn.config(bg="#3a3a3a"))
    
    def _build_results_section(self):
        """Build results display section"""
        results_frame = tk.Frame(self.content_frame, bg="white")
        results_frame.pack(fill="both", expand=True)
        
        tk.Label(results_frame, text="Report Results",
                font=("Helvetica", 14, "bold"),
                bg="white", fg="black").pack(pady=(0, 10))
        
        # Results container with border
        self.results_container = tk.Frame(results_frame, bg="#f9f9f9", relief="solid", bd=1)
        self.results_container.pack(fill="both", expand=True)
        
        # Initial placeholder
        tk.Label(self.results_container, text="Select filters and click 'Generate Report'",
                font=("Helvetica", 11), bg="#f9f9f9", fg="black").pack(pady=30)
    
    def _build_action_buttons(self):
        """Build action buttons at bottom"""
        actions_frame = tk.Frame(self.content_frame, bg="white")
        actions_frame.pack(fill="x", pady=(20, 10))
        
        # Export button
        self.export_btn = tk.Button(actions_frame, text="Export to CSV",
                                    command=self._export_report,
                                    bg="#3a3a3a", fg="black",
                                    activebackground="#1a1a1a", activeforeground="black",
                                    font=("Helvetica", 11, "bold"),
                                    relief="flat", cursor="hand2", height=2,
                                    state="disabled")
        self.export_btn.pack(pady=5, fill="x", padx=2)
        self.export_btn.bind("<Enter>", lambda e: self.export_btn.config(bg="#4a4a4a") if self.export_btn['state'] == 'normal' else None)
        self.export_btn.bind("<Leave>", lambda e: self.export_btn.config(bg="#3a3a3a") if self.export_btn['state'] == 'normal' else None)
        
        # Close button
        close_btn = tk.Button(actions_frame, text="Close",
                             command=self.destroy,
                             bg="#2c2c2c", fg="black",
                             activebackground="#0c0c0c", activeforeground="black",
                             font=("Helvetica", 12, "bold"),
                             relief="flat", cursor="hand2", height=2)
        close_btn.pack(pady=5, fill="x", padx=2)
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#3c3c3c"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#2c2c2c"))
    
    def _generate_report(self):
        """Generate report based on filters"""
        # Clear existing results
        for widget in self.results_container.winfo_children():
            widget.destroy()
        
        # Get filter values
        employee = self.employee_var.get()
        from_date = self.from_date.get_date()
        to_date = self.to_date.get_date()
        shift = self.shift_var.get()
        
        # Validate dates
        if from_date > to_date:
            messagebox.showerror("Error", "From date must be before To date")
            return
        
        # Collect data
        report_data = []
        current_date = from_date
        
        while current_date <= to_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Check both shifts if "All Shifts" selected
            shifts_to_check = ["Day", "Night"] if shift == "All Shifts" else [shift]
            
            for shift_name in shifts_to_check:
                filename = f"{date_str}_{shift_name}.csv"
                filepath = os.path.join(OUT_DIR, filename)
                
                if os.path.exists(filepath):
                    data = self._parse_log_file(filepath, employee)
                    report_data.extend(data)
            
            current_date += timedelta(days=1)
        
        # Display results
        self._display_report(report_data)
        
        # Enable export button if we have data
        if report_data:
            self.export_btn.config(state="normal")
            self.current_report_data = report_data
        else:
            self.export_btn.config(state="disabled")
            self.current_report_data = []
    
    def _parse_log_file(self, filepath, employee_filter):
        """Parse a daily log file and extract employee data"""
        data = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                lines = list(reader)
            
            # Extract date and shift from header
            date = None
            shift = None
            
            for row in lines[:10]:  # Check first 10 rows for metadata
                if row and len(row) >= 2:
                    if row[0] == "Date":
                        date = row[1]
                    elif row[0] == "Shift":
                        shift = row[1]
            
            # Find employee entries
            for i, row in enumerate(lines):
                if row and row[0] == "Employee Entries":
                    # Next row is header
                    if i + 1 < len(lines):
                        headers = lines[i + 1]
                    
                    # Following rows are employee data
                    for j in range(i + 2, len(lines)):
                        if lines[j] and lines[j][0]:
                            emp_row = lines[j]
                            emp_name = emp_row[0].strip()
                            
                            # Apply employee filter
                            if employee_filter != "All Employees" and emp_name != employee_filter:
                                continue
                            
                            # Extract employee data
                            entry = {
                                'Date': date or 'Unknown',
                                'Shift': shift or 'Unknown',
                                'Name': emp_name,
                                'Area': emp_row[1] if len(emp_row) > 1 else '',
                                'Cash': emp_row[2] if len(emp_row) > 2 else '0.00',
                                'Credit Total': emp_row[3] if len(emp_row) > 3 else '0.00',
                                'CC Received': emp_row[4] if len(emp_row) > 4 else '0.00',
                                'Voids': emp_row[5] if len(emp_row) > 5 else '0.00',
                                'Beer': emp_row[6] if len(emp_row) > 6 else '0.00',
                                'Liquor': emp_row[7] if len(emp_row) > 7 else '0.00',
                                'Wine': emp_row[8] if len(emp_row) > 8 else '0.00',
                                'Food': emp_row[9] if len(emp_row) > 9 else '0.00',
                            }
                            
                            data.append(entry)
                    break
        
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        
        return data
    
    def _display_report(self, data):
        """Display report data in results container"""
        # Clear container
        for widget in self.results_container.winfo_children():
            widget.destroy()
        
        if not data:
            tk.Label(self.results_container, text="No data found for selected filters",
                    font=("Helvetica", 11), bg="#f9f9f9", fg="black").pack(pady=30)
            return
        
        # Summary section
        summary_frame = tk.Frame(self.results_container, bg="#e8f4f8", relief="solid", bd=1)
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(summary_frame, text="Summary",
                font=("Helvetica", 12, "bold"),
                bg="#e8f4f8", fg="black").pack(pady=(8, 5))
        
        # Calculate totals
        total_cash = sum(float(entry['Cash']) for entry in data)
        total_credit = sum(float(entry['Credit Total']) for entry in data)
        total_sales = sum(float(entry['Beer']) + float(entry['Liquor']) + 
                         float(entry['Wine']) + float(entry['Food']) for entry in data)
        
        summary_text = f"Total Entries: {len(data)}\n"
        summary_text += f"Total Cash: ${total_cash:,.2f}\n"
        summary_text += f"Total Credit: ${total_credit:,.2f}\n"
        summary_text += f"Total Sales: ${total_sales:,.2f}"
        
        tk.Label(summary_frame, text=summary_text,
                font=("Helvetica", 10), bg="#e8f4f8", fg="black",
                justify="left").pack(pady=(0, 8), padx=10)
        
        # Individual entries
        entries_label = tk.Label(self.results_container, text="Detailed Entries",
                                font=("Helvetica", 11, "bold"),
                                bg="#f9f9f9", fg="black")
        entries_label.pack(pady=(10, 5))
        
        # Create scrollable frame for entries
        entries_canvas = Canvas(self.results_container, bg="#f9f9f9", highlightthickness=0, height=300)
        entries_scrollbar = Scrollbar(self.results_container, orient="vertical", command=entries_canvas.yview)
        entries_frame = tk.Frame(entries_canvas, bg="#f9f9f9")
        
        entries_frame.bind(
            "<Configure>",
            lambda e: entries_canvas.configure(scrollregion=entries_canvas.bbox("all"))
        )
        
        entries_canvas.create_window((0, 0), window=entries_frame, anchor="nw")
        entries_canvas.configure(yscrollcommand=entries_scrollbar.set)
        
        entries_canvas.pack(side="left", fill="both", expand=True, padx=10)
        entries_scrollbar.pack(side="right", fill="y")
        
        # Display each entry
        for i, entry in enumerate(data):
            entry_frame = tk.Frame(entries_frame, bg="white", relief="solid", bd=1)
            entry_frame.pack(fill="x", pady=3, padx=5)
            
            # Header with name and date
            header = tk.Frame(entry_frame, bg="#3a3a3a")
            header.pack(fill="x")
            
            tk.Label(header, text=f"{entry['Name']} - {entry['Date']} ({entry['Shift']})",
                    font=("Helvetica", 10, "bold"),
                    bg="#3a3a3a", fg="black").pack(pady=5, padx=8, anchor="w")
            
            # Details
            details = tk.Frame(entry_frame, bg="white")
            details.pack(fill="x", padx=8, pady=5)
            
            # Create two columns
            col1 = tk.Frame(details, bg="white")
            col1.pack(side="left", fill="both", expand=True)
            
            col2 = tk.Frame(details, bg="white")
            col2.pack(side="left", fill="both", expand=True)
            
            # Column 1
            self._add_detail_row(col1, "Area:", entry['Area'])
            self._add_detail_row(col1, "Cash:", f"${float(entry['Cash']):,.2f}")
            self._add_detail_row(col1, "Credit:", f"${float(entry['Credit Total']):,.2f}")
            self._add_detail_row(col1, "CC Received:", f"${float(entry['CC Received']):,.2f}")
            
            # Column 2
            self._add_detail_row(col2, "Voids:", f"${float(entry['Voids']):,.2f}")
            self._add_detail_row(col2, "Beer:", f"${float(entry['Beer']):,.2f}")
            self._add_detail_row(col2, "Liquor:", f"${float(entry['Liquor']):,.2f}")
            self._add_detail_row(col2, "Wine:", f"${float(entry['Wine']):,.2f}")
            self._add_detail_row(col2, "Food:", f"${float(entry['Food']):,.2f}")
    
    def _add_detail_row(self, parent, label, value):
        """Add a detail row to the entry display"""
        row = tk.Frame(parent, bg="white")
        row.pack(fill="x", pady=1)
        
        tk.Label(row, text=label, font=("Helvetica", 9, "bold"),
                bg="white", fg="black", width=12, anchor="w").pack(side="left")
        
        tk.Label(row, text=value, font=("Helvetica", 9),
                bg="white", fg="black", anchor="w").pack(side="left")
    
    def _export_report(self):
        """Export current report to CSV"""
        if not hasattr(self, 'current_report_data') or not self.current_report_data:
            messagebox.showwarning("Warning", "No report data to export")
            return
        
        from tkinter import filedialog
        
        # Generate default filename
        from_date = self.from_date.get_date().strftime("%Y-%m-%d")
        to_date = self.to_date.get_date().strftime("%Y-%m-%d")
        default_name = f"Report_{from_date}_to_{to_date}.csv"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name
        )
        
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # Write header
                    headers = ['Date', 'Shift', 'Name', 'Area', 'Cash', 'Credit Total',
                              'CC Received', 'Voids', 'Beer', 'Liquor', 'Wine', 'Food']
                    writer.writerow(headers)
                    
                    # Write data
                    for entry in self.current_report_data:
                        row = [entry.get(h, '') for h in headers]
                        writer.writerow(row)
                
                messagebox.showinfo("Success", f"Report exported to:\n{filename}")
            
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export report:\n{str(e)}")


if __name__ == "__main__":
    app = ReportApp()
    app.mainloop()
