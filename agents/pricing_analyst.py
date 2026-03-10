"""
Agent 1: Pricing Analyst Agent
Phân tích giá đối thủ từ database và đề xuất giá mới.

Chức năng:
- Phân tích giá đối thủ so với giá bán hiện tại.
- Tự động tăng giá nếu đối thủ hết hàng hoặc nhu cầu đạt đỉnh.
- Nhận lệnh giảm giá từ Inventory Controller khi tồn kho cao.
- Ghi nhật ký mọi thay đổi giá vào price_change_log.
"""

try:
    from crewai import Agent, Task
except ImportError:
    Agent = None
    Task = None

from database.crud import (
    get_all_products,
    get_latest_competitor_prices,
    check_competitors_out_of_stock,
    update_product_price,
    get_active_rules,
)


def create_pricing_analyst_agent() -> Agent:
    """Tạo Pricing Analyst Agent với CrewAI."""
    return Agent(
        role="Pricing Analyst",
        goal=(
            "Phân tích giá thị trường và đề xuất giá bán tối ưu cho cửa hàng laptop. "
            "Đảm bảo giá cạnh tranh nhưng vẫn có lợi nhuận."
        ),
        backstory=(
            "Bạn là chuyên gia phân tích giá với 10 năm kinh nghiệm trong ngành "
            "bán lẻ điện tử. Bạn hiểu rõ thị trường laptop Việt Nam, biết khi nào "
            "nên tăng/giảm giá dựa trên hành vi đối thủ và nhu cầu thị trường."
        ),
        verbose=True,
        allow_delegation=False,
    )


def analyze_competitor_prices(product_id: int) -> dict:
    """
    Phân tích giá đối thủ cho một sản phẩm.

    Returns:
        dict: {
            "product_id": int,
            "current_price": float,
            "min_competitor_price": float | None,
            "max_competitor_price": float | None,
            "avg_competitor_price": float | None,
            "competitors_out_of_stock": bool,
            "recommendation": str,
        }
    """
    from database.crud import get_product_by_id

    product = get_product_by_id(product_id)
    if not product:
        return {"error": f"Không tìm thấy sản phẩm ID {product_id}"}

    current_price = float(product["current_price"])
    competitor_prices = get_latest_competitor_prices(product_id)
    competitors_out = check_competitors_out_of_stock(product_id)

    analysis = {
        "product_id": product_id,
        "product_name": product["name"],
        "current_price": current_price,
        "cost_price": float(product["cost_price"]) if product["cost_price"] else None,
        "competitors_out_of_stock": competitors_out,
        "competitor_count": len(competitor_prices),
    }

    if competitor_prices:
        in_stock_prices = [
            float(p["price"]) for p in competitor_prices if p["is_in_stock"]
        ]
        if in_stock_prices:
            analysis["min_competitor_price"] = min(in_stock_prices)
            analysis["max_competitor_price"] = max(in_stock_prices)
            analysis["avg_competitor_price"] = sum(in_stock_prices) / len(in_stock_prices)
        else:
            analysis["min_competitor_price"] = None
            analysis["max_competitor_price"] = None
            analysis["avg_competitor_price"] = None
    else:
        analysis["min_competitor_price"] = None
        analysis["max_competitor_price"] = None
        analysis["avg_competitor_price"] = None

    return analysis


def suggest_new_price(product_id: int, overstock_discount: float = 0.0) -> dict:
    """
    Đề xuất giá mới dựa trên phân tích thị trường.

    Args:
        product_id: ID sản phẩm.
        overstock_discount: % giảm giá thêm do tồn kho cao (từ Inventory Agent).

    Returns:
        dict: {
            "product_id": int,
            "old_price": float,
            "new_price": float,
            "change_percent": float,
            "reason": str,
            "action": "increase" | "decrease" | "no_change",
        }
    """
    analysis = analyze_competitor_prices(product_id)
    if "error" in analysis:
        return analysis

    rules = get_active_rules()
    rule = rules[0] if rules else {
        "competitor_out_markup": 10.0,
        "high_demand_markup": 8.0,
    }

    current_price = analysis["current_price"]
    cost_price = analysis.get("cost_price") or (current_price * 0.75)
    new_price = current_price
    reason_parts = []
    action = "no_change"

    # ── RULE 1: Đối thủ hết hàng → tăng giá ──────────────
    if analysis["competitors_out_of_stock"]:
        markup = float(rule.get("competitor_out_markup", 10.0))
        new_price = current_price * (1 + markup / 100)
        reason_parts.append(
            f"Tất cả đối thủ hết hàng → tăng {markup}%"
        )
        action = "increase"

    # ── RULE 2: Giá thấp hơn đối thủ nhiều → tăng giá ────
    elif analysis.get("min_competitor_price"):
        min_comp = analysis["min_competitor_price"]
        avg_comp = analysis["avg_competitor_price"]

        # Nếu giá mình rẻ hơn giá thấp nhất của đối thủ > 10% → tăng
        if current_price < min_comp * 0.90:
            # Tăng giá lên bằng 95% giá thấp nhất đối thủ
            new_price = min_comp * 0.95
            reason_parts.append(
                f"Giá hiện tại thấp hơn đối thủ đáng kể "
                f"(min đối thủ: {min_comp:,.0f}₫) → điều chỉnh tăng"
            )
            action = "increase"

        # Nếu giá mình đắt hơn tất cả đối thủ > 5% → giảm
        elif current_price > avg_comp * 1.05 and avg_comp > 0:
            new_price = avg_comp * 1.02  # Giữ nhỉnh hơn avg 2%
            reason_parts.append(
                f"Giá cao hơn trung bình đối thủ "
                f"(avg: {avg_comp:,.0f}₫) → giảm để cạnh tranh"
            )
            action = "decrease"

    # ── RULE 3: Overstock discount từ Inventory Agent ─────
    if overstock_discount > 0:
        discount_amount = new_price * (overstock_discount / 100)
        new_price = new_price - discount_amount
        reason_parts.append(
            f"Tồn kho cao → giảm thêm {overstock_discount}%"
        )
        action = "decrease"

    # ── Đảm bảo không bán dưới giá vốn ───────────────────
    min_allowed = cost_price * 1.05  # Ít nhất lãi 5% trên giá vốn
    if new_price < min_allowed:
        new_price = min_allowed
        reason_parts.append("Điều chỉnh giá tối thiểu (lãi 5% trên vốn)")

    # Làm tròn
    new_price = round(new_price, -3)  # Làm tròn đến hàng nghìn

    change_percent = ((new_price - current_price) / current_price) * 100

    # Nếu thay đổi quá nhỏ (< 0.5%), bỏ qua
    if abs(change_percent) < 0.5:
        action = "no_change"
        new_price = current_price

    reason = " | ".join(reason_parts) if reason_parts else "Giá hiện tại hợp lý, không thay đổi"

    return {
        "product_id": product_id,
        "product_name": analysis["product_name"],
        "old_price": current_price,
        "new_price": new_price,
        "change_percent": round(change_percent, 2),
        "reason": reason,
        "action": action,
    }


def apply_price_change(suggestion: dict) -> bool:
    """
    Áp dụng đề xuất giá mới vào database.

    Args:
        suggestion: Dict từ suggest_new_price().

    Returns:
        True nếu thành công.
    """
    if suggestion.get("action") == "no_change":
        print(f"  ↔️  {suggestion['product_name']}: Giữ nguyên giá {suggestion['old_price']:,.0f}₫")
        return True

    success = update_product_price(
        product_id=suggestion["product_id"],
        new_price=suggestion["new_price"],
        reason=suggestion["reason"],
        triggered_by="pricing_agent",
    )

    if success:
        symbol = "📈" if suggestion["action"] == "increase" else "📉"
        print(
            f"  {symbol} {suggestion['product_name']}: "
            f"{suggestion['old_price']:,.0f}₫ → {suggestion['new_price']:,.0f}₫ "
            f"({suggestion['change_percent']:+.1f}%)"
        )
    else:
        print(f"  ❌ Lỗi cập nhật giá cho {suggestion['product_name']}")

    return success


def create_pricing_task(product_id: int, overstock_discount: float = 0.0) -> Task:
    """Tạo Task phân tích giá cho CrewAI."""
    return Task(
        description=(
            f"Phân tích giá đối thủ cho sản phẩm ID {product_id}. "
            f"So sánh với giá bán hiện tại và đề xuất giá mới. "
            f"Áp dụng giảm giá tồn kho: {overstock_discount}%."
        ),
        expected_output=(
            "Báo cáo phân tích giá bao gồm: giá hiện tại, giá đối thủ, "
            "đề xuất giá mới, và lý do."
        ),
        agent=create_pricing_analyst_agent(),
    )
