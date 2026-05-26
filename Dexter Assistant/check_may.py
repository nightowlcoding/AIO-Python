import sqlite3
import os

db_path = r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\ProductMixRestaurantDB\product_mix.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
for table in tables:
    cursor.execute(f"PRAGMA table_info('{table}')")
    cols = [c[1] for c in cursor.fetchall()]
    where_clause = " OR ".join([f'CAST("{c}" AS TEXT) LIKE "%2026-05%"' for c in cols])
    cursor.execute(f'SELECT count(*) FROM "{table}" WHERE {where_clause}')
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"Table {table} has {count} records in May 2026")
conn.close()
