
import sqlite3

db_path = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Manager App\manager_app.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"Tables: {tables}")

# Look for employee-related tables
emp_tables = [t for t in tables if "employee" in t.lower() or "staff" in t.lower() or "user" in t.lower()]
for table in emp_tables:
    print(f"\nData from table: {table}")
    cursor.execute(f"SELECT * FROM \"{table}\"")
    cols = [description[0] for description in cursor.description]
    print(f"Columns: {cols}")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

conn.close()

