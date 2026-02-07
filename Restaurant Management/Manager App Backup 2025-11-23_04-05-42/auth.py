"""
Authentication and Registration System
Multi-tenant login with company selection
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from database import get_db
from session import get_session
from app_config import create_button, COLORS, FONTS
from legal import TermsWindow, PrivacyWindow
import os
from PIL import Image, ImageTk
import subprocess
import sys


class AuthApp(tk.Tk):
    """Authentication application"""
    
    def __init__(self):
        super().__init__()
        self.title("Manager App - Login")
        self.geometry("450x600")
        self.configure(bg=COLORS['bg_primary'])
        self.resizable(False, False)
        
        self.db = get_db()
        self.session = get_session()
        
        # Check if session expired
        if self.session.user_id and not self.session.is_logged_in():
            messagebox.showinfo(
                "Session Expired",
                "Your session has expired due to inactivity.\n\nPlease log in again."
            )
            self.session.logout()
        
        # Check if already logged in
        if self.session.is_logged_in():
            self.open_dashboard()
            return
        
        self.show_login_screen()
    
    def show_login_screen(self):
        """Show login form"""
        # Clear window
        for widget in self.winfo_children():
            widget.destroy()
        
        # Header
        header_frame = tk.Frame(self, bg=COLORS['primary'], height=100)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="🏢 Manager App",
            font=('Arial', 24, 'bold'),
            bg=COLORS['primary'],
            fg="white"
        ).pack(pady=30)
        
        # Main container
        main_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        main_frame.pack(fill="both", expand=True, padx=40, pady=40)
        
        tk.Label(
            main_frame,
            text="Sign In",
            font=FONTS['title'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(pady=(0, 20))
        
        # Username
        tk.Label(
            main_frame,
            text="Username",
            font=FONTS['label'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(anchor="w", pady=(10, 5))
        
        self.username_var = tk.StringVar()
        username_entry = tk.Entry(
            main_frame,
            textvariable=self.username_var,
            font=FONTS['entry'],
            bd=2,
            relief="solid"
        )
        username_entry.pack(fill="x", ipady=8)
        username_entry.focus()
        
        # Password
        tk.Label(
            main_frame,
            text="Password",
            font=FONTS['label'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(anchor="w", pady=(15, 5))
        
        self.password_var = tk.StringVar()
        password_entry = tk.Entry(
            main_frame,
            textvariable=self.password_var,
            font=FONTS['entry'],
            show="●",
            bd=2,
            relief="solid"
        )
        password_entry.pack(fill="x", ipady=8)
        password_entry.bind('<Return>', lambda e: self.login())
        
        # Login button
        create_button(
            main_frame,
            "Sign In",
            self.login,
            style="primary"
        ).pack(fill="x", pady=(30, 10))
        
        # Register link
        register_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        register_frame.pack(pady=10)
        
        tk.Label(
            register_frame,
            text="Don't have an account?",
            font=FONTS['small'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary']
        ).pack(side="left", padx=5)
        
        register_btn = tk.Label(
            register_frame,
            text="Register Here",
            font=FONTS['small_bold'],
            bg=COLORS['bg_primary'],
            fg=COLORS['primary'],
            cursor="hand2"
        )
        register_btn.pack(side="left")
        register_btn.bind('<Button-1>', lambda e: self.show_registration_screen())
    
    def login(self):
        """Handle login"""
        username = self.username_var.get().strip()
        password = self.password_var.get()
        
        if not username or not password:
            messagebox.showwarning("Input Error", "Please enter username and password")
            return
        
        user = self.db.authenticate_user(username, password)
        
        if user:
            companies = self.db.get_user_companies(user['id'])
            
            if not companies:
                messagebox.showinfo(
                    "No Companies",
                    "You don't have access to any companies yet.\n\n"
                    "Please contact a business admin or create a company."
                )
                self.show_company_setup(user)
                return
            
            self.session.login(user, companies)
            self.db.log_action(user['id'], 'login')
            
            if len(companies) > 1:
                self.show_company_selector()
            else:
                self.open_dashboard()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")
    
    def show_registration_screen(self):
        """Show registration form"""
        # Clear window
        for widget in self.winfo_children():
            widget.destroy()
        
        # Header
        header_frame = tk.Frame(self, bg=COLORS['primary'], height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="Create Account",
            font=FONTS['header'],
            bg=COLORS['primary'],
            fg="white"
        ).pack(pady=25)
        
        # Main container with scrollbar
        canvas = tk.Canvas(self, bg=COLORS['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        main_frame = tk.Frame(canvas, bg=COLORS['bg_primary'])
        
        main_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=main_frame, anchor="nw", width=410)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")
        
        # Form fields
        self.reg_username_var = tk.StringVar()
        self.reg_email_var = tk.StringVar()
        self.reg_password_var = tk.StringVar()
        self.reg_confirm_var = tk.StringVar()
        self.reg_fullname_var = tk.StringVar()
        self.reg_phone_var = tk.StringVar()
        
        fields = [
            ("Full Name", self.reg_fullname_var, False),
            ("Username *", self.reg_username_var, False),
            ("Email *", self.reg_email_var, False),
            ("Phone", self.reg_phone_var, False),
            ("Password *", self.reg_password_var, True),
            ("Confirm Password *", self.reg_confirm_var, True)
        ]
        
        for label, var, is_password in fields:
            tk.Label(
                main_frame,
                text=label,
                font=FONTS['label'],
                bg=COLORS['bg_primary'],
                fg=COLORS['text']
            ).pack(anchor="w", pady=(10, 5))
            
            entry = tk.Entry(
                main_frame,
                textvariable=var,
                font=FONTS['entry'],
                show="●" if is_password else "",
                bd=2,
                relief="solid"
            )
            entry.pack(fill="x", ipady=8)
        
        # Register button
        create_button(
            main_frame,
            "Create Account",
            self.register,
            style="secondary"
        ).pack(fill="x", pady=(30, 10))
        
        # Terms notice
        terms_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        terms_frame.pack(pady=10)
        
        tk.Label(
            terms_frame,
            text="By creating an account, you agree to our",
            font=FONTS['small'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary']
        ).pack()
        
        links_frame = tk.Frame(terms_frame, bg=COLORS['bg_primary'])
        links_frame.pack()
        
        terms_link = tk.Label(
            links_frame,
            text="Terms of Service",
            font=FONTS['small_bold'],
            bg=COLORS['bg_primary'],
            fg=COLORS['primary'],
            cursor="hand2"
        )
        terms_link.pack(side="left")
        terms_link.bind('<Button-1>', lambda e: TermsWindow(self))
        
        tk.Label(
            links_frame,
            text=" and ",
            font=FONTS['small'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary']
        ).pack(side="left")
        
        privacy_link = tk.Label(
            links_frame,
            text="Privacy Policy",
            font=FONTS['small_bold'],
            bg=COLORS['bg_primary'],
            fg=COLORS['primary'],
            cursor="hand2"
        )
        privacy_link.pack(side="left")
        privacy_link.bind('<Button-1>', lambda e: PrivacyWindow(self))
        
        # Back to login
        back_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        back_frame.pack(pady=10)
        
        back_btn = tk.Label(
            back_frame,
            text="← Back to Login",
            font=FONTS['small_bold'],
            bg=COLORS['bg_primary'],
            fg=COLORS['primary'],
            cursor="hand2"
        )
        back_btn.pack()
        back_btn.bind('<Button-1>', lambda e: self.show_login_screen())
    
    def register(self):
        """Handle registration"""
        from security import InputValidator
        
        username = self.reg_username_var.get().strip()
        email = self.reg_email_var.get().strip()
        password = self.reg_password_var.get()
        confirm = self.reg_confirm_var.get()
        full_name = self.reg_fullname_var.get().strip()
        
        # Validation
        if not username or not email or not password:
            messagebox.showwarning("Input Error", "Please fill in all required fields (*)")
            return
        
        if len(username) < 3:
            messagebox.showwarning("Input Error", "Username must be at least 3 characters")
            return
        
        # Validate email
        validator = InputValidator()
        if not validator.validate_email(email):
            messagebox.showwarning("Input Error", "Please enter a valid email address")
            return
        
        # Validate password strength
        password_check = validator.validate_password_strength(password)
        if not password_check['valid']:
            missing = ', '.join(password_check['missing'])
            messagebox.showwarning(
                "Weak Password",
                f"Password must have:\n\n{missing}\n\n"
                "For your security, please create a stronger password."
            )
            return
        
        if password != confirm:
            messagebox.showwarning("Input Error", "Passwords do not match")
            return
        
        # Create user
        try:
            user_id, verification_token = self.db.create_user(username, email, password, full_name)
            
            if user_id:
                messagebox.showinfo(
                    "Success",
                    "Account created successfully!\n\n"
                    "You can now set up your company."
                )
                
                # Authenticate and setup company
                user = self.db.authenticate_user(username, password)
                
                # Show terms acceptance
                self.show_terms_acceptance(user, is_registration=True)
            else:
                messagebox.showerror(
                    "Registration Failed",
                    "Username or email already exists.\nPlease try different credentials."
                )
        except ValueError as e:
            messagebox.showerror("Registration Failed", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
    
    def show_company_setup(self, user):
        """Show company setup screen"""
        # Clear window
        for widget in self.winfo_children():
            widget.destroy()
        
        self.geometry("550x700")
        
        # Header
        header_frame = tk.Frame(self, bg=COLORS['secondary'], height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="🏢 Set Up Your Company",
            font=FONTS['header'],
            bg=COLORS['secondary'],
            fg="white"
        ).pack(pady=25)
        
        # Main container with scrollbar
        canvas = tk.Canvas(self, bg=COLORS['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        main_frame = tk.Frame(canvas, bg=COLORS['bg_primary'])
        
        main_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=main_frame, anchor="nw", width=510)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")
        
        # Store user for later
        self.setup_user = user
        
        # Form fields
        self.company_name_var = tk.StringVar()
        self.company_address_var = tk.StringVar()
        self.company_phone_var = tk.StringVar()
        self.company_email_var = tk.StringVar()
        self.company_website_var = tk.StringVar()
        self.company_tax_id_var = tk.StringVar()
        self.company_logo_var = tk.StringVar()
        
        # Logo upload
        logo_frame = tk.Frame(main_frame, bg=COLORS['bg_secondary'], relief="solid", bd=1)
        logo_frame.pack(fill="x", pady=(0, 20), padx=20, ipady=20)
        
        tk.Label(
            logo_frame,
            text="Company Logo (Optional)",
            font=FONTS['label'],
            bg=COLORS['bg_secondary'],
            fg=COLORS['text']
        ).pack(pady=5)
        
        create_button(
            logo_frame,
            "📁 Choose Logo",
            self.choose_logo,
            style="neutral",
            size="small"
        ).pack(pady=5)
        
        self.logo_label = tk.Label(
            logo_frame,
            text="No logo selected",
            font=FONTS['small'],
            bg=COLORS['bg_secondary'],
            fg=COLORS['text_light']
        )
        self.logo_label.pack(pady=5)
        
        # Company info
        fields = [
            ("Company Name *", self.company_name_var),
            ("Address", self.company_address_var),
            ("Phone", self.company_phone_var),
            ("Email", self.company_email_var),
            ("Website", self.company_website_var),
            ("Tax ID / EIN", self.company_tax_id_var)
        ]
        
        for label, var in fields:
            tk.Label(
                main_frame,
                text=label,
                font=FONTS['label'],
                bg=COLORS['bg_primary'],
                fg=COLORS['text']
            ).pack(anchor="w", pady=(10, 5), padx=20)
            
            entry = tk.Entry(
                main_frame,
                textvariable=var,
                font=FONTS['entry'],
                bd=2,
                relief="solid"
            )
            entry.pack(fill="x", ipady=8, padx=20)
        
        # Buttons
        btn_frame = tk.Frame(main_frame, bg=COLORS['bg_primary'])
        btn_frame.pack(fill="x", pady=(30, 10), padx=20)
        
        create_button(
            btn_frame,
            "Create Company",
            self.create_company,
            style="secondary"
        ).pack(fill="x", pady=5)
        
        create_button(
            btn_frame,
            "Skip for Now",
            lambda: self.show_login_screen(),
            style="neutral"
        ).pack(fill="x", pady=5)
    
    def choose_logo(self):
        """Choose company logo"""
        filename = filedialog.askopenfilename(
            title="Select Company Logo",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("All files", "*.*")
            ]
        )
        
        if filename:
            self.company_logo_var.set(filename)
            self.logo_label.config(text=f"Selected: {os.path.basename(filename)}")
    
    def create_company(self):
        """Create company"""
        name = self.company_name_var.get().strip()
        
        if not name:
            messagebox.showwarning("Input Error", "Please enter a company name")
            return
        
        company_id = self.db.create_company(
            name=name,
            admin_user_id=self.setup_user['id'],
            logo_path=self.company_logo_var.get(),
            address=self.company_address_var.get().strip(),
            phone=self.company_phone_var.get().strip(),
            email=self.company_email_var.get().strip(),
            website=self.company_website_var.get().strip(),
            tax_id=self.company_tax_id_var.get().strip()
        )
        
        if company_id:
            self.db.log_action(
                self.setup_user['id'],
                'company_created',
                company_id,
                {'company_name': name}
            )
            
            messagebox.showinfo(
                "Success",
                f"Company '{name}' created successfully!\n\n"
                "You are now the Business Admin."
            )
            
            # Login with new company
            companies = self.db.get_user_companies(self.setup_user['id'])
            self.session.login(self.setup_user, companies)
            self.open_dashboard()
        else:
            messagebox.showerror(
                "Error",
                "Company name already exists.\nPlease choose a different name."
            )
    
    def show_company_selector(self):
        """Show company selector for users with multiple companies"""
        # Clear window
        for widget in self.winfo_children():
            widget.destroy()
        
        self.geometry("450x500")
        
        # Header
        header_frame = tk.Frame(self, bg=COLORS['primary'], height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="Select Company",
            font=FONTS['header'],
            bg=COLORS['primary'],
            fg="white"
        ).pack(pady=25)
        
        # Main container
        main_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        main_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        tk.Label(
            main_frame,
            text=f"Welcome, {self.session.full_name}!",
            font=FONTS['subtitle'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text']
        ).pack(pady=(0, 20))
        
        tk.Label(
            main_frame,
            text="Choose a company to continue:",
            font=FONTS['label'],
            bg=COLORS['bg_primary'],
            fg=COLORS['text_secondary']
        ).pack(pady=(0, 15))
        
        # Company list
        for company in self.session.companies:
            company_frame = tk.Frame(
                main_frame,
                bg="white",
                relief="solid",
                bd=1,
                cursor="hand2"
            )
            company_frame.pack(fill="x", pady=5)
            
            # Make clickable
            company_frame.bind(
                '<Button-1>',
                lambda e, c_id=company['id']: self.select_company(c_id)
            )
            
            content = tk.Frame(company_frame, bg="white")
            content.pack(fill="x", padx=15, pady=15)
            
            tk.Label(
                content,
                text=company['name'],
                font=FONTS['body_bold'],
                bg="white",
                fg=COLORS['text']
            ).pack(anchor="w")
            
            role_text = company['role'].replace('_', ' ').title()
            tk.Label(
                content,
                text=f"Role: {role_text}",
                font=FONTS['small'],
                bg="white",
                fg=COLORS['text_light']
            ).pack(anchor="w")
            
            # Bind hover effects
            for widget in [company_frame, content]:
                widget.bind('<Enter>', lambda e, f=company_frame: f.config(bg=COLORS['bg_secondary']))
                widget.bind('<Leave>', lambda e, f=company_frame: f.config(bg="white"))
    
    def select_company(self, company_id):
        """Select company and open dashboard"""
        self.session.select_company(company_id)
        self.open_dashboard()
    
    def open_dashboard(self, show_onboarding=False):
        """Open main dashboard"""
        # Show onboarding if first login
        if show_onboarding:
            from onboarding import show_onboarding
            show_onboarding(self, self.session.current_company_name, self.session.full_name)
        
        self.destroy()
        
        # Launch main dashboard
        dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
        subprocess.Popen([sys.executable, dashboard_path])


if __name__ == "__main__":
    app = AuthApp()
    app.mainloop()
