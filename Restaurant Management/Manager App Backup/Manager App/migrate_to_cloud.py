#!/usr/bin/env python3
"""
Migrate SQLite database to PostgreSQL
Copies all data from local SQLite to cloud PostgreSQL
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

def migrate_to_cloud():
    """Migrate all data from SQLite to PostgreSQL"""
    
    print("🔄 Manager App - SQLite to PostgreSQL Migration\n")
    print("=" * 60)
    
    # Check if cloud DB is configured
    if not os.getenv('USE_POSTGRES') == 'true':
        print("\n❌ Cloud database not configured!")
        print("\nPlease set environment variables:")
        print("  USE_POSTGRES=true")
        print("  DB_HOST=your-host.railway.app")
        print("  DB_NAME=railway")
        print("  DB_USER=postgres")
        print("  DB_PASS=your_password")
        print("\nOr create .env file with these values.")
        return False
    
    try:
        # Import both databases
        from database import get_db as get_sqlite_db
        from database_cloud import get_cloud_db
        
        sqlite_db = get_sqlite_db()
        cloud_db = get_cloud_db()
        
        if not cloud_db.use_postgres:
            print("\n❌ Cloud database is not PostgreSQL!")
            print("   Check USE_POSTGRES environment variable.")
            return False
        
        print("\n✅ Connected to both databases")
        print(f"   Source: SQLite (local)")
        print(f"   Target: PostgreSQL (cloud)")
        
        # Get connections
        sqlite_conn = sqlite_db.get_connection()
        pg_conn = cloud_db.get_connection()
        
        sqlite_cursor = sqlite_conn.cursor()
        pg_cursor = pg_conn.cursor()
        
        # Tables to migrate (in order due to foreign keys)
        tables = [
            'companies',
            'users',
            'user_companies',
            'locations',
            'audit_log',
            'sessions',
            'invitations'
        ]
        
        total_rows = 0
        
        for table in tables:
            print(f"\n📦 Migrating table: {table}")
            
            try:
                # Get all rows from SQLite
                sqlite_cursor.execute(f"SELECT * FROM {table}")
                rows = sqlite_cursor.fetchall()
                
                if not rows:
                    print(f"   ⚠️  No data in {table}")
                    continue
                
                # Get column names
                column_names = [description[0] for description in sqlite_cursor.description]
                
                # Clear PostgreSQL table (optional - comment out to append)
                pg_cursor.execute(f"DELETE FROM {table}")
                
                # Insert into PostgreSQL
                placeholders = ','.join(['%s'] * len(column_names))
                columns = ','.join(column_names)
                
                insert_query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
                
                migrated = 0
                for row in rows:
                    try:
                        pg_cursor.execute(insert_query, tuple(row))
                        migrated += 1
                    except Exception as e:
                        print(f"   ⚠️  Error inserting row: {e}")
                        continue
                
                pg_conn.commit()
                total_rows += migrated
                
                print(f"   ✅ Migrated {migrated} rows")
                
            except Exception as e:
                print(f"   ❌ Error with {table}: {e}")
                continue
        
        # Close connections
        sqlite_conn.close()
        pg_conn.close()
        
        print("\n" + "=" * 60)
        print(f"\n✅ Migration complete!")
        print(f"   Total rows migrated: {total_rows}")
        print(f"\nNext steps:")
        print("  1. Test cloud database: .venv/bin/python Manager App/database_cloud.py")
        print("  2. Update imports in main.py to use database_cloud")
        print("  3. Test the app: .venv/bin/python Manager App/main.py")
        print("\n💡 Tip: Keep SQLite backup until you verify cloud DB works!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration():
    """Verify data was migrated correctly"""
    
    print("\n🔍 Verifying Migration...\n")
    
    try:
        from database import get_db as get_sqlite_db
        from database_cloud import get_cloud_db
        
        sqlite_db = get_sqlite_db()
        cloud_db = get_cloud_db()
        
        sqlite_conn = sqlite_db.get_connection()
        pg_conn = cloud_db.get_connection()
        
        tables = ['companies', 'users', 'user_companies', 'locations', 'audit_log']
        
        all_match = True
        
        for table in tables:
            # Count in SQLite
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            sqlite_count = sqlite_cursor.fetchone()[0]
            
            # Count in PostgreSQL
            pg_cursor = pg_conn.cursor()
            pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = pg_cursor.fetchone()[0]
            
            match = "✅" if sqlite_count == pg_count else "❌"
            print(f"{match} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
            
            if sqlite_count != pg_count:
                all_match = False
        
        sqlite_conn.close()
        pg_conn.close()
        
        if all_match:
            print("\n✅ All tables match! Migration successful.")
        else:
            print("\n⚠️  Some tables don't match. Check for errors above.")
        
        return all_match
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def backup_sqlite():
    """Create backup of SQLite database before migration"""
    import shutil
    
    source = os.path.expanduser("~/Documents/AIO Python/Manager App/manager_app.db")
    backup = os.path.expanduser(
        f"~/Documents/AIO Python/Manager App/manager_app_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    
    try:
        shutil.copy2(source, backup)
        print(f"✅ Backup created: {os.path.basename(backup)}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False


if __name__ == "__main__":
    print("\n🔄 SQLite to PostgreSQL Migration Tool\n")
    
    # Check if .env file exists
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        print("✅ Found .env file, loading environment variables...")
        from dotenv import load_dotenv
        load_dotenv()
    else:
        print("⚠️  No .env file found. Using system environment variables.")
    
    print("\nOptions:")
    print("  1. Backup SQLite (recommended first)")
    print("  2. Migrate to Cloud")
    print("  3. Verify Migration")
    print("  4. Full Migration (backup + migrate + verify)")
    print("  5. Exit")
    
    choice = input("\nChoose option (1-5): ").strip()
    
    if choice == '1':
        backup_sqlite()
    elif choice == '2':
        migrate_to_cloud()
    elif choice == '3':
        verify_migration()
    elif choice == '4':
        print("\n🚀 Starting full migration...\n")
        if backup_sqlite():
            if migrate_to_cloud():
                verify_migration()
    elif choice == '5':
        print("Goodbye!")
    else:
        print("Invalid choice")
