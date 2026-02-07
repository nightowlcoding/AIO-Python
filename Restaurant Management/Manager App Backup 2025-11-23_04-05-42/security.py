"""
Enhanced security middleware for multi-tenant Manager App
Ensures data isolation and prevents unauthorized access
"""
from session import get_session
from database import get_db
from functools import wraps
import os


class SecurityMiddleware:
    """Security checks for all data operations"""
    
    @staticmethod
    def verify_company_access(company_id):
        """Verify user has access to company"""
        session = get_session()
        
        if not session.is_logged_in():
            raise PermissionError("User not logged in")
        
        # System admins can access all
        if session.is_system_admin:
            return True
        
        # Check if user has access to this company
        user_companies = [c['id'] for c in session.companies]
        if company_id not in user_companies:
            raise PermissionError(f"Access denied to company {company_id}")
        
        return True
    
    @staticmethod
    def verify_file_access(file_path):
        """Verify file belongs to user's current company"""
        session = get_session()
        
        if not session.is_logged_in():
            raise PermissionError("User not logged in")
        
        # Get company data directory
        company_dir = session.get_data_dir()
        
        # Resolve absolute paths
        abs_file = os.path.abspath(file_path)
        abs_company = os.path.abspath(company_dir)
        
        # Check if file is within company directory
        if not abs_file.startswith(abs_company):
            raise PermissionError(f"Access denied to file outside company directory")
        
        return True
    
    @staticmethod
    def require_permission(permission):
        """Decorator to require specific permission"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                session = get_session()
                
                if not session.has_permission(permission):
                    raise PermissionError(f"Permission denied: {permission}")
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def require_role(role):
        """Decorator to require specific role"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                session = get_session()
                
                allowed_roles = {
                    'business_admin': ['business_admin'],
                    'manager': ['business_admin', 'manager'],
                    'staff': ['business_admin', 'manager', 'staff']
                }
                
                if session.current_role not in allowed_roles.get(role, []):
                    raise PermissionError(f"Role required: {role}")
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def sanitize_sql_input(value):
        """Sanitize input to prevent SQL injection"""
        if value is None:
            return None
        
        # Remove dangerous characters
        dangerous = ["'", '"', ";", "--", "/*", "*/", "xp_", "sp_"]
        str_value = str(value)
        
        for dangerous_char in dangerous:
            str_value = str_value.replace(dangerous_char, "")
        
        return str_value
    
    @staticmethod
    def validate_company_id_format(company_id):
        """Validate company ID is proper UUID format"""
        import re
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        
        if not uuid_pattern.match(str(company_id)):
            raise ValueError("Invalid company ID format")
        
        return True


class DataIsolation:
    """Ensures complete data isolation between companies"""
    
    @staticmethod
    def get_safe_file_path(filename, subdirectory=None):
        """Get safe file path within company's data directory"""
        session = get_session()
        
        if not session.current_company_id:
            raise PermissionError("No company selected")
        
        # Base directory for company
        company_dir = session.get_data_dir()
        
        # Add subdirectory if specified
        if subdirectory:
            company_dir = os.path.join(company_dir, subdirectory)
            os.makedirs(company_dir, exist_ok=True)
        
        # Combine with filename
        file_path = os.path.join(company_dir, filename)
        
        # Security check: ensure path is still within company directory
        abs_file = os.path.abspath(file_path)
        abs_company = os.path.abspath(company_dir)
        
        if not abs_file.startswith(abs_company):
            raise SecurityError("Path traversal attempt detected")
        
        return file_path
    
    @staticmethod
    def list_company_files(subdirectory=None, extension=None):
        """List files within company directory"""
        session = get_session()
        company_dir = session.get_data_dir()
        
        if subdirectory:
            company_dir = os.path.join(company_dir, subdirectory)
        
        if not os.path.exists(company_dir):
            return []
        
        files = []
        for filename in os.listdir(company_dir):
            file_path = os.path.join(company_dir, filename)
            
            # Skip directories
            if os.path.isdir(file_path):
                continue
            
            # Filter by extension if specified
            if extension and not filename.endswith(extension):
                continue
            
            files.append(filename)
        
        return sorted(files)
    
    @staticmethod
    def get_employee_list_path():
        """Get path to company-specific employee list"""
        return DataIsolation.get_safe_file_path('employee_list.csv', 'employees')
    
    @staticmethod
    def get_daily_log_path(date_str, shift):
        """Get path to company-specific daily log"""
        filename = f"{date_str}_{shift}.csv"
        return DataIsolation.get_safe_file_path(filename, 'daily_logs')
    
    @staticmethod
    def get_backup_directory():
        """Get company-specific backup directory"""
        session = get_session()
        backup_dir = os.path.join(session.get_data_dir(), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir


class RateLimiter:
    """Rate limiting to prevent abuse"""
    
    def __init__(self):
        self.attempts = {}
    
    def check_rate_limit(self, user_id, action, max_attempts=5, window_seconds=300):
        """Check if user has exceeded rate limit"""
        import time
        
        key = f"{user_id}:{action}"
        now = time.time()
        
        if key not in self.attempts:
            self.attempts[key] = []
        
        # Remove old attempts outside window
        self.attempts[key] = [
            timestamp for timestamp in self.attempts[key]
            if now - timestamp < window_seconds
        ]
        
        # Check if limit exceeded
        if len(self.attempts[key]) >= max_attempts:
            return False
        
        # Add current attempt
        self.attempts[key].append(now)
        return True
    
    def reset_rate_limit(self, user_id, action):
        """Reset rate limit for user action"""
        key = f"{user_id}:{action}"
        if key in self.attempts:
            del self.attempts[key]


class InputValidator:
    """Enhanced input validation"""
    
    @staticmethod
    def validate_email(email):
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone):
        """Validate phone number"""
        import re
        # Remove common formatting
        clean_phone = re.sub(r'[\s\-\(\)\.]', '', phone)
        
        # Check if valid (10-15 digits)
        return bool(re.match(r'^\d{10,15}$', clean_phone))
    
    @staticmethod
    def validate_password_strength(password):
        """Validate password meets security requirements
        
        Returns dict with:
            - valid: bool
            - missing: list of requirements not met
        """
        missing = []
        
        if len(password) < 8:
            missing.append("At least 8 characters")
        
        if not any(c.isupper() for c in password):
            missing.append("One uppercase letter")
        
        if not any(c.islower() for c in password):
            missing.append("One lowercase letter")
        
        if not any(c.isdigit() for c in password):
            missing.append("One number")
        
        return {
            'valid': len(missing) == 0,
            'missing': missing
        }
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitize filename to prevent directory traversal"""
        import re
        
        # Remove path separators
        filename = os.path.basename(filename)
        
        # Remove dangerous characters
        filename = re.sub(r'[^\w\s\-\.]', '', filename)
        
        # Prevent hidden files
        if filename.startswith('.'):
            filename = filename[1:]
        
        return filename


class EncryptionHelper:
    """Data encryption utilities"""
    
    @staticmethod
    def hash_password(password, salt=None):
        """Hash password with salt using PBKDF2"""
        import hashlib
        import secrets
        
        if salt is None:
            salt = secrets.token_hex(32)
        
        # Use PBKDF2 with 100,000 iterations
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        
        return {
            'hash': pwdhash.hex(),
            'salt': salt
        }
    
    @staticmethod
    def verify_password(password, stored_hash, salt):
        """Verify password against stored hash"""
        result = EncryptionHelper.hash_password(password, salt)
        return result['hash'] == stored_hash
    
    @staticmethod
    def encrypt_sensitive_data(data, key):
        """Encrypt sensitive data (requires cryptography library)"""
        try:
            from cryptography.fernet import Fernet
            
            f = Fernet(key)
            encrypted = f.encrypt(data.encode())
            return encrypted.decode()
        except ImportError:
            # Fallback if cryptography not installed
            import base64
            return base64.b64encode(data.encode()).decode()
    
    @staticmethod
    def decrypt_sensitive_data(encrypted_data, key):
        """Decrypt sensitive data"""
        try:
            from cryptography.fernet import Fernet
            
            f = Fernet(key)
            decrypted = f.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except ImportError:
            import base64
            return base64.b64decode(encrypted_data.encode()).decode()


class ComplianceLogger:
    """GDPR/CCPA compliance logging"""
    
    @staticmethod
    def log_data_access(user_id, company_id, data_type, action):
        """Log data access for compliance"""
        from database import get_db
        
        db = get_db()
        db.log_action(
            user_id,
            f'data_access_{action}',
            company_id,
            {
                'data_type': data_type,
                'action': action,
                'compliance': 'gdpr_ccpa'
            }
        )
    
    @staticmethod
    def log_data_export(user_id, company_id, export_type):
        """Log data export"""
        from database import get_db
        
        db = get_db()
        db.log_action(
            user_id,
            'data_exported',
            company_id,
            {
                'export_type': export_type,
                'compliance': 'gdpr_right_to_data'
            }
        )
    
    @staticmethod
    def log_data_deletion(user_id, company_id, deletion_type):
        """Log data deletion (right to be forgotten)"""
        from database import get_db
        
        db = get_db()
        db.log_action(
            user_id,
            'data_deleted',
            company_id,
            {
                'deletion_type': deletion_type,
                'compliance': 'gdpr_right_to_erasure'
            }
        )


# Global instances
security = SecurityMiddleware()
data_isolation = DataIsolation()
rate_limiter = RateLimiter()
validator = InputValidator()
encryption = EncryptionHelper()
compliance = ComplianceLogger()


# Convenience functions
def require_login(func):
    """Decorator to require user login"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        session = get_session()
        if not session.is_logged_in():
            raise PermissionError("Login required")
        return func(*args, **kwargs)
    return wrapper


def require_company(func):
    """Decorator to require company selection"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        session = get_session()
        if not session.current_company_id:
            raise PermissionError("Company selection required")
        return func(*args, **kwargs)
    return wrapper
