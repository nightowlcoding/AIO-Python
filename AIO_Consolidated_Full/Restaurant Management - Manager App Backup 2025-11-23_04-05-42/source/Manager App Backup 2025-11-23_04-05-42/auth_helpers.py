"""
Enhanced authentication methods
Terms acceptance, onboarding, and improved security
"""
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from legal import TermsWindow


def show_terms_acceptance(auth_app, user, is_registration=False):
    """Show terms acceptance dialog"""
    def on_accept():
        # Record terms acceptance
        from database import get_db
        db = get_db()
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET accepted_terms_version = ?,
                accepted_terms_date = ?
            WHERE id = ?
        ''', ('1.0', datetime.now().isoformat(), user['id']))
        
        conn.commit()
        conn.close()
        
        # Log the acceptance
        db.log_action(user['id'], 'terms_accepted', None, {'version': '1.0'})
        
        # Continue to company setup or dashboard
        if is_registration:
            auth_app.show_company_setup(user)
        else:
            companies = db.get_user_companies(user['id'])
            auth_app.session.login(user, companies)
            
            if len(companies) > 1:
                auth_app.show_company_selector()
            else:
                # Check if first login for onboarding
                is_first_login = user.get('last_login') is None or user.get('last_login') == user.get('created_at')
                auth_app.open_dashboard(show_onboarding=is_first_login)
    
    def on_decline():
        messagebox.showinfo(
            "Terms Required",
            "You must accept the Terms of Service and Privacy Policy to use Manager App.\\n\\n"
            "If you have concerns, please contact support."
        )
        # Return to login
        auth_app.show_login_screen()
    
    # Show terms window with accept callback
    terms_window = TermsWindow(auth_app, on_accept=on_accept, on_decline=on_decline)


def open_dashboard_with_onboarding(auth_app, show_onboarding=False):
    """Open dashboard with optional onboarding"""
    if show_onboarding and auth_app.session.current_company_name:
        from onboarding import show_onboarding as show_wizard
        show_wizard(auth_app, auth_app.session.current_company_name, auth_app.session.full_name)
    
    auth_app.destroy()
    
    import os
    import subprocess
    import sys
    
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
    subprocess.Popen([sys.executable, dashboard_path])
