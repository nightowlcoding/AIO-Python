import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Scrollbar
from datetime import datetime

EMPLOYEE_LIST_FILE = os.path.expanduser("~/Documents/AIO Python/employee_list.csv")

class EmployeeMaintenanceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Employee Maintenance")
        self.geometry("360x800")
        self.configure(bg="white")
        self.resizable(False, False)
        
        # Load employees
        self.employees = self._load_employees()
        
        # Main container
        main_frame = tk.Frame(self, bg="white")
        main_frame.pack(fill="both", expand=True)
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#2c2c2c", height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="Employee Maintenance", font=("Helvetica", 20, "bold"),
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
        self._build_add_section()
        self._build_employee_list()
        self._build_action_buttons()
        
        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def _load_employees(self):
        """Load employees from CSV file"""
        employees = []
        
        if os.path.exists(EMPLOYEE_LIST_FILE):
            try:
                with open(EMPLOYEE_LIST_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        employees.append(row)
            except Exception as e:
                print(f"Error loading employees: {e}")
        
        return employees
    
    def _save_employees(self):
        """Save employees to CSV file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(EMPLOYEE_LIST_FILE), exist_ok=True)
            
            with open(EMPLOYEE_LIST_FILE, 'w', newline='', encoding='utf-8') as f:
                if self.employees:
                    fieldnames = ['name', 'position', 'phone', 'email', 'hire_date', 'status']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(self.employees)
            
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save employees:\n{str(e)}")
            return False
    
    def _build_add_section(self):
        """Build add new employee section"""
        add_frame = tk.Frame(self.content_frame, bg="#f5f5f5", relief="solid", bd=1)
        add_frame.pack(fill="x", pady=(0, 15))
        
        tk.Label(add_frame, text="Quick Add Employee",
                font=("Helvetica", 14, "bold"),
                bg="#f5f5f5", fg="black").pack(pady=(15, 10))
        
        # Name
        name_container = tk.Frame(add_frame, bg="#f5f5f5")
        name_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(name_container, text="Name:",
                font=("Helvetica", 10, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(0, 2))
        
        self.name_var = tk.StringVar()
        name_entry = tk.Entry(name_container, textvariable=self.name_var,
                             font=("Helvetica", 11), relief="solid", bd=1)
        name_entry.pack(fill="x", pady=(0, 5))
        
        # Position
        position_container = tk.Frame(add_frame, bg="#f5f5f5")
        position_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(position_container, text="Position:",
                font=("Helvetica", 10, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(0, 2))
        
        self.position_var = tk.StringVar()
        position_entry = tk.Entry(position_container, textvariable=self.position_var,
                                 font=("Helvetica", 11), relief="solid", bd=1)
        position_entry.pack(fill="x", pady=(0, 5))
        
        # Phone
        phone_container = tk.Frame(add_frame, bg="#f5f5f5")
        phone_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(phone_container, text="Phone:",
                font=("Helvetica", 10, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(0, 2))
        
        self.phone_var = tk.StringVar()
        phone_entry = tk.Entry(phone_container, textvariable=self.phone_var,
                              font=("Helvetica", 11), relief="solid", bd=1)
        phone_entry.pack(fill="x", pady=(0, 5))
        
        # Email
        email_container = tk.Frame(add_frame, bg="#f5f5f5")
        email_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(email_container, text="Email:",
                font=("Helvetica", 10, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(0, 2))
        
        self.email_var = tk.StringVar()
        email_entry = tk.Entry(email_container, textvariable=self.email_var,
                              font=("Helvetica", 11), relief="solid", bd=1)
        email_entry.pack(fill="x", pady=(0, 5))
        
        # Status
        status_container = tk.Frame(add_frame, bg="#f5f5f5")
        status_container.pack(fill="x", padx=15, pady=5)
        
        tk.Label(status_container, text="Status:",
                font=("Helvetica", 10, "bold"),
                bg="#f5f5f5", fg="black").pack(anchor="w", pady=(0, 2))
        
        self.status_var = tk.StringVar(value="Active")
        status_dropdown = ttk.Combobox(status_container, textvariable=self.status_var,
                                      values=["Active", "Inactive"],
                                      state="readonly", font=("Helvetica", 10))
        status_dropdown.pack(fill="x", pady=(0, 5))
        
        # Add button
        add_btn = tk.Button(add_frame, text="Add Employee",
                           command=self._add_employee,
                           bg="#3a3a3a", fg="black",
                           activebackground="#1a1a1a", activeforeground="black",
                           font=("Helvetica", 12, "bold"),
                           relief="flat", cursor="hand2", height=2)
        add_btn.pack(pady=15, padx=15, fill="x")
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#4a4a4a"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#3a3a3a"))
    
    def _build_employee_list(self):
        """Build employee list section"""
        list_frame = tk.Frame(self.content_frame, bg="white")
        list_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        tk.Label(list_frame, text="Employee Management",
                font=("Helvetica", 14, "bold"),
                bg="white", fg="black").pack(pady=(0, 10))
        
        # Action buttons
        action_buttons_frame = tk.Frame(list_frame, bg="white")
        action_buttons_frame.pack(fill="x", pady=(0, 10))
        
        # Bulk Import button
        bulk_import_btn = tk.Button(action_buttons_frame, text="📁 Bulk Import",
                                    command=self._bulk_import,
                                    bg="#2196F3", fg="black",
                                    activebackground="#1976D2", activeforeground="black",
                                    font=("Helvetica", 11, "bold"),
                                    relief="flat", cursor="hand2", height=2)
        bulk_import_btn.pack(side="left", padx=(0, 5), fill="x", expand=True)
        bulk_import_btn.bind("<Enter>", lambda e: bulk_import_btn.config(bg="#1976D2"))
        bulk_import_btn.bind("<Leave>", lambda e: bulk_import_btn.config(bg="#2196F3"))
        
        # Download Template button
        template_btn = tk.Button(action_buttons_frame, text="⬇ Download Template",
                                command=self._download_template,
                                bg="#4CAF50", fg="black",
                                activebackground="#388E3C", activeforeground="black",
                                font=("Helvetica", 11, "bold"),
                                relief="flat", cursor="hand2", height=2)
        template_btn.pack(side="left", fill="x", expand=True)
        template_btn.bind("<Enter>", lambda e: template_btn.config(bg="#388E3C"))
        template_btn.bind("<Leave>", lambda e: template_btn.config(bg="#4CAF50"))
        
        # Current Employee List button
        view_list_btn = tk.Button(list_frame, text="📋 Current Employee List",
                                  command=self._show_employee_list,
                                  bg="#3a3a3a", fg="black",
                                  activebackground="#1a1a1a", activeforeground="black",
                                  font=("Helvetica", 12, "bold"),
                                  relief="flat", cursor="hand2", height=2)
        view_list_btn.pack(fill="x", pady=(10, 0), padx=2)
        view_list_btn.bind("<Enter>", lambda e: view_list_btn.config(bg="#4a4a4a"))
        view_list_btn.bind("<Leave>", lambda e: view_list_btn.config(bg="#3a3a3a"))
        
        # Container for employee cards (hidden by default, shown when view list is clicked)
        self.employee_list_container = tk.Frame(list_frame, bg="white")
        self.employee_list_container.pack(fill="both", expand=True)
        self.employee_list_container.pack_forget()  # Hide initially
    
    def _refresh_employee_list(self):
        """Refresh the employee list display"""
        # Clear existing widgets
        for widget in self.employee_list_container.winfo_children():
            widget.destroy()
        
        if not self.employees:
            tk.Label(self.employee_list_container, text="No employees found",
                    font=("Helvetica", 11), bg="white", fg="black").pack(pady=30)
            return
        
        # Display each employee
        for i, emp in enumerate(self.employees):
            emp_frame = tk.Frame(self.employee_list_container, bg="white", relief="solid", bd=1)
            emp_frame.pack(fill="x", pady=5)
            
            # Header with name and status
            header = tk.Frame(emp_frame, bg="#3a3a3a")
            header.pack(fill="x")
            
            name_label = tk.Label(header, text=emp.get('name', 'Unknown'),
                                 font=("Helvetica", 11, "bold"),
                                 bg="#3a3a3a", fg="black")
            name_label.pack(side="left", pady=8, padx=10)
            
            # Status indicator
            status = emp.get('status', 'Active')
            status_color = "#4CAF50" if status == "Active" else "#f44336"
            status_label = tk.Label(header, text=status,
                                   font=("Helvetica", 9, "bold"),
                                   bg=status_color, fg="black",
                                   padx=8, pady=2)
            status_label.pack(side="right", pady=8, padx=10)
            
            # Details
            details = tk.Frame(emp_frame, bg="white")
            details.pack(fill="x", padx=10, pady=8)
            
            # Position
            if emp.get('position'):
                self._add_detail_row(details, "Position:", emp['position'])
            
            # Phone
            if emp.get('phone'):
                self._add_detail_row(details, "Phone:", emp['phone'])
            
            # Email
            if emp.get('email'):
                self._add_detail_row(details, "Email:", emp['email'])
            
            # Hire date
            if emp.get('hire_date'):
                self._add_detail_row(details, "Hired:", emp['hire_date'])
            
            # Actions
            actions = tk.Frame(emp_frame, bg="white")
            actions.pack(fill="x", padx=10, pady=(0, 8))
            
            # Edit button
            edit_btn = tk.Button(actions, text="Edit",
                                command=lambda idx=i: self._edit_employee(idx),
                                bg="#2196F3", fg="black",
                                activebackground="#1976D2", activeforeground="black",
                                font=("Helvetica", 9, "bold"),
                                relief="flat", cursor="hand2", width=10)
            edit_btn.pack(side="left", padx=(0, 5))
            edit_btn.bind("<Enter>", lambda e, b=edit_btn: b.config(bg="#1976D2"))
            edit_btn.bind("<Leave>", lambda e, b=edit_btn: b.config(bg="#2196F3"))
            
            # Delete button
            delete_btn = tk.Button(actions, text="Delete",
                                  command=lambda idx=i: self._delete_employee(idx),
                                  bg="#f44336", fg="black",
                                  activebackground="#d32f2f", activeforeground="black",
                                  font=("Helvetica", 9, "bold"),
                                  relief="flat", cursor="hand2", width=10)
            delete_btn.pack(side="left")
            delete_btn.bind("<Enter>", lambda e, b=delete_btn: b.config(bg="#d32f2f"))
            delete_btn.bind("<Leave>", lambda e, b=delete_btn: b.config(bg="#f44336"))
    
    def _add_detail_row(self, parent, label, value):
        """Add a detail row to employee card"""
        row = tk.Frame(parent, bg="white")
        row.pack(fill="x", pady=2)
        
        tk.Label(row, text=label, font=("Helvetica", 9, "bold"),
                bg="white", fg="black", width=10, anchor="w").pack(side="left")
        
        tk.Label(row, text=value, font=("Helvetica", 9),
                bg="white", fg="black", anchor="w").pack(side="left", fill="x", expand=True)
    
    def _add_employee(self):
        """Add a new employee"""
        name = self.name_var.get().strip()
        position = self.position_var.get().strip()
        phone = self.phone_var.get().strip()
        email = self.email_var.get().strip()
        status = self.status_var.get()
        
        if not name:
            messagebox.showwarning("Warning", "Employee name is required")
            return
        
        # Create employee record
        employee = {
            'name': name,
            'position': position,
            'phone': phone,
            'email': email,
            'hire_date': datetime.now().strftime("%Y-%m-%d"),
            'status': status
        }
        
        self.employees.append(employee)
        
        if self._save_employees():
            # Clear form
            self.name_var.set("")
            self.position_var.set("")
            self.phone_var.set("")
            self.email_var.set("")
            self.status_var.set("Active")
            
            # Refresh list if visible
            if self.employee_list_container.winfo_ismapped():
                self._refresh_employee_list()
            
            messagebox.showinfo("Success", f"Employee '{name}' added successfully!")
    
    def _download_template(self):
        """Download a CSV template for bulk import"""
        from tkinter import filedialog
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="employee_import_template.csv"
        )
        
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    # Write header
                    writer.writerow(['name', 'position', 'phone', 'email', 'status'])
                    # Write sample data
                    writer.writerow(['John Doe', 'Server', '555-0123', 'john.doe@example.com', 'Active'])
                    writer.writerow(['Jane Smith', 'Bartender', '555-0124', 'jane.smith@example.com', 'Active'])
                    writer.writerow(['Bob Johnson', 'Manager', '555-0125', 'bob.johnson@example.com', 'Active'])
                
                messagebox.showinfo("Success", f"Template saved to:\n{filename}\n\nEdit this file and use 'Bulk Import' to add employees.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save template:\n{str(e)}")
    
    def _bulk_import(self):
        """Import employees from CSV file"""
        from tkinter import filedialog
        
        filename = filedialog.askopenfilename(
            title="Select Employee CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            imported_count = 0
            skipped_count = 0
            errors = []
            
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Validate header
                required_fields = ['name']
                if not all(field in reader.fieldnames for field in required_fields):
                    messagebox.showerror("Error", "CSV file must have at least a 'name' column.\n\nRequired: name\nOptional: position, phone, email, status")
                    return
                
                for row_num, row in enumerate(reader, start=2):
                    name = row.get('name', '').strip()
                    
                    if not name:
                        skipped_count += 1
                        errors.append(f"Row {row_num}: Missing name")
                        continue
                    
                    # Check for duplicates
                    if any(emp['name'].lower() == name.lower() for emp in self.employees):
                        skipped_count += 1
                        errors.append(f"Row {row_num}: '{name}' already exists")
                        continue
                    
                    # Create employee record
                    employee = {
                        'name': name,
                        'position': row.get('position', '').strip(),
                        'phone': row.get('phone', '').strip(),
                        'email': row.get('email', '').strip(),
                        'hire_date': datetime.now().strftime("%Y-%m-%d"),
                        'status': row.get('status', 'Active').strip() or 'Active'
                    }
                    
                    self.employees.append(employee)
                    imported_count += 1
            
            if imported_count > 0:
                if self._save_employees():
                    if self.employee_list_container.winfo_ismapped():
                        self._refresh_employee_list()
                    
                    # Show summary
                    summary = f"Successfully imported {imported_count} employee(s)."
                    if skipped_count > 0:
                        summary += f"\n\nSkipped {skipped_count} row(s):"
                        summary += "\n" + "\n".join(errors[:10])  # Show first 10 errors
                        if len(errors) > 10:
                            summary += f"\n... and {len(errors) - 10} more"
                    
                    messagebox.showinfo("Import Complete", summary)
                else:
                    messagebox.showerror("Error", "Failed to save imported employees")
            else:
                messagebox.showwarning("No Import", f"No employees were imported.\n\n{len(errors)} error(s):\n" + "\n".join(errors[:10]))
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import employees:\n{str(e)}")
    
    def _show_employee_list(self):
        """Toggle employee list visibility"""
        if self.employee_list_container.winfo_ismapped():
            # Hide the list
            self.employee_list_container.pack_forget()
        else:
            # Show the list
            self._refresh_employee_list()
            self.employee_list_container.pack(fill="both", expand=True, pady=(10, 0))
    
    def _edit_employee(self, index):
        """Edit an employee"""
        if index < 0 or index >= len(self.employees):
            return
        
        emp = self.employees[index]
        
        # Create edit window
        edit_window = tk.Toplevel(self)
        edit_window.title("Edit Employee")
        edit_window.geometry("320x500")
        edit_window.configure(bg="white")
        edit_window.resizable(False, False)
        
        # Center window
        edit_window.update_idletasks()
        x = (edit_window.winfo_screenwidth() // 2) - (320 // 2)
        y = (edit_window.winfo_screenheight() // 2) - (500 // 2)
        edit_window.geometry(f'320x500+{x}+{y}')
        
        # Header
        header = tk.Frame(edit_window, bg="#2c2c2c", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text="Edit Employee", font=("Helvetica", 18, "bold"),
                bg="#2c2c2c", fg="black").pack(pady=15)
        
        # Form
        form_frame = tk.Frame(edit_window, bg="white")
        form_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Name
        tk.Label(form_frame, text="Name:", font=("Helvetica", 10, "bold"),
                bg="white", fg="black").pack(anchor="w", pady=(5, 2))
        name_var = tk.StringVar(value=emp.get('name', ''))
        tk.Entry(form_frame, textvariable=name_var, font=("Helvetica", 11),
                relief="solid", bd=1).pack(fill="x", pady=(0, 10))
        
        # Position
        tk.Label(form_frame, text="Position:", font=("Helvetica", 10, "bold"),
                bg="white", fg="black").pack(anchor="w", pady=(5, 2))
        position_var = tk.StringVar(value=emp.get('position', ''))
        tk.Entry(form_frame, textvariable=position_var, font=("Helvetica", 11),
                relief="solid", bd=1).pack(fill="x", pady=(0, 10))
        
        # Phone
        tk.Label(form_frame, text="Phone:", font=("Helvetica", 10, "bold"),
                bg="white", fg="black").pack(anchor="w", pady=(5, 2))
        phone_var = tk.StringVar(value=emp.get('phone', ''))
        tk.Entry(form_frame, textvariable=phone_var, font=("Helvetica", 11),
                relief="solid", bd=1).pack(fill="x", pady=(0, 10))
        
        # Email
        tk.Label(form_frame, text="Email:", font=("Helvetica", 10, "bold"),
                bg="white", fg="black").pack(anchor="w", pady=(5, 2))
        email_var = tk.StringVar(value=emp.get('email', ''))
        tk.Entry(form_frame, textvariable=email_var, font=("Helvetica", 11),
                relief="solid", bd=1).pack(fill="x", pady=(0, 10))
        
        # Status
        tk.Label(form_frame, text="Status:", font=("Helvetica", 10, "bold"),
                bg="white", fg="black").pack(anchor="w", pady=(5, 2))
        status_var = tk.StringVar(value=emp.get('status', 'Active'))
        ttk.Combobox(form_frame, textvariable=status_var,
                    values=["Active", "Inactive"],
                    state="readonly", font=("Helvetica", 10)).pack(fill="x", pady=(0, 10))
        
        # Save button
        def save_changes():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Employee name is required")
                return
            
            self.employees[index] = {
                'name': name,
                'position': position_var.get().strip(),
                'phone': phone_var.get().strip(),
                'email': email_var.get().strip(),
                'hire_date': emp.get('hire_date', datetime.now().strftime("%Y-%m-%d")),
                'status': status_var.get()
            }
            
            if self._save_employees():
                if self.employee_list_container.winfo_ismapped():
                    self._refresh_employee_list()
                edit_window.destroy()
                messagebox.showinfo("Success", "Employee updated successfully!")
        
        save_btn = tk.Button(form_frame, text="Save Changes",
                            command=save_changes,
                            bg="#3a3a3a", fg="black",
                            activebackground="#1a1a1a", activeforeground="black",
                            font=("Helvetica", 11, "bold"),
                            relief="flat", cursor="hand2", height=2)
        save_btn.pack(fill="x", pady=(10, 5))
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#4a4a4a"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#3a3a3a"))
        
        # Cancel button
        cancel_btn = tk.Button(form_frame, text="Cancel",
                              command=edit_window.destroy,
                              bg="#2c2c2c", fg="black",
                              activebackground="#0c0c0c", activeforeground="black",
                              font=("Helvetica", 11, "bold"),
                              relief="flat", cursor="hand2", height=2)
        cancel_btn.pack(fill="x", pady=5)
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#3c3c3c"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg="#2c2c2c"))
    
    def _delete_employee(self, index):
        """Delete an employee"""
        if index < 0 or index >= len(self.employees):
            return
        
        emp = self.employees[index]
        name = emp.get('name', 'Unknown')
        
        if messagebox.askyesno("Confirm Delete", 
                              f"Are you sure you want to delete '{name}'?"):
            self.employees.pop(index)
            
            if self._save_employees():
                if self.employee_list_container.winfo_ismapped():
                    self._refresh_employee_list()
                messagebox.showinfo("Success", f"Employee '{name}' deleted successfully!")
    
    def _build_action_buttons(self):
        """Build action buttons at bottom"""
        actions_frame = tk.Frame(self.content_frame, bg="white")
        actions_frame.pack(fill="x", pady=(20, 10))
        
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


if __name__ == "__main__":
    app = EmployeeMaintenanceApp()
    app.mainloop()
