"""
Migration: Thêm cột chi tiết sản phẩm (CPU, GPU, RAM, ...) và ảnh.
Chạy 1 lần: python -m database.migrate_product_details
"""

from database.connection import get_connection


def migrate():
    conn = get_connection()
    cursor = conn.cursor()

    columns = [
        ("cpu", "VARCHAR(255)"),
        ("gpu", "VARCHAR(255)"),
        ("ram", "VARCHAR(100)"),
        ("storage", "VARCHAR(255)"),
        ("screen_size", "VARCHAR(100)"),
        ("screen_detail", "VARCHAR(255)"),
        ("battery", "VARCHAR(100)"),
        ("weight", "VARCHAR(50)"),
        ("os", "VARCHAR(100)"),
        ("ports", "TEXT"),
        ("color", "VARCHAR(100)"),
        ("warranty", "VARCHAR(100)"),
        ("description", "TEXT"),
        ("image_url", "VARCHAR(500)"),
    ]

    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")
            print(f"[migrate] Added column: {col_name}")
        except Exception as e:
            if "Duplicate" in str(e):
                print(f"[migrate] Column {col_name} already exists, skipping.")
            else:
                print(f"[migrate] Error adding {col_name}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print("[migrate] Done!")


if __name__ == "__main__":
    migrate()
