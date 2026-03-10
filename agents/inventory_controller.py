"""
Agent 2: Inventory Controller Agent
Kiểm tra số lượng tồn kho và phối hợp với Pricing Analyst.

Chức năng:
- Kiểm tra tồn kho tất cả sản phẩm.
- Nếu tồn kho > ngưỡng (mặc định 100): gửi yêu cầu giảm giá 5% cho Pricing Agent.
- Phát hiện sản phẩm sắp hết hàng và cảnh báo.
- Ghi nhật ký tình trạng tồn kho.
"""

try:
    from crewai import Agent, Task
except ImportError:
    Agent = None
    Task = None

from database.crud import (
    get_all_products,
    get_overstock_products,
    get_active_rules,
    get_product_by_id,
)


def create_inventory_controller_agent() -> Agent:
    """Tạo Inventory Controller Agent với CrewAI."""
    return Agent(
        role="Inventory Controller",
        goal=(
            "Quản lý và giám sát tồn kho hiệu quả. Phát hiện sản phẩm tồn kho cao "
            "và phối hợp với Pricing Analyst để điều chỉnh giá nhằm đẩy hàng."
        ),
        backstory=(
            "Bạn là chuyên gia quản lý kho hàng với kinh nghiệm tối ưu hóa "
            "vòng quay hàng tồn kho. Bạn hiểu rằng tồn kho cao gây lãng phí "
            "vốn và cần được xử lý bằng chiến lược giá linh hoạt."
        ),
        verbose=True,
        allow_delegation=True,
    )


def check_inventory_status() -> dict:
    """
    Kiểm tra tình trạng tồn kho toàn bộ sản phẩm.

    Returns:
        dict: {
            "total_products": int,
            "overstock_products": list[dict],   # Tồn kho > ngưỡng
            "low_stock_products": list[dict],    # Tồn kho < 10
            "out_of_stock_products": list[dict], # Tồn kho = 0
            "inventory_threshold": int,
            "discount_percent": float,
        }
    """
    rules = get_active_rules()
    rule = rules[0] if rules else {
        "inventory_threshold": 100,
        "discount_percent": 5.0,
    }

    threshold = int(rule.get("inventory_threshold", 100))
    discount = float(rule.get("discount_percent", 5.0))

    products = get_all_products()

    overstock = []
    low_stock = []
    out_of_stock = []

    for product in products:
        qty = product["stock_quantity"]
        product_info = {
            "id": product["id"],
            "name": product["name"],
            "stock_quantity": qty,
            "current_price": float(product["current_price"]),
        }

        if qty > threshold:
            product_info["excess_quantity"] = qty - threshold
            overstock.append(product_info)
        elif qty <= 0:
            out_of_stock.append(product_info)
        elif qty < 10:
            low_stock.append(product_info)

    return {
        "total_products": len(products),
        "overstock_products": overstock,
        "low_stock_products": low_stock,
        "out_of_stock_products": out_of_stock,
        "inventory_threshold": threshold,
        "discount_percent": discount,
    }


def get_overstock_discount_requests() -> list[dict]:
    """
    Tạo danh sách yêu cầu giảm giá cho sản phẩm tồn kho cao.

    Logic cốt lõi:
    - Nếu tồn kho > ngưỡng → yêu cầu Pricing Agent giảm giá theo %.
    - Mức giảm có thể tăng thêm nếu tồn kho vượt quá ngưỡng nhiều.

    Returns:
        list[dict]: Mỗi dict chứa:
            - product_id: ID sản phẩm
            - product_name: Tên sản phẩm
            - stock_quantity: Số lượng tồn
            - discount_percent: % giảm giá đề xuất
            - reason: Lý do
    """
    status = check_inventory_status()
    requests = []

    base_discount = status["discount_percent"]
    threshold = status["inventory_threshold"]

    for product in status["overstock_products"]:
        excess = product["excess_quantity"]

        # Tính mức giảm giá dựa trên mức vượt ngưỡng
        # Vượt 1x ngưỡng: giảm base_discount%
        # Vượt 2x ngưỡng: giảm base_discount * 1.5%
        # Vượt 3x+ ngưỡng: giảm base_discount * 2%
        excess_ratio = excess / threshold if threshold > 0 else 1
        if excess_ratio > 2:
            discount = base_discount * 2
        elif excess_ratio > 1:
            discount = base_discount * 1.5
        else:
            discount = base_discount

        # Giới hạn giảm tối đa 20%
        discount = min(discount, 20.0)

        requests.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "stock_quantity": product["stock_quantity"],
            "discount_percent": round(discount, 2),
            "reason": (
                f"Tồn kho {product['stock_quantity']} sản phẩm "
                f"(vượt ngưỡng {threshold} → dư {excess} sp). "
                f"Inventory Agent yêu cầu giảm {discount:.1f}% để đẩy hàng."
            ),
        })

    return requests


def generate_inventory_report() -> str:
    """Tạo báo cáo tồn kho dạng text."""
    status = check_inventory_status()

    report_lines = [
        "═" * 60,
        "📦 BÁO CÁO TỒN KHO",
        "═" * 60,
        f"Tổng sản phẩm: {status['total_products']}",
        f"Ngưỡng tồn kho: {status['inventory_threshold']}",
        f"Mức giảm giá cơ bản: {status['discount_percent']}%",
        "",
    ]

    if status["overstock_products"]:
        report_lines.append("🔴 SẢN PHẨM TỒN KHO CAO:")
        for p in status["overstock_products"]:
            report_lines.append(
                f"  - {p['name']}: {p['stock_quantity']} sp "
                f"(dư {p['excess_quantity']} sp)"
            )
    else:
        report_lines.append("✅ Không có sản phẩm tồn kho vượt ngưỡng")

    report_lines.append("")

    if status["low_stock_products"]:
        report_lines.append("🟡 SẢN PHẨM SẮP HẾT HÀNG (< 10):")
        for p in status["low_stock_products"]:
            report_lines.append(
                f"  - {p['name']}: {p['stock_quantity']} sp"
            )

    if status["out_of_stock_products"]:
        report_lines.append("⛔ SẢN PHẨM HẾT HÀNG:")
        for p in status["out_of_stock_products"]:
            report_lines.append(f"  - {p['name']}")

    report_lines.append("═" * 60)

    return "\n".join(report_lines)


def create_inventory_task() -> Task:
    """Tạo Task kiểm tra tồn kho cho CrewAI."""
    return Task(
        description=(
            "Kiểm tra tồn kho tất cả sản phẩm. Xác định sản phẩm nào cần "
            "giảm giá do tồn kho vượt ngưỡng. Tạo danh sách yêu cầu giảm giá "
            "gửi cho Pricing Analyst Agent."
        ),
        expected_output=(
            "Báo cáo tồn kho chi tiết và danh sách yêu cầu giảm giá "
            "cho các sản phẩm tồn kho cao."
        ),
        agent=create_inventory_controller_agent(),
    )
