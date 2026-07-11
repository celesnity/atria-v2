import sqlite3

conn = sqlite3.connect('data/warehouse.db')
cursor = conn.cursor()

# Tìm sản phẩm có chữ "Nhật" trong tên
cursor.execute("SELECT id, sku, name, category, quantity FROM items WHERE name LIKE '%Nhật%'")
results = cursor.fetchall()

if results:
    print(f"Found {len(results)} Japanese products:")
    for row in results:
        print(f"  ID:{row[0]} SKU:{row[1]} Name:{row[2]} Qty:{row[4]}")
else:
    print("No products with 'Nhật' found.")

# Tìm sản phẩm có chữ "japan" trong tên (case-insensitive)
cursor.execute("SELECT id, sku, name, category, quantity FROM items WHERE LOWER(name) LIKE '%japan%'")
results_jp = cursor.fetchall()

if results_jp:
    print(f"\nFound {len(results_jp)} products with 'Japan':")
    for row in results_jp:
        print(f"  ID:{row[0]} SKU:{row[1]} Name:{row[2]} Qty:{row[4]}")

conn.close()