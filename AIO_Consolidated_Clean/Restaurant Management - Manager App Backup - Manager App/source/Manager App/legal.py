"""
Terms of Service and Privacy Policy for Manager App
GDPR and CCPA compliant
"""
import tkinter as tk
from tkinter import ttk
from app_config import COLORS, FONTS
from datetime import datetime


TERMS_OF_SERVICE = """
MANAGER APP - TERMS OF SERVICE

Last Updated: November 19, 2025

1. ACCEPTANCE OF TERMS
By creating an account and using Manager App, you agree to these Terms of Service.

2. SERVICE DESCRIPTION
Manager App is a restaurant management software providing:
- Daily operations tracking
- Employee management
- Financial reporting
- Multi-location support
- Data analytics

3. USER ACCOUNTS
3.1 You must provide accurate information when registering
3.2 You are responsible for maintaining account security
3.3 One person per account (no sharing credentials)
3.4 Minimum age: 18 years old
3.5 You must notify us of unauthorized access immediately

4. DATA PRIVACY & SECURITY
4.1 Your data is stored securely on your local system
4.2 Company data is isolated (restaurants cannot access each other's data)
4.3 We use industry-standard encryption for sensitive data
4.4 You own all data you create in the system
4.5 We comply with GDPR and CCPA regulations

5. DATA ISOLATION
5.1 Each company has completely separate data storage
5.2 Users can only access companies they're authorized for
5.3 No cross-company data access without explicit permission
5.4 All file operations are restricted to company directories
5.5 Audit logs track all data access

6. USER RESPONSIBILITIES
6.1 Keep your password secure (minimum 8 characters)
6.2 Use appropriate roles for team members
6.3 Don't share sensitive business data with unauthorized persons
6.4 Maintain regular backups of critical data
6.5 Report security issues immediately

7. BUSINESS ADMIN RESPONSIBILITIES
7.1 Properly vet users before granting access
7.2 Assign appropriate roles and permissions
7.3 Monitor audit logs for suspicious activity
7.4 Maintain accurate company information
7.5 Remove access for departed employees promptly

8. PROHIBITED ACTIVITIES
8.1 Attempting to access other companies' data
8.2 SQL injection or other hacking attempts
8.3 Sharing login credentials
8.4 Automated scraping or data mining
8.5 Uploading malicious files
8.6 Excessive API calls (rate limiting enforced)

9. DATA RETENTION
9.1 Active data: Retained while account is active
9.2 Backups: Kept for 30 days
9.3 Audit logs: Retained for 1 year
9.4 Deleted accounts: Data removed within 30 days

10. YOUR RIGHTS (GDPR/CCPA)
10.1 Right to access your data
10.2 Right to export your data
10.3 Right to delete your data
10.4 Right to correct inaccurate data
10.5 Right to opt-out of data processing
10.6 Right to data portability

11. DISCLAIMERS
11.1 Software provided "AS IS"
11.2 We don't guarantee 100% uptime
11.3 You're responsible for data backups
11.4 We're not liable for data loss
11.5 Use at your own risk

12. LIMITATION OF LIABILITY
12.1 Maximum liability: Amount paid for service (if any)
12.2 No liability for indirect damages
12.3 No liability for third-party actions
12.4 Business interruption not covered

13. TERMINATION
13.1 You may delete your account anytime
13.2 We may terminate for Terms violations
13.3 Data exported before termination
13.4 No refunds after termination

14. CHANGES TO TERMS
14.1 We may update these Terms
14.2 You'll be notified of material changes
14.3 Continued use means acceptance

15. CONTACT
For questions about these Terms:
- Email: support@managerapp.com
- In-app support system
"""


PRIVACY_POLICY = """
MANAGER APP - PRIVACY POLICY

Last Updated: November 19, 2025

1. INFORMATION WE COLLECT

1.1 Account Information
- Username and email (required)
- Full name (optional but recommended)
- Phone number (optional)
- Company information

1.2 Usage Data
- Login times and IP addresses
- Features accessed
- Files created/modified
- Audit trail of actions

1.3 Business Data
- Employee records
- Sales data
- Financial information
- Operational logs

2. HOW WE USE YOUR INFORMATION

2.1 Service Delivery
- Provide core functionality
- Save your preferences
- Enable multi-company access
- Generate reports

2.2 Security
- Prevent unauthorized access
- Detect fraud and abuse
- Enforce rate limiting
- Maintain audit logs

2.3 Improvements
- Analyze usage patterns (anonymized)
- Fix bugs and errors
- Develop new features

3. DATA STORAGE

3.1 Local Storage
- All data stored on YOUR local system
- Database file: manager_app.db
- Company data: ~/Documents/AIO Python/company_data/
- Session data: session.json

3.2 No Cloud Storage
- We do NOT store your data on external servers
- No third-party cloud services
- Everything stays on your computer

3.3 Backups
- Automatic backups in company directory
- You control backup retention
- Export data anytime

4. DATA ISOLATION & SECURITY

4.1 Company Separation
- Each company has isolated data directory
- UUID-based directory names (not guessable)
- File path validation prevents cross-access
- Operating system permissions enforced

4.2 Access Control
- Role-based permissions
- User-company relationships tracked
- Session-based authentication
- Action logging

4.3 Encryption
- Passwords hashed with PBKDF2 (100,000 iterations)
- Sensitive data encrypted
- Secure session management
- No plaintext password storage

5. DATA SHARING

5.1 Within Company
- Users in same company can access shared data
- Based on assigned role and permissions
- Business admin controls access

5.2 Between Companies
- NO data sharing between companies
- Each company completely isolated
- Users must be explicitly added to each company

5.3 Third Parties
- We do NOT share data with third parties
- No analytics services
- No advertising networks
- No data sales

6. YOUR PRIVACY RIGHTS

6.1 Access (GDPR Article 15)
- View all data we store about you
- Export in machine-readable format
- Available through "Export Data" feature

6.2 Rectification (GDPR Article 16)
- Correct inaccurate data
- Update outdated information
- Via account settings

6.3 Erasure (GDPR Article 17)
- "Right to be forgotten"
- Delete account and all data
- Permanent and irreversible

6.4 Data Portability (GDPR Article 20)
- Export data in CSV/Excel format
- Take your data to another system
- No lock-in

6.5 Restrict Processing (GDPR Article 18)
- Limit how data is used
- Temporarily suspend account
- Contact support

6.6 Object (GDPR Article 21)
- Object to data processing
- Opt-out of non-essential features
- Account settings

7. CALIFORNIA RESIDENTS (CCPA)

7.1 Right to Know
- What data we collect
- How we use it
- Who we share with (nobody)

7.2 Right to Delete
- Request deletion of personal data
- Exceptions for legal obligations
- 30-day processing time

7.3 Right to Opt-Out
- No data sales (we don't sell data)
- Opt-out of sharing (not applicable)

7.4 Non-Discrimination
- Same service regardless of privacy choices
- No penalties for exercising rights

8. CHILDREN'S PRIVACY

8.1 Age Requirement
- Must be 18+ to create account
- No children's data collected
- COPPA compliance

9. DATA RETENTION

9.1 Active Accounts
- Data retained while account active
- You control retention period
- Delete anytime

9.2 Deleted Accounts
- Data removed within 30 days
- Backups purged
- Irreversible deletion

9.3 Legal Obligations
- May retain for legal compliance
- Tax records (7 years)
- Audit logs (1 year)

10. SECURITY MEASURES

10.1 Technical Safeguards
- Password hashing (PBKDF2)
- Session management
- Input validation
- SQL injection prevention
- Path traversal protection
- Rate limiting

10.2 Administrative Safeguards
- Access controls
- Audit logging
- Security monitoring
- Incident response plan

10.3 Physical Safeguards
- Data on your local system
- You control physical access
- Encryption at rest

11. BREACH NOTIFICATION

11.1 If Security Breach Occurs
- Notify affected users within 72 hours
- Describe breach and impact
- Remediation steps
- Contact information

12. INTERNATIONAL USERS

12.1 Data Location
- Data stored on YOUR local system
- No international transfers
- Your country's laws apply

13. COOKIES & TRACKING

13.1 No Cookies
- Desktop application (not web-based)
- No browser cookies
- No web tracking

13.2 Session Data
- Local session file only
- Deleted on logout
- Not shared externally

14. CHANGES TO POLICY

14.1 Updates
- May update this policy
- Notify via in-app message
- Email notification for material changes
- Effective 30 days after notice

15. CONTACT US

Privacy Questions:
- Email: privacy@managerapp.com
- Data Protection Officer: dpo@managerapp.com
- Address: [Your Address]

To Exercise Your Rights:
1. Log in to Manager App
2. Go to Settings → Privacy
3. Choose: Export Data, Delete Account, etc.

Or email: privacy@managerapp.com with request
"""


class TermsWindow(tk.Toplevel):
    """Terms of Service display"""
    
    def __init__(self, parent, on_accept=None, on_decline=None):
        super().__init__(parent)
        self.on_accept = on_accept
        self.on_decline = on_decline
        
        self.title("Terms of Service")
        self.geometry("700x600")
        self.configure(bg=COLORS['bg_primary'])
        
        # Make modal if callbacks provided
        if on_accept or on_decline:
            self.transient(parent)
            self.grab_set()
        
        # Header
        header = tk.Frame(self, bg=COLORS['primary'], height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="📜 Terms of Service",
            font=FONTS['title'],
            bg=COLORS['primary'],
            fg="white"
        ).pack(pady=15)
        
        # Content
        text_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        text_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        text_widget = tk.Text(
            text_frame,
            wrap="word",
            font=("Arial", 10),
            bg="white",
            fg=COLORS['text'],
            padx=20,
            pady=20
        )
        text_widget.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.insert("1.0", TERMS_OF_SERVICE)
        text_widget.configure(state="disabled")
        
        # Buttons
        if on_accept:
            btn_frame = tk.Frame(self, bg=COLORS['bg_primary'])
            btn_frame.pack(fill="x", padx=20, pady=(0, 20))
            
            accept_btn = tk.Button(
                btn_frame,
                text="I Accept",
                command=self._accept,
                bg=COLORS['secondary'],
                fg="white",
                font=FONTS['button'],
                padx=30,
                pady=10
            )
            accept_btn.pack(side="right", padx=5)
            
            decline_btn = tk.Button(
                btn_frame,
                text="Decline",
                command=self._decline,
                bg=COLORS['neutral'],
                fg="white",
                font=FONTS['button'],
                padx=30,
                pady=10
            )
            decline_btn.pack(side="right", padx=5)
    
    def _accept(self):
        """Handle acceptance"""
        if self.on_accept:
            self.on_accept()
        self.destroy()
    
    def _decline(self):
        """Handle decline"""
        if self.on_decline:
            self.on_decline()
        self.destroy()


class PrivacyWindow(tk.Toplevel):
    """Privacy Policy display"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Privacy Policy")
        self.geometry("700x600")
        self.configure(bg=COLORS['bg_primary'])
        
        # Header
        header = tk.Frame(self, bg=COLORS['secondary'], height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🔒 Privacy Policy",
            font=FONTS['title'],
            bg=COLORS['secondary'],
            fg="white"
        ).pack(pady=15)
        
        # Content
        text_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        text_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        text_widget = tk.Text(
            text_frame,
            wrap="word",
            font=("Arial", 10),
            bg="white",
            fg=COLORS['text'],
            padx=20,
            pady=20
        )
        text_widget.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.insert("1.0", PRIVACY_POLICY)
        text_widget.configure(state="disabled")
        
        # Close button
        btn_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        close_btn = tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            bg=COLORS['primary'],
            fg="white",
            font=FONTS['button'],
            padx=30,
            pady=10
        )
        close_btn.pack(side="right")
