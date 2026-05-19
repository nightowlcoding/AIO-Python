"""
Main Dashboard for Multi-Tenant Manager App
Shows company-specific features and management tools
"""
import tkinter as tk
from tkinter import ttk, messagebox
from session import get_session
from database import get_db
from app_config import create_button, COLORS, FONTS
import subprocess
import sys
import os


class DashboardApp(tk.Tk):
    """Main dashboard application"""
    
    def __init__(self):
        super().__init__()
        self.session = get_session()
        self.db = get_db()
        
        # Check if logged in
        if not self.session.is_logged_in():
            self.open_auth()
            return
        
        self.title(f"Manager App - {self.session.current_company_name}")
        self.geometry("900x700")
        self.configure(bg=COLORS['bg_primary'])
        
        self._build_ui()
    
    def _build_ui(self):
        """Build dashboard UI"""
        # Top bar
        top_bar = tk.Frame(self, bg=COLORS['primary'], height=70)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)
        
        # Company info
        company_frame = tk.Frame(top_bar, bg=COLORS['primary'])
        company_frame.pack(side="left", padx=20, pady=15)
        
        tk.Label(
            company_frame,
            text=self.session.current_company_name,
            font=FONTS['title'],
            bg=COLORS['primary'],
            fg="white"
        ).pack(anchor="w")
        
        role_text = self.session.current_role.replace('_', ' ').title()
        tk.Label(
            company_frame,
            text=f"{self.session.full_name} • {role_text}",
            font=FONTS['small'],
            bg=COLORS['primary'],
            fg="white"
        ).pack(anchor="w")
        
        # User menu
        user_frame = tk.Frame(top_bar, bg=COLORS['primary'])
        user_frame.pack(side="right", padx=20, pady=15)
        
        if len(self.session.companies) > 1:
            switch_btn = tk.Label(
                user_frame,
                text="🔄 Switch Company",
                font=FONTS['small_bold'],
                bg=COLORS['primary'],
                fg="white",
                cursor="hand2"
            )
            switch_btn.pack(side="left", padx=10)
            switch_btn.bind('<Button-1>', lambda e: self.switch_company())
        
        settings_btn = tk.Label(
            user_frame,
            text="⚙️ Settings",
            font=FONTS['small_bold'],
            bg=COLORS['primary'],
            fg="white",
            cursor="hand2"
        )
        settings_btn.pack(side="left", padx=10)
        settings_btn.bind('<Button-1>', lambda e: self.open_settings())
        
        logout_btn = tk.Label(
            user_frame,
            text="🚪 Logout",
            font=FONTS['small_bold'],
            bg=COLORS['primary'],
            fg="white",
            cursor="hand2"
        )
        logout_btn.pack(side="left", padx=10)
        logout_btn.bind('<Button-1>', lambda e: self.logout())
        
        # Main content
        content_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        content_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Quick actions
        tk.Label(
            content_frame,
            text="📊 Daily Operations",
            font=FONTS['subtitle'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(anchor="w", pady=(0, 15))
        
        operations_grid = tk.Frame(content_frame, bg=COLORS['bg_primary'])
        operations_grid.pack(fill="x", pady=(0, 30))
        
        # Row 1
        row1 = tk.Frame(operations_grid, bg=COLORS['bg_primary'])
        row1.pack(fill="x", pady=5)
        
        create_button(
            row1,
            "📝 Daily Log",
            lambda: self.open_app("dailylog.py"),
            style="primary",
            size="large"
        ).pack(side="left", fill="both", expand=True, padx=5)
        
        create_button(
            row1,
            "💰 Cash Manager",
            lambda: self.open_app("CashManager.py"),
            style="secondary",
            size="large"
        ).pack(side="left", fill="both", expand=True, padx=5)
        
        # Row 2
        row2 = tk.Frame(operations_grid, bg=COLORS['bg_primary'])
        row2.pack(fill="x", pady=5)
        
        create_button(
            row2,
            "📈 Reports",
            lambda: self.open_app("report.py"),
            style="accent",
            size="large"
        ).pack(side="left", fill="both", expand=True, padx=5)
        
        create_button(
            row2,
            "📥 Import Data",
            lambda: self.open_app("DLimport.py"),
            style="neutral",
            size="large"
        ).pack(side="left", fill="both", expand=True, padx=5)
        
        # Employee Management
        tk.Label(
            content_frame,
            text="👥 Employee Management",
            font=FONTS['subtitle'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(anchor="w", pady=(20, 15))
        
        employee_grid = tk.Frame(content_frame, bg=COLORS['bg_primary'])
        employee_grid.pack(fill="x", pady=(0, 30))
        
        create_button(
            employee_grid,
            "📋 Employee List",
            lambda: self.open_app("employee_maintenance.py"),
            style="secondary",
            size="large"
        ).pack(side="left", fill="both", expand=True, padx=5)
        
        create_button(
            employee_grid,
            "🎯 Employee Grading",
            lambda: self.open_app("../employeegrading_gui.py"),
            style="accent",
            size="large"
        ).pack(side="left", fill="both", expand=True, padx=5)
        
        # Admin section (only for business admin)
        if self.session.is_business_admin():
            tk.Label(
                content_frame,
                text="🔧 Business Administration",
                font=FONTS['subtitle'],
                bg=COLORS['bg_primary'],
                fg=COLORS['text']
            ).pack(anchor="w", pady=(20, 15))
            
            admin_grid = tk.Frame(content_frame, bg=COLORS['bg_primary'])
            admin_grid.pack(fill="x")
            
            admin_row1 = tk.Frame(admin_grid, bg=COLORS['bg_primary'])
            admin_row1.pack(fill="x", pady=5)
            
            create_button(
                admin_row1,
                "🏢 Company Settings",
                self.open_company_settings,
                style="primary",
                size="large"
            ).pack(side="left", fill="both", expand=True, padx=5)
            
            create_button(
                admin_row1,
                "👤 User Management",
                self.open_user_management,
                style="secondary",
                size="large"
            ).pack(side="left", fill="both", expand=True, padx=5)
            
            admin_row2 = tk.Frame(admin_grid, bg=COLORS['bg_primary'])
            admin_row2.pack(fill="x", pady=5)
            
            create_button(
                admin_row2,
                "📍 Locations",
                self.open_locations,
                style="accent",
                size="large"
            ).pack(side="left", fill="both", expand=True, padx=5)
            
            create_button(
                admin_row2,
                "📊 Audit Log",
                self.open_audit_log,
                style="neutral",
                size="large"
            ).pack(side="left", fill="both", expand=True, padx=5)
    
    def open_app(self, app_file):
        """Open an application"""
        app_path = os.path.join(os.path.dirname(__file__), app_file)
        if os.path.exists(app_path):
            subprocess.Popen([sys.executable, app_path])
        else:
            messagebox.showerror("Error", f"Application not found: {app_file}")
    
    def open_company_settings(self):
        """Open company settings"""
        CompanySettingsWindow(self)
    
    def open_user_management(self):
        """Open user management"""
        UserManagementWindow(self)
    
    def open_locations(self):
        """Open locations management"""
        LocationsWindow(self)
    
    def open_audit_log(self):
        """Open audit log"""
        AuditLogWindow(self)
    
    def open_settings(self):
        """Open user settings"""
        messagebox.showinfo("Settings", "User settings coming soon!")
    
    def switch_company(self):
        """Switch to different company"""
        self.destroy()
        auth_path = os.path.join(os.path.dirname(__file__), "auth.py")
        subprocess.Popen([sys.executable, auth_path])
    
    def logout(self):
        """Logout user"""
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.db.log_action(self.session.user_id, 'logout', self.session.current_company_id)
            self.session.logout()
            self.destroy()
            self.open_auth()
    
    def open_auth(self):
        """Open authentication"""
        self.destroy()
        auth_path = os.path.join(os.path.dirname(__file__), "auth.py")
        subprocess.Popen([sys.executable, auth_path])


class CompanySettingsWindow(tk.Toplevel):
    """Company settings window"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.session = get_session()
        self.db = get_db()
        
        self.title("Company Settings")
        self.geometry("600x650")
        self.configure(bg=COLORS['bg_primary'])
        
        company = self.db.get_company(self.session.current_company_id)
        
        # Header
        header = tk.Frame(self, bg=COLORS['primary'], height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🏢 Company Settings",
            font=FONTS['title'],
            bg=COLORS['primary'],
            fg="white"
        ).pack(pady=15)
        
        # Scrollable content
        canvas = tk.Canvas(self, bg=COLORS['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=COLORS['bg_primary'])
        
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=560)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")
        
        # Form fields
        self.name_var = tk.StringVar(value=company['name'])
        self.address_var = tk.StringVar(value=company['address'] or "")
        self.phone_var = tk.StringVar(value=company['phone'] or "")
        self.email_var = tk.StringVar(value=company['email'] or "")
        self.website_var = tk.StringVar(value=company['website'] or "")
        self.tax_id_var = tk.StringVar(value=company['tax_id'] or "")
        
        fields = [
            ("Company Name", self.name_var),
            ("Address", self.address_var),
            ("Phone", self.phone_var),
            ("Email", self.email_var),
            ("Website", self.website_var),
            ("Tax ID / EIN", self.tax_id_var)
        ]
        
        for label, var in fields:
            tk.Label(
                content,
                text=label,
                font=FONTS['label'],
                bg=COLORS['bg_primary'],
                fg=COLORS['text']
            ).pack(anchor="w", pady=(15, 5))
            
            entry = tk.Entry(
                content,
                textvariable=var,
                font=FONTS['entry'],
                bd=2,
                relief="solid"
            )
            entry.pack(fill="x", ipady=8)
        
        # Buttons
        btn_frame = tk.Frame(content, bg=COLORS['bg_primary'])
        btn_frame.pack(fill="x", pady=30)
        
        create_button(
            btn_frame,
            "💾 Save Changes",
            self.save_changes,
            style="primary"
        ).pack(fill="x", pady=5)
        
        create_button(
            btn_frame,
            "Cancel",
            self.destroy,
            style="neutral"
        ).pack(fill="x", pady=5)
    
    def save_changes(self):
        """Save company changes"""
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showwarning("Input Error", "Company name is required")
            return
        
        self.db.update_company(
            self.session.current_company_id,
            name=name,
            address=self.address_var.get().strip(),
            phone=self.phone_var.get().strip(),
            email=self.email_var.get().strip(),
            website=self.website_var.get().strip(),
            tax_id=self.tax_id_var.get().strip()
        )
        
        self.db.log_action(
            self.session.user_id,
            'company_updated',
            self.session.current_company_id,
            {'changes': 'company_info'}
        )
        
        # Update session
        self.session.current_company_name = name
        self.session.save()
        
        messagebox.showinfo("Success", "Company settings saved successfully!")
        self.destroy()
        
        # Refresh parent
        self.master.destroy()
        DashboardApp().mainloop()


class UserManagementWindow(tk.Toplevel):
    """User management window"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.session = get_session()
        self.db = get_db()
        
        self.title("User Management")
        self.geometry("800x600")
        self.configure(bg=COLORS['bg_primary'])
        
        self._build_ui()
    
    def _build_ui(self):
        """Build UI"""
        # Header
        header = tk.Frame(self, bg=COLORS['secondary'], height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="👤 User Management",
            font=FONTS['title'],
            bg=COLORS['secondary'],
            fg="white"
        ).pack(side="left", padx=20, pady=15)
        
        create_button(
            header,
            "➕ Add User",
            self.add_user,
            style="neutral",
            size="small"
        ).pack(side="right", padx=20)
        
        # Users list
        list_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        list_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Table
        columns = ("Name", "Username", "Email", "Role", "Status")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Load users
        users = self.db.get_company_users(self.session.current_company_id)
        
        for user in users:
            role_text = user['role'].replace('_', ' ').title()
            status = "Active" if user['is_active'] else "Inactive"
            
            tree.insert("", "end", values=(
                user['full_name'] or user['username'],
                user['username'],
                user['email'],
                role_text,
                status
            ))
        
        # Context menu
        tree.bind('<Double-Button-1>', lambda e: self.edit_user(tree))
    
    def add_user(self):
        """Add new user (placeholder)"""
        messagebox.showinfo("Add User", "Add user functionality coming soon!")
    
    def edit_user(self, tree):
        """Edit user (placeholder)"""
        messagebox.showinfo("Edit User", "Edit user functionality coming soon!")


class LocationsWindow(tk.Toplevel):
    """Locations management window"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.session = get_session()
        self.db = get_db()
        
        self.title("Locations")
        self.geometry("700x500")
        self.configure(bg=COLORS['bg_primary'])
        
        messagebox.showinfo("Locations", "Multi-location support coming soon!")
        self.destroy()


class AuditLogWindow(tk.Toplevel):
    """Audit log window"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.session = get_session()
        self.db = get_db()
        
        self.title("Audit Log")
        self.geometry("900x600")
        self.configure(bg=COLORS['bg_primary'])
        
        messagebox.showinfo("Audit Log", "Audit log viewer coming soon!")
        self.destroy()


if __name__ == "__main__":
    app = DashboardApp()
    app.mainloop()
