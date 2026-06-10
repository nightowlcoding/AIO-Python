#!/usr/bin/env python3
"""
Manager App - Enhanced Entry Point
Launches authentication with all new security features
"""
import sys
import os

# Add Manager App to path
sys.path.insert(0, os.path.dirname(__file__))

# Import enhanced authentication functions
from auth_enhanced import enhanced_login, enhanced_register, check_session_timeout
from auth import AuthApp

# Monkey patch the AuthApp methods to use enhanced versions
original_init = AuthApp.__init__

def enhanced_init(self):
    """Enhanced initialization with session timeout check"""
    # Call original init but intercept before showing login
    import tkinter as tk
    tk.Tk.__init__(self)
    self.title("Dexter Restaurant Management Assistant - Login")
    self.geometry("450x600")
    
    from app_config import COLORS
    self.configure(bg=COLORS['bg_primary'])
    self.resizable(False, False)
    
    from database import get_db
    from session import get_session
    
    self.db = get_db()
    self.session = get_session()
    
    # Check session timeout
    if check_session_timeout(self):
        pass  # Session was expired and cleared
    
    # Check if already logged in
    if self.session.is_logged_in():
        self.open_dashboard()
        return
    
    self.show_login_screen()

# Patch methods
AuthApp.__init__ = enhanced_init
AuthApp.login = lambda self: enhanced_login(self)
AuthApp.register = lambda self: enhanced_register(self)

# Add open_dashboard method that supports onboarding
def open_dashboard_method(self, show_onboarding=False):
    """Open dashboard with optional onboarding"""
    if show_onboarding and self.session.current_company_name:
        from onboarding import show_onboarding as show_wizard
        show_wizard(self, self.session.current_company_name, self.session.full_name)
    
    self.destroy()
    
    import subprocess
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
    subprocess.Popen([sys.executable, dashboard_path])

AuthApp.open_dashboard = open_dashboard_method

if __name__ == "__main__":
    print("🏢 Dexter Restaurant Management Assistant - Enhanced Edition")
    print("✓ Security: PBKDF2 password hashing")
    print("✓ Session: 30-minute timeout, 8-hour max")
    print("✓ Protection: Account lockout after 5 failed attempts")
    print("✓ Compliance: GDPR/CCPA terms acceptance")
    print("✓ UX: Onboarding wizard for new users")
    print("")
    print("Launching...")
    
    app = AuthApp()
    app.mainloop()
