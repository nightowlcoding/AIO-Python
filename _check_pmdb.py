import sqlite3
db = sqlite3.connect(r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\ProductMixRestaurantDB\product_mix.db')
tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables])
for t in tables:
    n = db.execute('SELECT COUNT(*) FROM ' + t[0]).fetchone()[0]
    print('  ' + t[0] + ': ' + str(n) + ' rows')
    if t[0] == 'categories' and n > 0:
        rows = db.execute('SELECT * FROM categories LIMIT 5').fetchall()
        print('  Sample:', rows)
db.close()
