"""
CRUD operations cho MySQL database.
Quản lý sản phẩm, giá đối thủ, lịch sử giá, tồn kho, quy tắc kinh doanh,
xác thực nhân viên và nhật ký hoạt động.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import bcrypt
from mysql.connector import Error

from database.connection import get_connection


# ═══════════════════════════════════════════════════════════
#  PRODUCTS
# ═══════════════════════════════════════════════════════════

def get_all_products(active_only: bool = True) -> list[dict]:
    """Lấy danh sách tất cả sản phẩm."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM products"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY name"
        cursor.execute(query)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_product_by_id(product_id: int) -> Optional[dict]:
    """Lấy thông tin một sản phẩm theo ID."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def update_product_price(product_id: int, new_price: float, reason: str,
                         triggered_by: str = "manual") -> bool:
    """
    Cập nhật giá sản phẩm và ghi nhật ký thay đổi.

    Args:
        product_id: ID sản phẩm
        new_price: Giá mới
        reason: Lý do thay đổi
        triggered_by: 'pricing_agent', 'inventory_agent', hoặc 'manual'
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Lấy giá hiện tại
        cursor.execute("SELECT current_price FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        if not product:
            return False

        old_price = float(product["current_price"])
        change_percent = ((new_price - old_price) / old_price) * 100

        # Cập nhật giá mới
        cursor.execute(
            "UPDATE products SET current_price = %s WHERE id = %s",
            (new_price, product_id),
        )

        # Ghi nhật ký thay đổi giá
        cursor.execute(
            """INSERT INTO price_change_log
               (product_id, old_price, new_price, change_percent, reason, triggered_by)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (product_id, old_price, new_price, round(change_percent, 2),
             reason, triggered_by),
        )

        conn.commit()
        return True
    except Error as e:
        conn.rollback()
        print(f"[Error] Lỗi cập nhật giá: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def update_stock_quantity(product_id: int, new_quantity: int,
                          change_type: str = "adjustment",
                          note: str = "") -> bool:
    """Cập nhật số lượng tồn kho và ghi log."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT stock_quantity FROM products WHERE id = %s", (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            return False

        old_qty = product["stock_quantity"]

        cursor.execute(
            "UPDATE products SET stock_quantity = %s WHERE id = %s",
            (new_quantity, product_id),
        )

        cursor.execute(
            """INSERT INTO inventory_log
               (product_id, quantity_before, quantity_after, change_type, note)
               VALUES (%s, %s, %s, %s, %s)""",
            (product_id, old_qty, new_quantity, change_type, note),
        )

        conn.commit()
        return True
    except Error as e:
        conn.rollback()
        print(f"[Error] Lỗi cập nhật tồn kho: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
#  COMPETITOR PRICES
# ═══════════════════════════════════════════════════════════

def save_competitor_price(product_id: int, competitor_id: int,
                          competitor_product_name: str,
                          competitor_url: str, price: float,
                          is_in_stock: bool = True) -> bool:
    """Lưu giá thu thập được từ đối thủ vào database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO competitor_prices
               (product_id, competitor_id, competitor_product_name,
                competitor_url, price, is_in_stock)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (product_id, competitor_id, competitor_product_name,
             competitor_url, price, is_in_stock),
        )
        conn.commit()
        return True
    except Error as e:
        conn.rollback()
        print(f"[Error] Lỗi lưu giá đối thủ: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def get_latest_competitor_prices(product_id: int) -> list[dict]:
    """Lấy giá mới nhất của tất cả đối thủ cho một sản phẩm."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT cp.*, c.name as competitor_name, c.platform
               FROM competitor_prices cp
               JOIN competitors c ON cp.competitor_id = c.id
               WHERE cp.product_id = %s
                 AND cp.scraped_at = (
                     SELECT MAX(cp2.scraped_at)
                     FROM competitor_prices cp2
                     WHERE cp2.product_id = cp.product_id
                       AND cp2.competitor_id = cp.competitor_id
                 )
               ORDER BY cp.price ASC""",
            (product_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_competitor_price_history(product_id: int, days: int = 30) -> list[dict]:
    """Lấy lịch sử giá đối thủ trong N ngày gần nhất."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        since = datetime.now() - timedelta(days=days)
        cursor.execute(
            """SELECT cp.*, c.name as competitor_name
               FROM competitor_prices cp
               JOIN competitors c ON cp.competitor_id = c.id
               WHERE cp.product_id = %s AND cp.scraped_at >= %s
               ORDER BY cp.scraped_at DESC""",
            (product_id, since),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def check_competitors_out_of_stock(product_id: int) -> bool:
    """Kiểm tra xem TẤT CẢ đối thủ có hết hàng sản phẩm này không."""
    prices = get_latest_competitor_prices(product_id)
    if not prices:
        return False
    return all(not p["is_in_stock"] for p in prices)


# ═══════════════════════════════════════════════════════════
#  PRICE CHANGE LOG
# ═══════════════════════════════════════════════════════════

def get_price_change_history(product_id: Optional[int] = None,
                             limit: int = 50) -> list[dict]:
    """Lấy lịch sử thay đổi giá."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """SELECT pcl.*, p.name as product_name
                   FROM price_change_log pcl
                   JOIN products p ON pcl.product_id = p.id"""
        params = []

        if product_id:
            query += " WHERE pcl.product_id = %s"
            params.append(product_id)

        query += " ORDER BY pcl.created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
#  BUSINESS RULES
# ═══════════════════════════════════════════════════════════

def get_active_rules() -> list[dict]:
    """Lấy tất cả quy tắc kinh doanh đang hoạt động."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM business_rules WHERE is_active = TRUE ORDER BY id"
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def update_business_rule(rule_id: int, inventory_threshold: int,
                         discount_percent: float,
                         competitor_out_markup: float,
                         high_demand_markup: float) -> bool:
    """Cập nhật quy tắc kinh doanh."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE business_rules
               SET inventory_threshold = %s,
                   discount_percent = %s,
                   competitor_out_markup = %s,
                   high_demand_markup = %s
               WHERE id = %s""",
            (inventory_threshold, discount_percent,
             competitor_out_markup, high_demand_markup, rule_id),
        )
        conn.commit()
        return True
    except Error as e:
        conn.rollback()
        print(f"[Error] Lỗi cập nhật quy tắc: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def get_all_competitors() -> list[dict]:
    """Lấy danh sách tất cả đối thủ."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM competitors WHERE is_active = TRUE")
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_overstock_products(threshold: int = 100) -> list[dict]:
    """Lấy danh sách sản phẩm có tồn kho vượt ngưỡng."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT * FROM products
               WHERE stock_quantity > %s AND is_active = TRUE
               ORDER BY stock_quantity DESC""",
            (threshold,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
#  ADMIN – PRODUCT MANAGEMENT (THÊM / SỬA / XÓA)
# ═══════════════════════════════════════════════════════════

def create_product(name: str, brand: str, model: str, specs: str,
                   current_price: float, cost_price: float,
                   stock_quantity: int, category: str,
                   cpu: str = "", gpu: str = "", ram: str = "",
                   storage: str = "", screen_size: str = "",
                   screen_detail: str = "", battery: str = "",
                   weight: str = "", os: str = "", ports: str = "",
                   color: str = "", warranty: str = "",
                   description: str = "", image_url: str = "",
                   ) -> Optional[int]:
    """Thêm sản phẩm mới vào database. Returns: ID hoặc None."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO products
               (name, brand, model, specs, current_price, cost_price,
                stock_quantity, category, is_active,
                cpu, gpu, ram, storage, screen_size, screen_detail,
                battery, weight, os, ports, color, warranty,
                description, image_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,
                       %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name, brand, model, specs, current_price, cost_price,
             stock_quantity, category,
             cpu, gpu, ram, storage, screen_size, screen_detail,
             battery, weight, os, ports, color, warranty,
             description, image_url),
        )
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        conn.rollback()
        print(f"Loi tao san pham: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def update_product(product_id: int, name: str, brand: str, model: str,
                   specs: str, current_price: float, cost_price: float,
                   stock_quantity: int, category: str,
                   cpu: str = "", gpu: str = "", ram: str = "",
                   storage: str = "", screen_size: str = "",
                   screen_detail: str = "", battery: str = "",
                   weight: str = "", os: str = "", ports: str = "",
                   color: str = "", warranty: str = "",
                   description: str = "", image_url: str = "",
                   ) -> bool:
    """Cập nhật thông tin sản phẩm."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE products
               SET name=%s, brand=%s, model=%s, specs=%s,
                   current_price=%s, cost_price=%s,
                   stock_quantity=%s, category=%s,
                   cpu=%s, gpu=%s, ram=%s, storage=%s,
                   screen_size=%s, screen_detail=%s,
                   battery=%s, weight=%s, os=%s, ports=%s,
                   color=%s, warranty=%s, description=%s, image_url=%s
               WHERE id=%s""",
            (name, brand, model, specs, current_price, cost_price,
             stock_quantity, category,
             cpu, gpu, ram, storage, screen_size, screen_detail,
             battery, weight, os, ports, color, warranty,
             description, image_url, product_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        conn.rollback()
        print(f"Loi cap nhat san pham: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def delete_product(product_id: int) -> bool:
    """Xóa sản phẩm (soft delete – đánh dấu is_active = FALSE)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE products SET is_active = FALSE WHERE id = %s",
            (product_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        conn.rollback()
        print(f"Loi xoa san pham: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def delete_all_products() -> int:
    """Ẩn toàn bộ sản phẩm đang active. Returns: số dòng bị ảnh hưởng."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE products SET is_active = FALSE WHERE is_active = TRUE")
        conn.commit()
        return int(cursor.rowcount or 0)
    except Error as e:
        conn.rollback()
        print(f"Loi xoa tat ca san pham: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def hard_delete_product(product_id: int) -> bool:
    """Xóa vĩnh viễn 1 sản phẩm (DELETE)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        conn.rollback()
        print(f"Loi xoa vinh vien san pham: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def hard_delete_all_products() -> int:
    """Xóa vĩnh viễn toàn bộ sản phẩm (DELETE). Returns: số dòng bị ảnh hưởng."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM products")
        conn.commit()
        return int(cursor.rowcount or 0)
    except Error as e:
        conn.rollback()
        print(f"Loi xoa vinh vien tat ca san pham: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def search_products(keyword: str) -> list[dict]:
    """Tìm kiếm sản phẩm theo tên, thương hiệu, model."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        like = f"%{keyword}%"
        cursor.execute(
            """SELECT * FROM products
               WHERE is_active = TRUE
                 AND (name LIKE %s OR brand LIKE %s OR model LIKE %s)
               ORDER BY name""",
            (like, like, like),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_products_with_competitor_prices() -> list[dict]:
    """
    Lấy tất cả sản phẩm kèm giá đối thủ mới nhất.
    Dùng cho trang shop khách hàng.
    """
    products = get_all_products(active_only=True)
    for product in products:
        product["competitor_prices"] = get_latest_competitor_prices(product["id"])
        # Tính giá thấp nhất đối thủ
        in_stock = [float(cp["price"]) for cp in product["competitor_prices"]
                    if cp["is_in_stock"]]
        product["min_competitor_price"] = min(in_stock) if in_stock else None
        product["max_competitor_price"] = max(in_stock) if in_stock else None
        product["avg_competitor_price"] = (
            sum(in_stock) / len(in_stock) if in_stock else None
        )
    return products


def save_competitor_prices_bulk(product_id: int,
                                prices: list[dict]) -> bool:
    """
    Lưu danh sách giá đối thủ cho một sản phẩm (dùng khi AI gợi ý giá).
    prices: [{"competitor_id": int, "name": str, "url": str,
              "price": float, "is_in_stock": bool}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for p in prices:
            cursor.execute(
                """INSERT INTO competitor_prices
                   (product_id, competitor_id, competitor_product_name,
                    competitor_url, price, is_in_stock)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (product_id, p["competitor_id"], p["name"],
                 p["url"], p["price"], p["is_in_stock"]),
            )
        conn.commit()
        return True
    except Error as e:
        conn.rollback()
        print(f"Loi luu gia doi thu: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def _get_or_create_competitor(cursor, site_name: str,
                              domain: str = "") -> int:
    """Tìm hoặc tạo competitor theo tên, trả về competitor_id."""
    cursor.execute(
        "SELECT id FROM competitors WHERE name = %s", (site_name,))
    row = cursor.fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["id"]
    base_url = f"https://{domain}" if domain else ""
    cursor.execute(
        """INSERT INTO competitors (name, base_url, platform, is_active)
           VALUES (%s, %s, 'other', TRUE)""",
        (site_name, base_url),
    )
    return cursor.lastrowid


def save_ai_scraped_prices(product_id: int,
                           ai_results: list[dict]) -> bool:
    """
    Lưu kết quả AI scrape giá vào competitor_prices.
    ai_results: list từ quick_price_check, mỗi item có
        site_name, domain, product_title, price, url, ...
    """
    if not ai_results or not product_id:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for r in ai_results:
            price = r.get("price", 0)
            if not price or price <= 0:
                continue
            comp_id = _get_or_create_competitor(
                cursor,
                r.get("site_name", r.get("domain", "Unknown")),
                r.get("domain", ""),
            )
            cursor.execute(
                """INSERT INTO competitor_prices
                   (product_id, competitor_id, competitor_product_name,
                    competitor_url, price, is_in_stock)
                   VALUES (%s, %s, %s, %s, %s, TRUE)""",
                (product_id, comp_id,
                 r.get("product_title", "")[:500],
                 r.get("url", "")[:1000],
                 price),
            )
        conn.commit()
        print(f"[DB] Saved {len(ai_results)} competitor prices for product {product_id}")
        return True
    except Error as e:
        conn.rollback()
        print(f"[DB] Error saving AI prices: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
#  ADMIN USERS (Xác thực nhân viên)
# ═══════════════════════════════════════════════════════════

def authenticate_admin(username: str, password: str,
                       employee_code: str) -> Optional[dict]:
    """
    Xác thực nhân viên: username + password + mã nhân viên.
    Returns user dict nếu hợp lệ, None nếu sai.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT * FROM admin_users
               WHERE username = %s AND employee_code = %s AND is_active = TRUE""",
            (username, employee_code),
        )
        user = cursor.fetchone()
        if not user:
            return None

        stored_hash = user["password_hash"]
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode("utf-8")

        if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
            return user
        return None
    finally:
        cursor.close()
        conn.close()


def create_admin_user(username: str, password: str, employee_code: str,
                      full_name: str, role: str = "staff") -> Optional[int]:
    """Tạo tài khoản nhân viên admin mới."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        pw_hash = bcrypt.hashpw(password.encode("utf-8"),
                                bcrypt.gensalt()).decode("utf-8")
        cursor.execute(
            """INSERT INTO admin_users
               (username, password_hash, employee_code, full_name, role)
               VALUES (%s, %s, %s, %s, %s)""",
            (username, pw_hash, employee_code, full_name, role),
        )
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        conn.rollback()
        print(f"Loi tao admin user: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_admin_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM admin_users WHERE id = %s AND is_active = TRUE",
            (user_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


# ═══════════════════════════════════════════════════════════
#  ADMIN ACTIVITY LOG (Nhật ký hoạt động – read-only)
# ═══════════════════════════════════════════════════════════

def log_admin_activity(user_id: int, employee_code: str, full_name: str,
                       action_type: str, description: str,
                       ip_address: str = "") -> bool:
    """Ghi 1 dòng nhật ký hoạt động của nhân viên."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO admin_activity_log
               (user_id, employee_code, full_name, action_type, description, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, employee_code, full_name, action_type,
             description, ip_address),
        )
        conn.commit()
        return True
    except Error as e:
        conn.rollback()
        print(f"Loi ghi activity log: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def get_activity_log(limit: int = 200) -> list[dict]:
    """Lấy danh sách nhật ký hoạt động (mới nhất trước)."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT * FROM admin_activity_log
               ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
