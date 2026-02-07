"""
Database module for multi-tenant Manager App
Handles users, companies, and role-based access
"""
import sqlite3
import os
import hashlib
import uuid
from datetime import datetime
import json

DB_PATH = os.path.expanduser("~/Documents/AIO Python/Manager App/manager_app.db")


class Database:
    """Database manager for multi-tenant system"""
    
    def __init__(self):
        self.db_path = DB_PATH
        # Ensure the directory for the database exists
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        self.init_database()
    
    def get_connection(self):
        """Get database connection with timeout and WAL mode"""
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')  # 30 second timeout
        return conn
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Companies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                logo_path TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                tax_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                settings TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT,
                full_name TEXT,
                phone TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER DEFAULT 1,
                is_system_admin INTEGER DEFAULT 0,
                email_verified INTEGER DEFAULT 0,
                email_verification_token TEXT,
                password_reset_token TEXT,
                password_reset_expires TEXT,
                failed_login_attempts INTEGER DEFAULT 0,
                account_locked_until TEXT,
                accepted_terms_version TEXT,
                accepted_terms_date TEXT,
                password_changed_at TEXT,
                last_password_hashes TEXT
            )
        ''')
        
        # User-Company relationships with roles
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_companies (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(user_id, company_id)
            )
        ''')
        
        # Locations table (for multi-location companies)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                manager_user_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (manager_user_id) REFERENCES users(id)
            )
        ''')
        
        # Audit log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                company_id TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                company_id TEXT,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        ''')
        
        # Invitations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invitations (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                invited_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                accepted_at TEXT,
                accepted_by_user_id TEXT,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (invited_by_user_id) REFERENCES users(id),
                FOREIGN KEY (accepted_by_user_id) REFERENCES users(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password, salt=None):
        """Hash password using PBKDF2 with salt"""
        if salt is None:
            salt = os.urandom(32).hex()
        
        # Use PBKDF2 with 100,000 iterations
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        
        return password_hash, salt
    
    def create_user(self, username, email, password, full_name=None, is_system_admin=False):
        """Create a new user"""
        from security import InputValidator
        
        # Validate inputs
        validator = InputValidator()
        if not validator.validate_email(email):
            raise ValueError("Invalid email format")
        
        password_strength = validator.validate_password_strength(password)
        if not password_strength['valid']:
            raise ValueError(f"Password too weak: {', '.join(password_strength['missing'])}")
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        user_id = str(uuid.uuid4())
        password_hash, salt = self.hash_password(password)
        now = datetime.now().isoformat()
        
        # Generate email verification token
        verification_token = str(uuid.uuid4())
        
        try:
            cursor.execute('''
                INSERT INTO users (id, username, email, password_hash, password_salt, 
                                 full_name, created_at, updated_at, is_system_admin,
                                 email_verification_token, password_changed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, email, password_hash, salt, full_name, now, now, 
                  1 if is_system_admin else 0, verification_token, now))
            
            conn.commit()
            return user_id, verification_token
        except sqlite3.IntegrityError as e:
            return None, None
        finally:
            conn.close()
    
    def authenticate_user(self, username, password):
        """Authenticate user and return user data"""
        from datetime import datetime, timedelta
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM users 
            WHERE username = ? AND is_active = 1
        ''', (username,))
        
        user = cursor.fetchone()
        
        if not user:
            return None
        
        # Check if account is locked
        if user['account_locked_until']:
            locked_until = datetime.fromisoformat(user['account_locked_until'])
            if datetime.now() < locked_until:
                remaining = int((locked_until - datetime.now()).total_seconds() / 60)
                raise PermissionError(f"Account locked. Try again in {remaining} minutes.")
            else:
                # Unlock account
                cursor.execute('UPDATE users SET account_locked_until = NULL, failed_login_attempts = 0 WHERE id = ?', 
                             (user['id'],))
                conn.commit()
        
        # Verify password
        if user['password_salt']:
            # New PBKDF2 method
            password_hash, _ = self.hash_password(password, user['password_salt'])
        else:
            # Legacy SHA-256 (for migration)
            password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if password_hash == user['password_hash']:
            # Successful login - reset failed attempts
            cursor.execute('''
                UPDATE users SET last_login = ?, failed_login_attempts = 0, account_locked_until = NULL 
                WHERE id = ?
            ''', (datetime.now().isoformat(), user['id']))
            conn.commit()
            
            # Migrate to PBKDF2 if using old hash
            if not user['password_salt']:
                new_hash, new_salt = self.hash_password(password)
                cursor.execute('UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?',
                             (new_hash, new_salt, user['id']))
                conn.commit()
            
            conn.close()
            return dict(user)
        else:
            # Failed login - increment counter
            failed_attempts = user['failed_login_attempts'] + 1
            
            if failed_attempts >= 5:
                # Lock account for 15 minutes
                from datetime import timedelta
                locked_until = (datetime.now() + timedelta(minutes=15)).isoformat()
                cursor.execute('''
                    UPDATE users SET failed_login_attempts = ?, account_locked_until = ? WHERE id = ?
                ''', (failed_attempts, locked_until, user['id']))
                conn.commit()
                conn.close()
                raise PermissionError("Too many failed attempts. Account locked for 15 minutes.")
            else:
                cursor.execute('UPDATE users SET failed_login_attempts = ? WHERE id = ?', 
                             (failed_attempts, user['id']))
                conn.commit()
                conn.close()
                remaining = 5 - failed_attempts
                raise ValueError(f"Invalid password. {remaining} attempts remaining before lockout.")
        
        conn.close()
        return None
    
    def create_company(self, name, admin_user_id, **kwargs):
        """Create a new company with admin user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        company_id = str(uuid.uuid4())
        uc_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        settings = kwargs.get('settings', {})
        
        try:
            # Insert company
            cursor.execute('''
                INSERT INTO companies (id, name, logo_path, address, phone, email, 
                                     website, tax_id, created_at, updated_at, settings)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (company_id, name, kwargs.get('logo_path'), kwargs.get('address'),
                  kwargs.get('phone'), kwargs.get('email'), kwargs.get('website'),
                  kwargs.get('tax_id'), now, now, json.dumps(settings)))
            
            # Assign admin user to company in same transaction
            cursor.execute('''
                INSERT INTO user_companies (id, user_id, company_id, role, 
                                          permissions, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (uc_id, admin_user_id, company_id, 'business_admin', None, now))
            
            conn.commit()
            return company_id
        except sqlite3.IntegrityError:
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def add_user_to_company(self, user_id, company_id, role, permissions=None):
        """Add user to company with specific role"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        uc_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            cursor.execute('''
                INSERT INTO user_companies (id, user_id, company_id, role, 
                                          permissions, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (uc_id, user_id, company_id, role, 
                  json.dumps(permissions) if permissions else None, now))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_user_companies(self, user_id):
        """Get all companies a user has access to"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.*, uc.role, uc.permissions 
            FROM companies c
            JOIN user_companies uc ON c.id = uc.company_id
            WHERE uc.user_id = ? AND uc.is_active = 1 AND c.is_active = 1
            ORDER BY c.name
        ''', (user_id,))
        
        companies = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return companies
    
    def get_company(self, company_id):
        """Get company details"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM companies WHERE id = ?', (company_id,))
        company = cursor.fetchone()
        
        conn.close()
        return dict(company) if company else None
    
    def update_company(self, company_id, **kwargs):
        """Update company information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        fields = []
        values = []
        
        allowed_fields = ['name', 'logo_path', 'address', 'phone', 'email', 
                         'website', 'tax_id', 'settings']
        
        for field in allowed_fields:
            if field in kwargs:
                fields.append(f"{field} = ?")
                value = kwargs[field]
                if field == 'settings' and isinstance(value, dict):
                    value = json.dumps(value)
                values.append(value)
        
        if fields:
            fields.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            values.append(company_id)
            
            query = f"UPDATE companies SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
        
        conn.close()
    
    def get_company_users(self, company_id):
        """Get all users for a company"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.*, uc.role, uc.permissions
            FROM users u
            JOIN user_companies uc ON u.id = uc.user_id
            WHERE uc.company_id = ? AND uc.is_active = 1 AND u.is_active = 1
            ORDER BY u.full_name, u.username
        ''', (company_id,))
        
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return users
    
    def get_user_role(self, user_id, company_id):
        """Get user's role for a specific company"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT role, permissions FROM user_companies
            WHERE user_id = ? AND company_id = ? AND is_active = 1
        ''', (user_id, company_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'role': result['role'],
                'permissions': json.loads(result['permissions']) if result['permissions'] else {}
            }
        return None
    
    def update_user_role(self, user_id, company_id, role, permissions=None):
        """Update user's role in company"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE user_companies 
            SET role = ?, permissions = ?
            WHERE user_id = ? AND company_id = ?
        ''', (role, json.dumps(permissions) if permissions else None, user_id, company_id))
        
        conn.commit()
        conn.close()
    
    def create_location(self, company_id, name, **kwargs):
        """Create a location for a company"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        location_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            cursor.execute('''
                INSERT INTO locations (id, company_id, name, address, phone, 
                                     manager_user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (location_id, company_id, name, kwargs.get('address'),
                  kwargs.get('phone'), kwargs.get('manager_user_id'), now))
            
            conn.commit()
            return location_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    
    def get_company_locations(self, company_id):
        """Get all locations for a company"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT l.*, u.full_name as manager_name
            FROM locations l
            LEFT JOIN users u ON l.manager_user_id = u.id
            WHERE l.company_id = ? AND l.is_active = 1
            ORDER BY l.name
        ''', (company_id,))
        
        locations = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return locations
    
    def log_action(self, user_id, action, company_id=None, details=None, ip_address=None):
        """Log user action for audit trail"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        log_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO audit_log (id, user_id, company_id, action, details, 
                                 ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (log_id, user_id, company_id, action, 
              json.dumps(details) if details else None, ip_address, now))
        
        conn.commit()
        conn.close()
    
    def get_audit_log(self, company_id=None, user_id=None, limit=100):
        """Get audit log entries"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT al.*, u.username, u.full_name, c.name as company_name
            FROM audit_log al
            LEFT JOIN users u ON al.user_id = u.id
            LEFT JOIN companies c ON al.company_id = c.id
            WHERE 1=1
        '''
        params = []
        
        if company_id:
            query += ' AND al.company_id = ?'
            params.append(company_id)
        
        if user_id:
            query += ' AND al.user_id = ?'
            params.append(user_id)
        
        query += ' ORDER BY al.timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        logs = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return logs


# Singleton instance
_db = None

def get_db():
    """Get database instance"""
    global _db
    if _db is None:
        _db = Database()
    return _db
