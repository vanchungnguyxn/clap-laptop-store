"""
Entry point chính cho hệ thống Multi-Agent Laptop Store.
Khởi chạy Flask app + scheduler thu thập dữ liệu.
"""

import sys

from app import create_app
from database.connection import init_db


def main():
    """Khởi tạo và chạy ứng dụng."""
    # 1. Khởi tạo database (tạo bảng nếu chưa có)
    print("[*] Dang khoi tao database...")
    try:
        init_db()
    except Exception as e:
        print(f"[!] Loi DB (co the da ton tai): {e}")

    # 2. Khởi động scheduler thu thập dữ liệu đối thủ (tùy chọn)
    try:
        from data_collection.scheduler import start_scheduler
        print("[*] Dang khoi dong scheduler thu thap gia...")
        start_scheduler()
    except ImportError as e:
        print(f"[!] Bo qua scheduler (thieu thu vien): {e}")
    except Exception as e:
        print(f"[!] Scheduler loi: {e}")

    # 3. Khởi động Flask web server
    print("[*] Dang khoi dong Flask Dashboard tai http://localhost:5000")
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
