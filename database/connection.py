"""
Quản lý kết nối MySQL và khởi tạo database.
Hỗ trợ cả local development và Railway (MYSQL_URL).
"""

import os
import mysql.connector
from mysql.connector import Error
from config import Config


def get_connection():
    """Tạo và trả về một kết nối MySQL."""
    try:
        connection = mysql.connector.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
        return connection
    except Error as e:
        print(f"[DB] Connection error: {e}")
        raise


def get_connection_without_db():
    """Kết nối MySQL mà chưa chọn database (dùng để tạo DB)."""
    try:
        connection = mysql.connector.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            charset="utf8mb4",
        )
        return connection
    except Error as e:
        print(f"[DB] Connection error (no db): {e}")
        raise


def init_db():
    """
    Khởi tạo database: tạo DB nếu chưa có, chạy schema.sql.
    Trên Railway, DB đã tồn tại sẵn → chỉ tạo tables.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Thử kết nối không chọn DB (local dev: tạo DB mới)
    # Trên Railway, CREATE DATABASE có thể bị từ chối quyền → bỏ qua
    try:
        conn = get_connection_without_db()
        cursor = conn.cursor()
    except Exception:
        conn = get_connection()
        cursor = conn.cursor()

    try:
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except mysql.connector.Error as e:
                    if e.errno in (1050, 1007, 1062, 1044):
                        pass
                    else:
                        print(f"[DB] SQL Warning: {e}")

        conn.commit()
        print("[DB] Database initialized successfully")

    except Error as e:
        print(f"[DB] Init error: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
