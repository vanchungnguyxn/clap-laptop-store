"""
Coordinator: Điều phối hoạt động giữa Pricing Analyst và Inventory Controller.

Flow chính:
1. Inventory Controller kiểm tra tồn kho.
2. Nếu tồn kho > ngưỡng → gửi yêu cầu giảm giá cho Pricing Analyst.
3. Pricing Analyst phân tích giá đối thủ + áp dụng overstock discount.
4. Kết quả cuối cùng: "Quyết định giá mới" được ghi nhật ký.
"""

from datetime import datetime

try:
    from crewai import Crew, Process
except ImportError:
    Crew = None
    Process = None

from agents.pricing_analyst import (
    create_pricing_analyst_agent,
    create_pricing_task,
    suggest_new_price,
    apply_price_change,
    analyze_competitor_prices,
)
from agents.inventory_controller import (
    create_inventory_controller_agent,
    create_inventory_task,
    check_inventory_status,
    get_overstock_discount_requests,
    generate_inventory_report,
)
from database.crud import get_all_products


def run_pricing_analysis():
    """
    Chạy quy trình phân tích giá Multi-Agent hoàn chỉnh.

    Flow:
    1. Inventory Controller → Kiểm tra tồn kho
    2. Inventory Controller → Tạo yêu cầu giảm giá (nếu cần)
    3. Pricing Analyst → Phân tích giá đối thủ + áp dụng discount
    4. Áp dụng thay đổi giá vào database

    Returns:
        dict: Báo cáo tổng hợp.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"🤖 MULTI-AGENT PRICING ANALYSIS")
    print(f"⏰ Thời gian: {timestamp}")
    print(f"{'='*60}\n")

    # ── BƯỚC 1: Inventory Controller kiểm tra tồn kho ────
    print("📦 [INVENTORY CONTROLLER] Đang kiểm tra tồn kho...")
    inventory_status = check_inventory_status()
    inventory_report = generate_inventory_report()
    print(inventory_report)

    # ── BƯỚC 2: Tạo yêu cầu giảm giá từ Inventory Agent ─
    discount_requests = get_overstock_discount_requests()
    if discount_requests:
        print(f"\n📋 Inventory Controller gửi {len(discount_requests)} yêu cầu giảm giá:")
        for req in discount_requests:
            print(f"  → {req['product_name']}: giảm {req['discount_percent']}% "
                  f"(tồn kho: {req['stock_quantity']})")
    else:
        print("\n✅ Không có yêu cầu giảm giá từ Inventory Controller.")

    # ── BƯỚC 3: Pricing Analyst phân tích và đề xuất giá ──
    print(f"\n💰 [PRICING ANALYST] Đang phân tích giá thị trường...")
    products = get_all_products()

    # Tạo map product_id → discount
    discount_map = {
        req["product_id"]: req["discount_percent"]
        for req in discount_requests
    }

    decisions = []
    for product in products:
        pid = product["id"]
        overstock_discount = discount_map.get(pid, 0.0)

        suggestion = suggest_new_price(pid, overstock_discount)
        decisions.append(suggestion)

    # ── BƯỚC 4: Áp dụng thay đổi giá ─────────────────────
    print(f"\n📝 [QUYẾT ĐỊNH GIÁ MỚI]")
    print("-" * 60)

    changes_applied = 0
    for decision in decisions:
        if decision.get("action") != "no_change":
            success = apply_price_change(decision)
            if success:
                changes_applied += 1
        else:
            print(f"  ↔️  {decision.get('product_name', 'N/A')}: "
                  f"Giữ nguyên {decision.get('old_price', 0):,.0f}₫")

    # ── Tổng kết ──────────────────────────────────────────
    summary = {
        "timestamp": timestamp,
        "total_products": len(products),
        "overstock_products": len(inventory_status["overstock_products"]),
        "low_stock_products": len(inventory_status["low_stock_products"]),
        "discount_requests": len(discount_requests),
        "price_changes_applied": changes_applied,
        "decisions": decisions,
    }

    print(f"\n{'='*60}")
    print(f"📊 TỔNG KẾT:")
    print(f"  Tổng sản phẩm phân tích: {summary['total_products']}")
    print(f"  Sản phẩm tồn kho cao: {summary['overstock_products']}")
    print(f"  Yêu cầu giảm giá: {summary['discount_requests']}")
    print(f"  Thay đổi giá đã áp dụng: {summary['price_changes_applied']}")
    print(f"{'='*60}\n")

    return summary


def run_crew_analysis():
    """
    Chạy phân tích giá thông qua CrewAI Crew (delegation mode).
    Sử dụng khi muốn tận dụng LLM cho phân tích phức tạp hơn.
    """
    # Tạo agents
    pricing_agent = create_pricing_analyst_agent()
    inventory_agent = create_inventory_controller_agent()

    # Tạo tasks
    inventory_task = create_inventory_task()
    pricing_task = create_pricing_task(product_id=0)  # Placeholder

    # Tạo Crew
    crew = Crew(
        agents=[inventory_agent, pricing_agent],
        tasks=[inventory_task, pricing_task],
        process=Process.sequential,
        verbose=True,
    )

    # Chạy Crew
    result = crew.kickoff()
    return result


# ─── Chạy trực tiếp để test ──────────────────────────────
if __name__ == "__main__":
    run_pricing_analysis()
