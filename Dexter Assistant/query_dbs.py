import sqlite3
import os

dbs = [
    r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\ProductMixRestaurantDB\product_mix.db',
    r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\ProductMixRestaurantDB\production_items.db',
    r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Manager App\manager_app.db'
]

for db_path in dbs:
    print(f'--- {db_path} ---')
    if not os.path.exists(db_path):
        print('File not found')
        continue
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f'Tables: {tables}')
        for table in tables:
            cursor.execute(f'PRAGMA table_info("{table}")')
            cols = [c[1] for c in cursor.fetchall()]
            if not cols: continue
            where_clause = " OR ".join([f'CAST("{c}" AS TEXT) LIKE "%2026-05-19%"' for c in cols])
            query = f'SELECT * FROM "{table}" WHERE {where_clause}'
            try:
                cursor.execute(query)
                rows = cursor.fetchall()
                if rows:
                    print(f'Matching records in {table}:')
                    for r in rows: print(r)
            except Exception as e:
                pass
        conn.close()
    except Exception as e:
        print(f'Error accessing {db_path}: {e}')
