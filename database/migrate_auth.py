"""
Migration: Tạo bảng admin_users + admin_activity_log và user mặc định.
Chạy 1 lần: python -m database.migrate_auth
"""

import bcrypt
from database.connection import get_connection


def migrate():
    conn = get_connection()
    cursor = conn.cursor()

    statements = [
        """CREATE TABLE IF NOT EXISTS admin_users (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            username        VARCHAR(100) NOT NULL UNIQUE,
            password_hash   VARCHAR(255) NOT NULL,
            employee_code   VARCHAR(50)  NOT NULL UNIQUE,
            full_name       VARCHAR(255) NOT NULL,
            role            VARCHAR(50)  DEFAULT 'staff',
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_username (username),
            INDEX idx_employee_code (employee_code)
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS admin_activity_log (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            user_id         INT,
            employee_code   VARCHAR(50)  NOT NULL,
            full_name       VARCHAR(255),
            action_type     VARCHAR(50)  NOT NULL,
            description     TEXT         NOT NULL,
            ip_address      VARCHAR(45),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_employee (employee_code),
            INDEX idx_action (action_type),
            INDEX idx_created (created_at DESC)
        ) ENGINE=InnoDB""",
    ]

    for sql in statements:
        try:
            cursor.execute(sql)
        except Exception as e:
            print(f"[migrate] Skip: {e}")

    # Default admin: admin / admin123 / NV001
    pw_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
    try:
        cursor.execute(
            """INSERT INTO admin_users
               (username, password_hash, employee_code, full_name, role)
               VALUES (%s, %s, %s, %s, %s)""",
            ("admin", pw_hash, "NV001", "Quản trị viên", "admin"),
        )
        print("[migrate] Created default admin user: admin / admin123 / NV001")
    except Exception as e:
        if "Duplicate" in str(e):
            print("[migrate] Default admin user already exists, skipping.")
        else:
            print(f"[migrate] Error creating user: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print("[migrate] Done!")


if __name__ == "__main__":
    migrate()
