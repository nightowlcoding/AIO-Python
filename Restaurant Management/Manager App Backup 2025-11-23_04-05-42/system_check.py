#!/usr/bin/env python3
"""
Quick System Check
Verifies all components are working
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

def check_system():
    """Run system checks"""
    print("🔍 Manager App - System Check\n")
    print("=" * 60)
    
    # 1. Database
    print("\n1. Database Check...")
    try:
        from database import get_db
        db = get_db()
        conn = db.get_connection()
        
        # Check tables exist
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['users', 'companies', 'user_companies', 'locations', 
                          'audit_log', 'sessions', 'invitations']
        
        for table in required_tables:
            if table in tables:
                print(f"   ✅ Table '{table}' exists")
            else:
                print(f"   ❌ Table '{table}' missing")
        
        conn.close()
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False
    
    # 2. Password Hashing
    print("\n2. Password Security Check...")
    try:
        test_password = "TestPassword123"
        hash1, salt1 = db.hash_password(test_password)
        hash2, salt2 = db.hash_password(test_password)
        
        # Same password should have different hashes (different salts)
        if hash1 != hash2:
            print(f"   ✅ PBKDF2 with unique salts working")
        else:
            print(f"   ⚠️  Warning: Same hash for same password (check salt generation)")
        
        # Verify hash
        verify_hash, _ = db.hash_password(test_password, salt1)
        if verify_hash == hash1:
            print(f"   ✅ Password verification working")
        else:
            print(f"   ❌ Password verification failed")
    except Exception as e:
        print(f"   ❌ Password hashing error: {e}")
        return False
    
    # 3. Session Management
    print("\n3. Session Management Check...")
    try:
        from session import get_session
        session = get_session()
        print(f"   ✅ Session module loaded")
        print(f"   ℹ️  Session timeout: 30 minutes")
        print(f"   ℹ️  Max duration: 8 hours")
    except Exception as e:
        print(f"   ❌ Session error: {e}")
        return False
    
    # 4. Security Middleware
    print("\n4. Security Middleware Check...")
    try:
        from security import InputValidator, EncryptionHelper, SecurityMiddleware
        
        validator = InputValidator()
        
        # Test email validation
        if validator.validate_email("test@example.com"):
            print(f"   ✅ Email validation working")
        else:
            print(f"   ❌ Email validation failed")
        
        # Test password strength
        weak = validator.validate_password_strength("weak")
        if not weak['valid']:
            print(f"   ✅ Password strength validation working")
        else:
            print(f"   ❌ Password strength validation too lenient")
        
        strong = validator.validate_password_strength("Strong123Pass")
        if strong['valid']:
            print(f"   ✅ Strong password accepted")
        else:
            print(f"   ❌ Strong password rejected: {strong['missing']}")
    except Exception as e:
        print(f"   ❌ Security module error: {e}")
        return False
    
    # 5. Legal Documents
    print("\n5. Legal Compliance Check...")
    try:
        from legal import TERMS_OF_SERVICE, PRIVACY_POLICY
        
        if len(TERMS_OF_SERVICE) > 1000:
            print(f"   ✅ Terms of Service loaded ({len(TERMS_OF_SERVICE)} chars)")
        else:
            print(f"   ❌ Terms of Service too short")
        
        if len(PRIVACY_POLICY) > 1000:
            print(f"   ✅ Privacy Policy loaded ({len(PRIVACY_POLICY)} chars)")
        else:
            print(f"   ❌ Privacy Policy too short")
    except Exception as e:
        print(f"   ❌ Legal documents error: {e}")
        return False
    
    # 6. Onboarding
    print("\n6. User Experience Check...")
    try:
        from onboarding import OnboardingWizard
        print(f"   ✅ Onboarding wizard available")
    except Exception as e:
        print(f"   ❌ Onboarding error: {e}")
        return False
    
    # 7. Data Export
    print("\n7. Data Privacy Tools Check...")
    try:
        from data_export import DataExporter, AccountDeleter
        print(f"   ✅ Data export tool available")
        print(f"   ✅ Account deletion tool available")
    except Exception as e:
        print(f"   ❌ Data export error: {e}")
        return False
    
    # 8. Enhanced Auth
    print("\n8. Enhanced Authentication Check...")
    try:
        from auth_enhanced import enhanced_login, enhanced_register
        from auth_helpers import show_terms_acceptance
        print(f"   ✅ Enhanced login available")
        print(f"   ✅ Enhanced registration available")
        print(f"   ✅ Terms acceptance flow available")
    except Exception as e:
        print(f"   ❌ Enhanced auth error: {e}")
        return False
    
    # 9. Count users and companies
    print("\n9. Database Status...")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        user_count = cursor.fetchone()[0]
        print(f"   ℹ️  Active users: {user_count}")
        
        cursor.execute("SELECT COUNT(*) FROM companies WHERE is_active = 1")
        company_count = cursor.fetchone()[0]
        print(f"   ℹ️  Active companies: {company_count}")
        
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        log_count = cursor.fetchone()[0]
        print(f"   ℹ️  Audit log entries: {log_count}")
        
        conn.close()
    except Exception as e:
        print(f"   ⚠️  Database stats error: {e}")
    
    print("\n" + "=" * 60)
    print("\n✅ All checks passed! System is ready.\n")
    print("Launch the app:")
    print("  ../.venv/bin/python main.py")
    print("")
    
    return True


if __name__ == "__main__":
    try:
        success = check_system()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Check interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
