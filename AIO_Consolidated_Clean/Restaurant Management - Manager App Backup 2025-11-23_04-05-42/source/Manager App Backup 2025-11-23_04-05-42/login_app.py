import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Scrollbar
from PIL import Image, ImageTk
import json
import os
import hashlib
from datetime import datetime
import subprocess
import sys
from app_config import create_button, create_header, COLORS, FONTS

# File to store user data
USER_DATA_FILE = os.path.expanduser("~/Documents/AIO Python/users.json")


class ModernLoginApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Login System")
        self.geometry("360x800")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)
        
        # Initialize user database
        self._init_user_db()
        
        # Container for switching between pages
        self.container = tk.Frame(self, bg="#f0f0f0")
        self.container.pack(fill="both", expand=True)
        
        # Configure grid layout
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        # Dictionary to hold all frames
        self.frames = {}
        
        # Create all pages
        for F in (LoginPage, SignUpPage, DashboardPage, AccountPage):
            frame = F(self.container, self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")
        
        # Show login page first
        self.show_frame("LoginPage")
        
        # Center window on screen
        self.center_window()
    
    def _init_user_db(self):
        """Initialize user database file if it doesn't exist"""
        if not os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'w') as f:
                json.dump({}, f)
    
    def center_window(self):
        """Center the window on screen"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def show_frame(self, page_name):
        """Show a frame for the given page name"""
        frame = self.frames[page_name]
        frame.tkraise()
    
    def hash_password(self, password):
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def load_users(self):
        """Load users from JSON file"""
        try:
            with open(USER_DATA_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load user data: {e}")
            return {}
    
    def save_users(self, users):
        """Save users to JSON file"""
        try:
            with open(USER_DATA_FILE, 'w') as f:
                json.dump(users, f, indent=4)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save user data: {e}")
            return False
    
    def register_user(self, username, email, password):
        """Register a new user"""
        users = self.load_users()
        
        # Check if username already exists
        if username in users:
            return False, "Username already exists"
        
        # Check if email already exists
        for user, data in users.items():
            if data.get('email') == email:
                return False, "Email already registered"
        
        # Create new user
        users[username] = {
            'email': email,
            'password': self.hash_password(password),
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'last_login': None
        }
        
        if self.save_users(users):
            return True, "Registration successful"
        return False, "Failed to save user data"
    
    def authenticate_user(self, username, password):
        """Authenticate a user"""
        users = self.load_users()
        
        if username not in users:
            return False, "Username not found"
        
        if users[username]['password'] != self.hash_password(password):
            return False, "Incorrect password"
        
        # Update last login
        users[username]['last_login'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_users(users)
        
        return True, "Login successful"


class LoginPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#f0f0f0")
        self.controller = controller
        
        # Main container
        main_frame = tk.Frame(self, bg="white", relief="flat", bd=0)
        main_frame.place(relx=0.5, rely=0.5, anchor="center", width=360, height=640)
        
        # Add shadow effect (simulated with multiple frames)
        shadow = tk.Frame(self, bg="#d0d0d0")
        shadow.place(relx=0.5, rely=0.505, anchor="center", width=385, height=485)
        main_frame.lift()
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#2c2c2c", height=140)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        # Logo
        try:
            logo_path = '/Users/arnoldoramirezjr/Documents/AIO Python/Manager App/Night Owl Logo.png'
            logo_image = Image.open(logo_path)
            logo_image = logo_image.resize((120, 120), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(logo_image)
            tk.Label(header_frame, image=self.logo_photo, bg="#2c2c2c").pack(pady=10)
        except Exception as e:
            print(f"Logo loading error: {e}")
        
        # Content area
        content_frame = tk.Frame(main_frame, bg="white")
        content_frame.pack(fill="both", expand=True, padx=40, pady=30)
        
        # Username
        tk.Label(content_frame, text="Username", font=("Helvetica", 11),
                bg="white", fg="black").pack(anchor="w", pady=(10, 5))
        
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(content_frame, textvariable=self.username_var,
                                   font=("Helvetica", 11))
        username_entry.pack(fill="x", ipady=8)
        
        # Password
        tk.Label(content_frame, text="Password", font=("Helvetica", 11),
                bg="white", fg="black").pack(anchor="w", pady=(20, 5))
        
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(content_frame, textvariable=self.password_var,
                                   show="•", font=("Helvetica", 11))
        password_entry.pack(fill="x", ipady=8)
        
        # Bind Enter key to login
        password_entry.bind('<Return>', lambda e: self.login())
        
        # Remember me checkbox
        self.remember_var = tk.BooleanVar()
        tk.Checkbutton(content_frame, text="Remember me", variable=self.remember_var,
                      bg="white", fg="black", font=("Helvetica", 10),
                      activebackground="white").pack(anchor="w", pady=(10, 1))
        
        # Login button
        login_btn = tk.Button(content_frame, text="Login", command=self.login,
                             bg="#3a3a3a", fg="black",
                             activebackground="#1a1a1a", activeforeground="black",
                             font=("Helvetica", 12, "bold"),
                             relief="flat", cursor="hand2", height=2)
        login_btn.pack(fill="x", pady=(25, 10))
        
        # Hover effects
        login_btn.bind("<Enter>", lambda e: login_btn.config(bg="#4a4a4a"))
        login_btn.bind("<Leave>", lambda e: login_btn.config(bg="#3a3a3a"))
        
        # Sign up link
        signup_frame = tk.Frame(content_frame, bg="white")
        signup_frame.pack(pady=(15, 0))
        
        tk.Label(signup_frame, text="Don't have an account?",
                bg="white", fg="black", font=("Helvetica", 10)).pack(side="left")
        
        signup_link = tk.Label(signup_frame, text="Sign Up",
                              bg="white", fg="black", font=("Helvetica", 10, "bold"),
                              cursor="hand2")
        signup_link.pack(side="left", padx=(5, 0))
        signup_link.bind("<Button-1>", lambda e: controller.show_frame("SignUpPage"))
        
        # Underline on hover
        signup_link.bind("<Enter>", lambda e: signup_link.config(font=("Helvetica", 10, "bold", "underline")))
        signup_link.bind("<Leave>", lambda e: signup_link.config(font=("Helvetica", 10, "bold")))
    
    def login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        
        if not username or not password:
            messagebox.showwarning("Missing Information", "Please enter both username and password")
            return
        
        success, message = self.controller.authenticate_user(username, password)
        
        if success:
            # Clear password field
            self.password_var.set("")
            # Show dashboard
            dashboard = self.controller.frames["DashboardPage"]
            dashboard.set_user(username)
            self.controller.show_frame("DashboardPage")
        else:
            messagebox.showerror("Login Failed", message)
            self.password_var.set("")


class SignUpPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#f0f0f0")
        self.controller = controller
        
        # Main container
        main_frame = tk.Frame(self, bg="white", relief="flat", bd=0)
        main_frame.place(relx=0.5, rely=0.5, anchor="center", width=380, height=520)
        
        # Add shadow effect
        shadow = tk.Frame(self, bg="#d0d0d0")
        shadow.place(relx=0.5, rely=0.505, anchor="center", width=385, height=525)
        main_frame.lift()
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#3d3d3d", height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="Create Account", font=("Helvetica", 24, "bold"),
                bg="#3d3d3d", fg="black").pack(pady=20)
        
        # Content area
        content_frame = tk.Frame(main_frame, bg="white")
        content_frame.pack(fill="both", expand=True, padx=40, pady=30)
        
        # Username
        tk.Label(content_frame, text="Username", font=("Helvetica", 11),
                bg="white", fg="black").pack(anchor="w", pady=(5, 5))
        
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(content_frame, textvariable=self.username_var,
                                   font=("Helvetica", 11))
        username_entry.pack(fill="x", ipady=8)
        
        # Email
        tk.Label(content_frame, text="Email", font=("Helvetica", 11),
                bg="white", fg="black").pack(anchor="w", pady=(15, 5))
        
        self.email_var = tk.StringVar()
        email_entry = ttk.Entry(content_frame, textvariable=self.email_var,
                               font=("Helvetica", 11))
        email_entry.pack(fill="x", ipady=8)
        
        # Password
        tk.Label(content_frame, text="Password", font=("Helvetica", 11),
                bg="white", fg="black").pack(anchor="w", pady=(15, 5))
        
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(content_frame, textvariable=self.password_var,
                                   show="•", font=("Helvetica", 11))
        password_entry.pack(fill="x", ipady=8)
        
        # Confirm Password
        tk.Label(content_frame, text="Confirm Password", font=("Helvetica", 11),
                bg="white", fg="black").pack(anchor="w", pady=(15, 5))
        
        self.confirm_password_var = tk.StringVar()
        confirm_entry = ttk.Entry(content_frame, textvariable=self.confirm_password_var,
                                 show="•", font=("Helvetica", 11))
        confirm_entry.pack(fill="x", ipady=8)
        
        # Bind Enter key to signup
        confirm_entry.bind('<Return>', lambda e: self.signup())
        
        # Sign up button
        signup_btn = tk.Button(content_frame, text="Sign Up", command=self.signup,
                              bg="#3a3a3a", fg="black",
                              activebackground="#1a1a1a", activeforeground="black",
                              font=("Helvetica", 12, "bold"),
                              relief="flat", cursor="hand2", height=2)
        signup_btn.pack(fill="x", pady=(20, 10))
        
        # Hover effects
        signup_btn.bind("<Enter>", lambda e: signup_btn.config(bg="#4a4a4a"))
        signup_btn.bind("<Leave>", lambda e: signup_btn.config(bg="#3a3a3a"))
        
        # Login link
        login_frame = tk.Frame(content_frame, bg="white")
        login_frame.pack(pady=(15, 0))
        
        tk.Label(login_frame, text="Already have an account?",
                bg="white", fg="black", font=("Helvetica", 10)).pack(side="left")
        
        login_link = tk.Label(login_frame, text="Login",
                             bg="white", fg="black", font=("Helvetica", 10, "bold"),
                             cursor="hand2")
        login_link.pack(side="left", padx=(5, 0))
        login_link.bind("<Button-1>", lambda e: controller.show_frame("LoginPage"))
        
        # Underline on hover
        login_link.bind("<Enter>", lambda e: login_link.config(font=("Helvetica", 10, "bold", "underline")))
        login_link.bind("<Leave>", lambda e: login_link.config(font=("Helvetica", 10, "bold")))
    
    def signup(self):
        username = self.username_var.get().strip()
        email = self.email_var.get().strip()
        password = self.password_var.get()
        confirm_password = self.confirm_password_var.get()
        
        # Validation
        if not username or not email or not password:
            messagebox.showwarning("Missing Information", "Please fill in all fields")
            return
        
        if len(username) < 3:
            messagebox.showwarning("Invalid Username", "Username must be at least 3 characters long")
            return
        
        if "@" not in email or "." not in email:
            messagebox.showwarning("Invalid Email", "Please enter a valid email address")
            return
        
        if len(password) < 6:
            messagebox.showwarning("Weak Password", "Password must be at least 6 characters long")
            return
        
        if password != confirm_password:
            messagebox.showerror("Password Mismatch", "Passwords do not match")
            return
        
        # Register user
        success, message = self.controller.register_user(username, email, password)
        
        if success:
            messagebox.showinfo("Success", "Account created successfully!\nYou can now login.")
            # Clear fields
            self.username_var.set("")
            self.email_var.set("")
            self.password_var.set("")
            self.confirm_password_var.set("")
            # Go to login page
            self.controller.show_frame("LoginPage")
        else:
            messagebox.showerror("Registration Failed", message)


class DashboardPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#f0f0f0")
        self.controller = controller
        self.current_user = None
        
        # Main container
        main_frame = tk.Frame(self, bg="white", relief="flat", bd=0)
        main_frame.place(relx=0.5, rely=0.5, anchor="center", width=380, height=750)
        
        # Add shadow effect
        shadow = tk.Frame(self, bg="#d0d0d0")
        shadow.place(relx=0.5, rely=0.505, anchor="center", width=385, height=755)
        main_frame.lift()
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#2c2c2c", height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        self.header_welcome_label = tk.Label(header_frame, text="Welcome!", font=("Helvetica", 24, "bold"),
                bg="#2c2c2c", fg="black")
        self.header_welcome_label.pack(pady=20)
        
        # Content area with scrollbar
        canvas_frame = tk.Frame(main_frame, bg="white")
        canvas_frame.pack(fill="both", expand=True)
        
        canvas = Canvas(canvas_frame, bg="white", highlightthickness=0)
        scrollbar = Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        content_frame = tk.Frame(canvas, bg="white")
        
        content_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=content_frame, anchor="nw", width=300)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y", pady=20, padx=(0, 5))
        
        # Quick actions section
        actions_label = tk.Label(content_frame, text="Pick task",
                                font=("Helvetica", 16, "bold"),
                                bg="white", fg="black")
        actions_label.pack(pady=(20, 15))
        
        # Center frame for buttons
        center_frame = tk.Frame(content_frame, bg="white")
        center_frame.pack(pady=10)
        
        # Action buttons
        actions_grid = tk.Frame(center_frame, bg="white")
        actions_grid.pack()
        
        action_buttons = [
            ("📊 Daily Log", self.open_daily_log, 'primary'),
            ("📈 Reports", self.open_reports, 'accent'),
            ("👥 Employee", self.open_employee_maintenance, 'secondary')
        ]
        
        for i, (text, cmd, style) in enumerate(action_buttons):
            btn = create_button(actions_grid, text, cmd, style=style, size='large')
            btn.grid(row=i, column=0, padx=2, pady=8)
        
        # Account button
        account_btn = create_button(content_frame, "👤 Account", self.open_account, 
                                    style='neutral', size='large')
        account_btn.pack(pady=(30, 10), padx=2)
        
        # Account information section
        account_info_frame = tk.Frame(content_frame, bg="#f5f5f5", relief="solid", bd=1)
        account_info_frame.pack(fill="x", pady=10, padx=2)
        
        tk.Label(account_info_frame, text="Account Information",
                font=("Helvetica", 12, "bold"),
                bg="#f5f5f5", fg="black").pack(pady=(10, 5))
        
        self.account_username_label = tk.Label(account_info_frame, text="", font=("Helvetica", 10),
                                              bg="#f5f5f5", fg="black")
        self.account_username_label.pack(pady=2)
        
        self.account_email_label = tk.Label(account_info_frame, text="", font=("Helvetica", 10),
                                           bg="#f5f5f5", fg="black")
        self.account_email_label.pack(pady=2)
        
        self.account_created_label = tk.Label(account_info_frame, text="", font=("Helvetica", 10),
                                             bg="#f5f5f5", fg="black")
        self.account_created_label.pack(pady=(2, 10))
        
        # Logout button
        logout_btn = create_button(content_frame, "🚪 Logout", self.logout,
                                   style='danger', size='large')
        logout_btn.pack(pady=(20, 10), padx=2)
        
        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def _darken_color(self, hex_color):
        """Darken a hex color by 20%"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darker = tuple(int(c * 0.8) for c in rgb)
        return f'#{darker[0]:02x}{darker[1]:02x}{darker[2]:02x}'
    
    def set_user(self, username):
        """Set the current user and display their information"""
        self.current_user = username
        users = self.controller.load_users()
        
        if username in users:
            user_data = users[username]
            self.header_welcome_label.config(text=f"Welcome, {username}!")
            
            # Update account information section
            self.account_username_label.config(text=f"Username: {username}")
            self.account_email_label.config(text=f"Email: {user_data.get('email', 'N/A')}")
            self.account_created_label.config(text=f"Member since: {user_data.get('created_at', 'N/A')}")
    
    def open_account(self):
        """Open account page"""
        account_page = self.controller.frames["AccountPage"]
        account_page.set_user(self.current_user)
        self.controller.show_frame("AccountPage")
    
    def view_profile(self):
        """Display user profile details"""
        users = self.controller.load_users()
        if self.current_user and self.current_user in users:
            user_data = users[self.current_user]
            profile_info = f"Username: {self.current_user}\n"
            profile_info += f"Email: {user_data.get('email', 'N/A')}\n"
            profile_info += f"Account Created: {user_data.get('created_at', 'N/A')}\n"
            profile_info += f"Last Login: {user_data.get('last_login', 'N/A')}\n"
            profile_info += f"Role: User"
            messagebox.showinfo("Profile", profile_info)
    
    def open_settings(self):
        """Open settings dialog"""
        settings_window = tk.Toplevel(self.controller)
        settings_window.title("Settings")
        settings_window.geometry("300x250")
        settings_window.configure(bg="white")
        settings_window.resizable(False, False)
        
        # Center the window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (300 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (250 // 2)
        settings_window.geometry(f'300x250+{x}+{y}')
        
        tk.Label(settings_window, text="Settings", 
                font=("Helvetica", 18, "bold"),
                bg="white", fg="black").pack(pady=20)
        
        tk.Label(settings_window, text="Change Password", 
                font=("Helvetica", 11),
                bg="white", fg="black").pack(pady=10)
        
        tk.Button(settings_window, text="Update Password", 
                 bg="#3a3a3a", fg="black", 
                 font=("Helvetica", 10, "bold"),
                 activebackground="#1a1a1a", activeforeground="black",
                 relief="flat", cursor="hand2",
                 command=lambda: messagebox.showinfo("Info", "Password change coming soon!")).pack(pady=10)
        
        tk.Button(settings_window, text="Close", 
                 bg="#2c2c2c", fg="black", 
                 font=("Helvetica", 10, "bold"),
                 activebackground="#0c0c0c", activeforeground="black",
                 relief="flat", cursor="hand2",
                 command=settings_window.destroy).pack(pady=20)
    
    def view_statistics(self):
        """Show user statistics"""
        users = self.controller.load_users()
        if self.current_user and self.current_user in users:
            user_data = users[self.current_user]
            created = user_data.get('created_at', 'N/A')
            
            # Calculate days since account creation
            try:
                created_date = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                days_old = (datetime.now() - created_date).days
                stats = f"Account Statistics\n\n"
                stats += f"Account Age: {days_old} days\n"
                stats += f"Total Users: {len(users)}\n"
                stats += f"Your Rank: Member"
                messagebox.showinfo("Statistics", stats)
            except:
                messagebox.showinfo("Statistics", "Unable to calculate statistics")
    
    def open_daily_log(self):
        """Open daily log application"""
        try:
            dailylog_path = os.path.join(os.path.dirname(__file__), "dailylog.py")
            subprocess.Popen([sys.executable, dailylog_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Daily Log:\n{str(e)}")
    
    def open_reports(self):
        """Open reports application"""
        try:
            report_path = os.path.join(os.path.dirname(__file__), "report.py")
            subprocess.Popen([sys.executable, report_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Reports:\n{str(e)}")
    
    def open_employee_maintenance(self):
        """Open employee maintenance application"""
        try:
            emp_maint_path = os.path.join(os.path.dirname(__file__), "employee_maintenance.py")
            subprocess.Popen([sys.executable, emp_maint_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Employee Maintenance:\n{str(e)}")
    
    def logout(self):
        """Logout the current user"""
        self.current_user = None
        self.controller.show_frame("LoginPage")


class AccountPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller
        self.current_user = None
        
        # Scrollable canvas
        canvas = Canvas(self, bg="white", highlightthickness=0)
        scrollbar = Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="white")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Content frame
        content_frame = tk.Frame(self.scrollable_frame, bg="white")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        header_frame = tk.Frame(content_frame, bg="#2c2c2c", height=60)
        header_frame.pack(fill="x", pady=(0, 20))
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="Account", 
                font=("Helvetica", 20, "bold"),
                bg="#2c2c2c", fg="black").pack(expand=True)
        
        # User info section
        info_frame = tk.Frame(content_frame, bg="#f5f5f5", relief="solid", bd=1)
        info_frame.pack(fill="x", pady=15)
        
        tk.Label(info_frame, text="User Information",
                font=("Helvetica", 12, "bold"),
                bg="#f5f5f5", fg="black").pack(pady=(15, 10))
        
        self.username_label = tk.Label(info_frame, text="", font=("Helvetica", 11),
                                       bg="#f5f5f5", fg="black")
        self.username_label.pack(pady=5)
        
        self.email_label = tk.Label(info_frame, text="", font=("Helvetica", 10),
                                    bg="#f5f5f5", fg="black")
        self.email_label.pack(pady=5)
        
        self.created_label = tk.Label(info_frame, text="", font=("Helvetica", 10),
                                      bg="#f5f5f5", fg="black")
        self.created_label.pack(pady=5)
        
        self.last_login_label = tk.Label(info_frame, text="", font=("Helvetica", 10),
                                         bg="#f5f5f5", fg="black")
        self.last_login_label.pack(pady=(5, 15))
        
        # Account actions section
        actions_label = tk.Label(content_frame, text="Account Actions",
                                font=("Helvetica", 12, "bold"),
                                bg="white", fg="black")
        actions_label.pack(pady=(10, 10))
        
        # Profile button
        profile_btn = tk.Button(content_frame, text="View Profile", 
                               command=self.view_profile,
                               bg="#3a3a3a", fg="black", 
                               activebackground="#1a1a1a", activeforeground="black",
                               font=("Helvetica", 10, "bold"),
                               relief="flat", cursor="hand2", height=2, width=20)
        profile_btn.pack(pady=5)
        profile_btn.bind("<Enter>", lambda e: profile_btn.config(bg="#4a4a4a"))
        profile_btn.bind("<Leave>", lambda e: profile_btn.config(bg="#3a3a3a"))
        
        # Settings button
        settings_btn = create_button(content_frame, "⚙️ Settings", self.open_settings,
                                    style='secondary', height=2, width=20)
        settings_btn.pack(pady=5)
        
        # Statistics button
        stats_btn = create_button(content_frame, "📊 Statistics", self.view_statistics,
                                 style='accent', height=2, width=20)
        stats_btn.pack(pady=5)
        
        # Back button
        back_btn = create_button(content_frame, "← Back", self.back_to_dashboard,
                                style='neutral', height=2)
        back_btn.pack(pady=(20, 10))
    
    def set_user(self, username):
        """Set the current user and update display"""
        self.current_user = username
        self.update_user_info()
    
    def update_user_info(self):
        """Update user information display"""
        if self.current_user:
            users = self.controller.load_users()
            if self.current_user in users:
                user_data = users[self.current_user]
                self.username_label.config(text=f"Username: {self.current_user}")
                self.email_label.config(text=f"Email: {user_data.get('email', 'N/A')}")
                self.created_label.config(text=f"Account Created: {user_data.get('created_at', 'N/A')}")
                self.last_login_label.config(text=f"Last Login: {user_data.get('last_login', 'N/A')}")
    
    def view_profile(self):
        """Show user profile details"""
        users = self.controller.load_users()
        if self.current_user and self.current_user in users:
            user_data = users[self.current_user]
            profile_info = f"Profile Information\n\n"
            profile_info += f"Username: {self.current_user}\n"
            profile_info += f"Email: {user_data.get('email', 'N/A')}\n"
            profile_info += f"Created: {user_data.get('created_at', 'N/A')}\n"
            profile_info += f"Last Login: {user_data.get('last_login', 'N/A')}"
            messagebox.showinfo("Profile", profile_info)
    
    def open_settings(self):
        """Open settings window"""
        settings_window = tk.Toplevel(self)
        settings_window.title("Settings")
        settings_window.geometry("300x250")
        settings_window.configure(bg="white")
        settings_window.resizable(False, False)
        
        # Center window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (300 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (250 // 2)
        settings_window.geometry(f'300x250+{x}+{y}')
        
        tk.Label(settings_window, text="Settings", 
                font=("Helvetica", 18, "bold"),
                bg="white", fg="black").pack(pady=20)
        
        tk.Label(settings_window, text="Change Password", 
                font=("Helvetica", 11),
                bg="white", fg="black").pack(pady=10)
        
        tk.Button(settings_window, text="Update Password", 
                 bg="#3a3a3a", fg="black", 
                 font=("Helvetica", 10, "bold"),
                 activebackground="#1a1a1a", activeforeground="black",
                 relief="flat", cursor="hand2",
                 command=lambda: messagebox.showinfo("Info", "Password change coming soon!")).pack(pady=10)
        
        tk.Button(settings_window, text="Close", 
                 bg="#2c2c2c", fg="black", 
                 font=("Helvetica", 10, "bold"),
                 activebackground="#0c0c0c", activeforeground="black",
                 relief="flat", cursor="hand2",
                 command=settings_window.destroy).pack(pady=20)
    
    def view_statistics(self):
        """Show user statistics"""
        users = self.controller.load_users()
        if self.current_user and self.current_user in users:
            user_data = users[self.current_user]
            created = user_data.get('created_at', 'N/A')
            
            # Calculate days since account creation
            try:
                created_date = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                days_old = (datetime.now() - created_date).days
                stats = f"Account Statistics\n\n"
                stats += f"Account Age: {days_old} days\n"
                stats += f"Total Users: {len(users)}\n"
                stats += f"Your Rank: Member"
                messagebox.showinfo("Statistics", stats)
            except:
                messagebox.showinfo("Statistics", "Unable to calculate statistics")
    
    def back_to_dashboard(self):
        """Return to dashboard"""
        self.controller.show_frame("DashboardPage")


def main():
    app = ModernLoginApp()
    app.mainloop()


if __name__ == "__main__":
    main()
