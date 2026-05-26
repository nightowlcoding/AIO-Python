import sys
import os
from pathlib import Path

# Adjust paths
base_dir = Path(r'C:\Users\arnol\OneDrive\Desktop\AIO-Python')
manager_app_dir = base_dir / 'Dexter Assistant' / 'Manager App'
sys.path.insert(0, str(manager_app_dir.absolute()))

# Mocking database path for the module if necessary
os.chdir(str(manager_app_dir))

try:
    from manager_app import app
    import database
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test():
    with app.test_client() as client:
        try:
            conn = database.get_db_connection()
            user = conn.execute('SELECT id FROM users WHERE is_active = 1 LIMIT 1').fetchone()
            conn.close()
        except Exception as e:
            print(f"DB Error: {e}")
            return
        
        if not user:
            print('/daily-log: FAIL (No active user)')
            return

        user_id = user['id']
        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
            sess['current_company_id'] = 'verification-company'

        # Correct endpoint for reports based on file list is report.py -> maybe /reports or /report?
        # Listing showed report.py and manager_app.py.
        endpoints = ['/daily-log', '/employees', '/reports']
        patterns = ['Big House Burgers', 'Alice', 'Kingsville']
        
        for ep in endpoints:
            try:
                response = client.get(ep, follow_redirects=True)
                text = response.get_data(as_text=True)
                passed = all(p in text for p in patterns)
                print(f'{ep}: {"PASS" if passed else "FAIL"}')
            except Exception as e:
                print(f'{ep}: FAIL (Error: {e})')

if __name__ == '__main__':
    test()
