"""" 
Session management for multi-tenant Manager App
Handles current user, company, and permissions
"""
import json
import os
from datetime import datetime, timedelta

SESSION_FILE = os.path.expanduser("~/Documents/AIO Python/Manager App/session.json")
SESSION_TIMEOUT_MINUTES = 30  # Inactivity timeout
MAX_SESSION_HOURS = 8  # Maximum session duration


class Session:
    """Manages current user session"""
    
    def __init__(self):
        self.user_id = None
        self.username = None
        self.full_name = None
        self.email = None
        self.is_system_admin = False
        self.current_company_id = None
        self.current_company_name = None
        self.current_role = None
        self.current_permissions = {}
        self.companies = []
        self.session_created_at = None
        self.last_activity = None
    
    def login(self, user_data, companies):
        """Set session data after login"""
        self.user_id = user_data['id']
        self.username = user_data['username']
        self.full_name = user_data.get('full_name', user_data['username'])
        self.email = user_data['email']
        self.is_system_admin = bool(user_data.get('is_system_admin', 0))
        self.companies = companies
        self.session_created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # Auto-select first company if available
        if companies:
            self.select_company(companies[0]['id'])
        
        self.save()
    
    def select_company(self, company_id):
        """Select active company"""
        company = next((c for c in self.companies if c['id'] == company_id), None)
        if company:
            self.current_company_id = company_id
            self.current_company_name = company['name']
            self.current_role = company['role']
            self.current_permissions = json.loads(company['permissions']) if company.get('permissions') else {}
            self.save()
            return True
        return False
    
    def logout(self):
        """Clear session"""
        self.user_id = None
        self.username = None
        self.full_name = None
        self.email = None
        self.is_system_admin = False
        self.current_company_id = None
        self.current_company_name = None
        self.current_role = None
        self.current_permissions = {}
        self.companies = []
        
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    
    def save(self):
        """Save session to file"""
        data = {
            'user_id': self.user_id,
            'username': self.username,
            'full_name': self.full_name,
            'email': self.email,
            'is_system_admin': self.is_system_admin,
            'current_company_id': self.current_company_id,
            'current_company_name': self.current_company_name,
            'current_role': self.current_role,
            'current_permissions': self.current_permissions,
            'companies': self.companies,
            'session_created_at': self.session_created_at.isoformat() if self.session_created_at else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(SESSION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load session from file"""
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                
                self.user_id = data.get('user_id')
                self.username = data.get('username')
                self.full_name = data.get('full_name')
                self.email = data.get('email')
                self.is_system_admin = data.get('is_system_admin', False)
                self.current_company_id = data.get('current_company_id')
                self.current_company_name = data.get('current_company_name')
                self.current_role = data.get('current_role')
                self.current_permissions = data.get('current_permissions', {})
                self.companies = data.get('companies', [])
                
                # Load timestamps
                if data.get('session_created_at'):
                    self.session_created_at = datetime.fromisoformat(data['session_created_at'])
                if data.get('last_activity'):
                    self.last_activity = datetime.fromisoformat(data['last_activity'])
                
                return True
            except:
                return False
        return False
    
    def is_logged_in(self):
        """Check if user is logged in and session is valid"""
        if self.user_id is None:
            return False
        
        # Check session timeout
        if self.last_activity:
            if isinstance(self.last_activity, str):
                self.last_activity = datetime.fromisoformat(self.last_activity)
            
            inactive_duration = datetime.now() - self.last_activity
            if inactive_duration > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                # Session expired due to inactivity
                self.logout()
                return False
        
        # Check maximum session duration
        if self.session_created_at:
            if isinstance(self.session_created_at, str):
                self.session_created_at = datetime.fromisoformat(self.session_created_at)
            
            total_duration = datetime.now() - self.session_created_at
            if total_duration > timedelta(hours=MAX_SESSION_HOURS):
                # Session expired due to max duration
                self.logout()
                return False
        
        # Update activity timestamp
        self.last_activity = datetime.now()
        self.save()
        
        return True
    
    def has_permission(self, permission):
        """Check if user has specific permission"""
        if self.is_system_admin:
            return True
        
        if self.current_role == 'business_admin':
            return True
        
        return self.current_permissions.get(permission, False)
    
    def is_business_admin(self):
        """Check if user is business admin for current company"""
        return self.current_role == 'business_admin' or self.is_system_admin
    
    def is_manager(self):
        """Check if user is manager or above"""
        return self.current_role in ['business_admin', 'manager'] or self.is_system_admin
    
    def get_data_dir(self):
        """Get data directory for current company"""
        if self.current_company_id:
            base_dir = os.path.expanduser("~/Documents/AIO Python/company_data")
            company_dir = os.path.join(base_dir, self.current_company_id)
            os.makedirs(company_dir, exist_ok=True)
            return company_dir
        return os.path.expanduser("~/Documents/AIO Python/daily_logs")


# Singleton instance
_session = None

def get_session():
    """Get session instance"""
    global _session
    if _session is None:
        _session = Session()
        _session.load()
    return _session
