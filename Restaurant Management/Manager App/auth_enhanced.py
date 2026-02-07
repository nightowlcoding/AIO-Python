"""
Updated authentication methods to integrate with new security features
Import and use these methods in auth.py
"""
import tkinter as tk
from tkinter import messagebox


def enhanced_login(auth_app):
    """Enhanced login with security features and error handling"""
    username = auth_app.username_var.get().strip()
    password = auth_app.password_var.get()
    
    if not username or not password:
        messagebox.showwarning("Input Error", "Please enter username and password")
        return
    
    try:
        user = auth_app.db.authenticate_user(username, password)
        
        if user:
            # Get user's companies
            companies = auth_app.db.get_user_companies(user['id'])
            
            if not companies:
                messagebox.showinfo(
                    "No Companies",
                    "You don't have access to any companies yet.\n\n"
                    "Please contact your administrator or create a new company."
                )
                auth_app.show_company_setup(user)
                return
            
            # Login successful
            auth_app.session.login(user, companies)
            auth_app.db.log_action(user['id'], 'login', None)
            
            # Check if terms accepted
            if not user.get('accepted_terms_version'):
                from auth_helpers import show_terms_acceptance
                show_terms_acceptance(auth_app, user, is_registration=False)
                return
            
            # Select company
            if len(companies) > 1:
                auth_app.show_company_selector()
            else:
                # Check if first login for onboarding
                # First login is when last_login is None or same as created_at
                is_first_login = (
                    user.get('last_login') is None or 
                    user.get('last_login') == user.get('created_at')
                )
                
                from auth_helpers import open_dashboard_with_onboarding
                open_dashboard_with_onboarding(auth_app, show_onboarding=is_first_login)
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")
    
    except PermissionError as e:
        # Account locked or other permission issue
        messagebox.showerror("Access Denied", str(e))
    except ValueError as e:
        # Failed attempts warning
        messagebox.showwarning("Login Failed", str(e))
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred during login:\n{str(e)}")


def enhanced_register(auth_app):
    """Enhanced registration with password strength validation"""
    from security import InputValidator
    
    username = auth_app.reg_username_var.get().strip()
    email = auth_app.reg_email_var.get().strip()
    password = auth_app.reg_password_var.get()
    confirm = auth_app.reg_confirm_var.get()
    full_name = auth_app.reg_fullname_var.get().strip()
    
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
        missing = '\n• '.join([''] + password_check['missing'])
        messagebox.showwarning(
            "Weak Password",
            f"Password must have:{missing}\n\n"
            "For your security, please create a stronger password."
        )
        return
    
    if password != confirm:
        messagebox.showwarning("Input Error", "Passwords do not match")
        return
    
    # Create user
    try:
        user_id, verification_token = auth_app.db.create_user(username, email, password, full_name)
        
        if user_id:
            messagebox.showinfo(
                "Account Created! ✓",
                "Your account has been created successfully!\n\n"
                "Next, please review and accept our Terms of Service."
            )
            
            # Authenticate user
            user = auth_app.db.authenticate_user(username, password)
            
            # Show terms acceptance before company setup
            from auth_helpers import show_terms_acceptance
            show_terms_acceptance(auth_app, user, is_registration=True)
        else:
            messagebox.showerror(
                "Registration Failed",
                "Username or email already exists.\nPlease try different credentials."
            )
    except ValueError as e:
        messagebox.showerror("Registration Failed", str(e))
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred:\n{str(e)}")


def check_session_timeout(auth_app):
    """Check and handle session timeout"""
    if auth_app.session.user_id and not auth_app.session.is_logged_in():
        messagebox.showinfo(
            "Session Expired",
            "Your session has expired due to inactivity.\n\n"
            "For your security, please log in again."
        )
        auth_app.session.logout()
        return True
    return False
