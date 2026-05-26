import sqlite3
import os

db_path = r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\ProductMixRestaurantDB\product_mix.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Check for tables that might contain sales or employee data specifically
    target_tables = ['product_mix_uploads', 'all_levels_records', 'production_plans']
    for table in target_tables:
        cursor.execute(f"PRAGMA table_info('{table}')")
        cols = [c[1] for c in cursor.fetchall()]
        if not cols: continue
        print(f"Checking table: {table}")
        where_clause = " OR ".join([f'CAST("{c}" AS TEXT) LIKE "%2026-05-19%"' for c in cols])
        cursor.execute(f'SELECT count(*) FROM "{table}" WHERE {where_clause}')
        count = cursor.fetchone()[0]
        print(f"Count for 2026-05-19 in {table}: {count}")
    conn.close()
else:
    print("DB not found")
