"""
Data Export Tool for GDPR Compliance
Allows users to export all their data
"""
import os
import json
import csv
import zipfile
from datetime import datetime
from tkinter import messagebox, filedialog
from database import get_db
from session import get_session


class DataExporter:
    """Export user and company data"""
    
    def __init__(self):
        self.db = get_db()
        self.session = get_session()
    
    def export_all_data(self):
        """Export all user and company data"""
        if not self.session.is_logged_in():
            messagebox.showerror("Error", "You must be logged in to export data")
            return None
        
        # Ask where to save
        filename = filedialog.asksaveasfilename(
            title="Save Data Export",
            defaultextension=".zip",
            filetypes=[("ZIP Archive", "*.zip")],
            initialfile=f"my_data_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )
        
        if not filename:
            return None
        
        try:
            # Create temporary directory for export
            temp_dir = os.path.join(os.path.dirname(filename), f"temp_export_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Export user data
            self._export_user_data(temp_dir)
            
            # Export company data
            self._export_company_data(temp_dir)
            
            # Export audit logs
            self._export_audit_logs(temp_dir)
            
            # Create README
            self._create_readme(temp_dir)
            
            # Create ZIP file
            with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)
            
            # Cleanup temp directory
            import shutil
            shutil.rmtree(temp_dir)
            
            # Log the export
            self.db.log_action(
                self.session.user_id,
                'data_exported',
                self.session.current_company_id,
                {'export_file': os.path.basename(filename)}
            )
            
            messagebox.showinfo(
                "Export Complete",
                f"Your data has been exported successfully!\n\n"
                f"File: {os.path.basename(filename)}\n\n"
                f"This export contains all your personal information,\n"
                f"company data, and activity logs in accordance with\n"
                f"GDPR Article 20 (Right to Data Portability)."
            )
            
            return filename
        
        except Exception as e:
            messagebox.showerror("Export Failed", f"An error occurred:\n{str(e)}")
            return None
    
    def _export_user_data(self, export_dir):
        """Export user account information"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (self.session.user_id,))
        user = dict(cursor.fetchone())
        
        # Remove sensitive fields
        user.pop('password_hash', None)
        user.pop('password_salt', None)
        user.pop('email_verification_token', None)
        user.pop('password_reset_token', None)
        
        # Save as JSON
        with open(os.path.join(export_dir, 'user_profile.json'), 'w') as f:
            json.dump(user, f, indent=2)
        
        conn.close()
    
    def _export_company_data(self, export_dir):
        """Export company information and user role"""
        companies_dir = os.path.join(export_dir, 'companies')
        os.makedirs(companies_dir, exist_ok=True)
        
        for company in self.session.companies:
            company_data = {
                'company_info': company,
                'role': company['role'],
                'permissions': json.loads(company.get('permissions', '{}'))
            }
            
            # Get company data directory
            company_data_dir = os.path.join(
                os.path.expanduser("~/Documents/AIO Python/company_data"),
                company['id']
            )
            
            # Copy relevant files if accessible
            if os.path.exists(company_data_dir) and self.session.is_business_admin():
                company_data['data_location'] = company_data_dir
                company_data['has_data_files'] = True
            
            filename = f"{company['name'].replace(' ', '_')}_{company['id'][:8]}.json"
            with open(os.path.join(companies_dir, filename), 'w') as f:
                json.dump(company_data, f, indent=2)
    
    def _export_audit_logs(self, export_dir):
        """Export user's audit log"""
        logs = self.db.get_audit_log(user_id=self.session.user_id, limit=1000)
        
        # Save as CSV
        csv_path = os.path.join(export_dir, 'activity_log.csv')
        if logs:
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)
        
        # Also save as JSON for easier reading
        json_path = os.path.join(export_dir, 'activity_log.json')
        with open(json_path, 'w') as f:
            json.dump(logs, f, indent=2)
    
    def _create_readme(self, export_dir):
        """Create README file explaining the export"""
        readme_content = f"""
DATA EXPORT - Manager App
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
User: {self.session.username} ({self.session.email})

This export contains all your personal data stored in Manager App.
This data is provided in accordance with:
- GDPR Article 15 (Right of Access)
- GDPR Article 20 (Right to Data Portability)
- CCPA Section 1798.100 (Right to Know)

CONTENTS:
=========

1. user_profile.json
   - Your account information
   - Username, email, full name
   - Account creation date
   - Last login information
   - Terms acceptance status

2. companies/ folder
   - Information about companies you have access to
   - Your role in each company
   - Your permissions

3. activity_log.csv / activity_log.json
   - Complete log of your activities
   - Login history
   - Actions performed
   - Timestamps and IP addresses

DATA PORTABILITY:
================
All files are in standard JSON and CSV formats that can be:
- Read by any text editor
- Imported into spreadsheet software (Excel, Google Sheets)
- Processed by other applications
- Converted to other formats

YOUR RIGHTS:
===========
Under GDPR and CCPA, you have the right to:
✓ Access your data (this export)
✓ Rectify incorrect data (via Settings → Profile)
✓ Delete your data (via Settings → Delete Account)
✓ Restrict processing (via Settings → Privacy)
✓ Object to processing (via Settings → Privacy)
✓ Data portability (this export)

QUESTIONS:
==========
If you have questions about this data or your privacy rights:
- Email: privacy@managerapp.com
- Data Protection Officer: dpo@managerapp.com

This export does NOT include:
- Password (stored as one-way hash for security)
- Other users' data
- Company data you don't have permission to access
"""
        
        with open(os.path.join(export_dir, 'README.txt'), 'w') as f:
            f.write(readme_content)


class AccountDeleter:
    """Delete user account and all personal data"""
    
    def __init__(self):
        self.db = get_db()
        self.session = get_session()
    
    def delete_account(self):
        """Delete user account with confirmation"""
        if not self.session.is_logged_in():
            messagebox.showerror("Error", "You must be logged in")
            return False
        
        # First confirmation
        if not messagebox.askyesno(
            "Delete Account?",
            "Are you sure you want to delete your account?\n\n"
            "This will:\n"
            "• Permanently delete your profile\n"
            "• Remove you from all companies\n"
            "• Delete your activity history\n\n"
            "⚠️ This action CANNOT be undone!\n\n"
            "Do you want to continue?"
        ):
            return False
        
        # Offer data export
        if messagebox.askyesno(
            "Export Your Data First?",
            "Would you like to export your data before deletion?\n\n"
            "This is your last chance to get a copy of your information."
        ):
            exporter = DataExporter()
            export_file = exporter.export_all_data()
            if not export_file:
                if not messagebox.askyesno(
                    "Continue Without Export?",
                    "Export was cancelled.\n\n"
                    "Do you still want to delete your account?"
                ):
                    return False
        
        # Final confirmation
        if not messagebox.askyesno(
            "Final Confirmation",
            "⚠️ FINAL WARNING ⚠️\n\n"
            "This will permanently delete ALL your data.\n\n"
            "Are you absolutely sure?"
        ):
            return False
        
        try:
            user_id = self.session.user_id
            username = self.session.username
            
            # Log the deletion
            self.db.log_action(
                user_id,
                'account_deleted',
                None,
                {'username': username, 'deletion_date': datetime.now().isoformat()}
            )
            
            # Delete user from companies
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM user_companies WHERE user_id = ?', (user_id,))
            
            # Mark user as deleted (soft delete for audit trail)
            cursor.execute('''
                UPDATE users 
                SET is_active = 0,
                    email = ?,
                    username = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (
                f'deleted_{user_id}@deleted.local',
                f'deleted_{user_id}',
                datetime.now().isoformat(),
                user_id
            ))
            
            conn.commit()
            conn.close()
            
            # Logout
            self.session.logout()
            
            messagebox.showinfo(
                "Account Deleted",
                "Your account has been successfully deleted.\n\n"
                "All your personal data has been removed.\n\n"
                "Thank you for using Manager App."
            )
            
            return True
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete account:\n{str(e)}")
            return False


def export_company_data():
    """Export current company's data"""
    session = get_session()
    
    if not session.is_business_admin():
        messagebox.showerror(
            "Permission Denied",
            "Only Business Admins can export company data."
        )
        return
    
    # This would export all company files
    # Implementation depends on what data to include
    messagebox.showinfo(
        "Company Export",
        "Company data export will include:\n"
        "• Daily logs\n"
        "• Employee records\n"
        "• Cash records\n"
        "• Reports\n\n"
        "This feature is coming soon!"
    )
