"""
Cloud Database Module - PostgreSQL Compatible
Supports both local SQLite and cloud PostgreSQL
"""
import os
import hashlib
import uuid
from datetime import datetime
import json

# Auto-detect database type from environment
USE_POSTGRES = os.getenv('USE_POSTGRES', 'false').lower() == 'true'

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
        print("✅ Using PostgreSQL (Cloud Mode)")
    except ImportError:
        print("⚠️  psycopg2 not installed. Run: pip install psycopg2-binary")
        print("   Falling back to SQLite")
        USE_POSTGRES = False

if not USE_POSTGRES:
    import sqlite3
    print("✅ Using SQLite (Local Mode)")

# Database connection settings
if USE_POSTGRES:
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'manager_app'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASS', ''),
        'port': os.getenv('DB_PORT', '5432')
    }
else:
    DB_PATH = os.path.expanduser("~/Documents/AIO Python/Manager App/manager_app.db")


class CloudDatabase:
    """Database manager that works with SQLite or PostgreSQL"""
    
    def __init__(self):
        self.use_postgres = USE_POSTGRES
        self.init_database()
    
    def get_connection(self):
        """Get database connection (SQLite or PostgreSQL)"""
        if self.use_postgres:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.cursor_factory = psycopg2.extras.RealDictCursor
            return conn
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn
    
    def init_database(self):
        """Initialize database tables (compatible with both SQLite and PostgreSQL)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # SQL type mapping
        if self.use_postgres:
            text_type = "TEXT"
            int_type = "INTEGER"
            pk_type = "TEXT PRIMARY KEY"
            timestamp_type = "TIMESTAMP"
        else:
            text_type = "TEXT"
            int_type = "INTEGER"
            pk_type = "TEXT PRIMARY KEY"
            timestamp_type = "TEXT"
        
        # Companies table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS companies (
                id {pk_type},
                name {text_type} NOT NULL UNIQUE,
                logo_path {text_type},
                address {text_type},
                phone {text_type},
                email {text_type},
                website {text_type},
                tax_id {text_type},
                created_at {timestamp_type} NOT NULL,
                updated_at {timestamp_type} NOT NULL,
                settings {text_type},
                is_active {int_type} DEFAULT 1
            )
        ''')
        
        # Users table with all security fields
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                id {pk_type},
                username {text_type} NOT NULL UNIQUE,
                email {text_type} NOT NULL UNIQUE,
                password_hash {text_type} NOT NULL,
                password_salt {text_type},
                full_name {text_type},
                phone {text_type},
                created_at {timestamp_type} NOT NULL,
                updated_at {timestamp_type} NOT NULL,
                last_login {timestamp_type},
                is_active {int_type} DEFAULT 1,
                is_system_admin {int_type} DEFAULT 0,
                email_verified {int_type} DEFAULT 0,
                email_verification_token {text_type},
                password_reset_token {text_type},
                password_reset_expires {timestamp_type},
                failed_login_attempts {int_type} DEFAULT 0,
                account_locked_until {timestamp_type},
                accepted_terms_version {text_type},
                accepted_terms_date {timestamp_type},
                password_changed_at {timestamp_type},
                last_password_hashes {text_type}
            )
        ''')
        
        # User-Company relationships
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS user_companies (
                id {pk_type},
                user_id {text_type} NOT NULL,
                company_id {text_type} NOT NULL,
                role {text_type} NOT NULL,
                permissions {text_type},
                created_at {timestamp_type} NOT NULL,
                is_active {int_type} DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(user_id, company_id)
            )
        ''')
        
        # Locations table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS locations (
                id {pk_type},
                company_id {text_type} NOT NULL,
                name {text_type} NOT NULL,
                address {text_type},
                phone {text_type},
                manager_user_id {text_type},
                is_active {int_type} DEFAULT 1,
                created_at {timestamp_type} NOT NULL,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (manager_user_id) REFERENCES users(id)
            )
        ''')
        
        # Audit log
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS audit_log (
                id {pk_type},
                user_id {text_type},
                company_id {text_type},
                action {text_type} NOT NULL,
                details {text_type},
                ip_address {text_type},
                timestamp {timestamp_type} NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        ''')
        
        # Sessions table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS sessions (
                id {pk_type},
                user_id {text_type} NOT NULL,
                company_id {text_type},
                token {text_type} NOT NULL UNIQUE,
                created_at {timestamp_type} NOT NULL,
                last_activity {timestamp_type} NOT NULL,
                expires_at {timestamp_type} NOT NULL,
                ip_address {text_type},
                user_agent {text_type},
                is_active {int_type} DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        ''')
        
        # Invitations table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS invitations (
                id {pk_type},
                company_id {text_type} NOT NULL,
                email {text_type} NOT NULL,
                role {text_type} NOT NULL,
                token {text_type} NOT NULL UNIQUE,
                invited_by_user_id {text_type} NOT NULL,
                created_at {timestamp_type} NOT NULL,
                expires_at {timestamp_type} NOT NULL,
                accepted_at {timestamp_type},
                accepted_by_user_id {text_type},
                is_active {int_type} DEFAULT 1,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (invited_by_user_id) REFERENCES users(id),
                FOREIGN KEY (accepted_by_user_id) REFERENCES users(id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Database initialized ({('PostgreSQL' if self.use_postgres else 'SQLite')})")
    
    def execute_query(self, query, params=None):
        """Execute query with parameter substitution for both DB types"""
        if self.use_postgres:
            # PostgreSQL uses %s for parameters
            query = query.replace('?', '%s')
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        try:
            result = cursor.fetchall()
        except:
            result = None
        
        conn.commit()
        conn.close()
        
        return result


# Singleton
_cloud_db = None

def get_cloud_db():
    """Get cloud database instance"""
    global _cloud_db
    if _cloud_db is None:
        _cloud_db = CloudDatabase()
    return _cloud_db


# Connection test
def test_connection():
    """Test database connection"""
    try:
        db = get_cloud_db()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        if db.use_postgres:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"✅ PostgreSQL connected: {version}")
        else:
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            print(f"✅ SQLite connected: {version}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing database connection...\n")
    test_connection()
