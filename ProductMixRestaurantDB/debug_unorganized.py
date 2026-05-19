import sqlite3

conn = sqlite3.connect('product_mix.db')
conn.row_factory = sqlite3.Row

# Get unorganized count
cursor = conn.cursor()
cursor.execute('''
    SELECT COUNT(DISTINCT i.item_name) as unorganized_count
    FROM all_levels_items i
    LEFT JOIN product_item_production_mappings m 
        ON i.restaurant_id = m.restaurant_id 
        AND LOWER(TRIM(i.item_name)) = LOWER(TRIM(m.source_item_name))
    WHERE m.source_item_name IS NULL
''')
row = cursor.fetchone()
print(f'Total unorganized items: {row["unorganized_count"]}')

# Count by restaurant with details
cursor.execute('''
    SELECT r.id, r.name, r.city, COUNT(DISTINCT i.item_name) as count
    FROM all_levels_items i
    LEFT JOIN restaurants r ON i.restaurant_id = r.id
    LEFT JOIN product_item_production_mappings m 
        ON i.restaurant_id = m.restaurant_id 
        AND LOWER(TRIM(i.item_name)) = LOWER(TRIM(m.source_item_name))
    WHERE m.source_item_name IS NULL
    GROUP BY i.restaurant_id
    ORDER BY r.id
''')
for row in cursor.fetchall():
    print(f'  [{row["id"]}] {row["name"]} ({row["city"]}): {row["count"]} unorganized')

# Check how many mappings exist
cursor.execute('SELECT COUNT(*) as total FROM product_item_production_mappings')
row = cursor.fetchone()
print(f'\nTotal mappings created: {row["total"]}')

# Check production items
cursor.execute('SELECT COUNT(*) as total FROM production_items')
row = cursor.fetchone()
print(f'Total production items: {row["total"]}')

conn.close()
