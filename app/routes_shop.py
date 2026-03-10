"""
Shop Blueprint – Trang khách hàng xem sản phẩm và so sánh giá.
URL prefix: / (trang chủ)
"""

from flask import Blueprint, render_template, request, jsonify

from database.crud import (
    get_all_products,
    get_product_by_id,
    get_latest_competitor_prices,
    get_products_with_competitor_prices,
    search_products,
)

shop_bp = Blueprint("shop", __name__)


@shop_bp.route("/")
def index():
    """Trang chủ shop – danh sách sản phẩm."""
    keyword = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    brand = request.args.get("brand", "").strip()
    sort = request.args.get("sort", "name")

    if keyword:
        products = search_products(keyword)
    else:
        products = get_all_products(active_only=True)

    if category:
        products = [p for p in products if p.get("category") == category]

    if brand:
        products = [p for p in products
                    if (p.get("brand") or "").lower() == brand.lower()]

    for product in products:
        comp_prices = get_latest_competitor_prices(product["id"])
        product["competitor_prices"] = comp_prices
        in_stock = [float(cp["price"]) for cp in comp_prices if cp["is_in_stock"]]
        product["min_competitor_price"] = min(in_stock) if in_stock else None

    if sort == "price_asc":
        products.sort(key=lambda p: float(p["current_price"]))
    elif sort == "price_desc":
        products.sort(key=lambda p: float(p["current_price"]), reverse=True)
    elif sort == "newest":
        products.sort(key=lambda p: p.get("id", 0), reverse=True)

    all_products = get_all_products(active_only=True)
    categories = sorted(set(p["category"] for p in all_products if p.get("category")))
    brands = sorted(set(p["brand"] for p in all_products if p.get("brand")))

    return render_template(
        "shop/index.html",
        products=products,
        categories=categories,
        brands=brands,
        keyword=keyword,
        selected_category=category,
        selected_brand=brand,
        selected_sort=sort,
        total_products=len(all_products),
    )


@shop_bp.route("/product/<int:product_id>")
def product_detail(product_id: int):
    """Trang chi tiết sản phẩm – so sánh giá với đối thủ."""
    product = get_product_by_id(product_id)
    if not product:
        return render_template("shop/404.html"), 404

    competitor_prices = get_latest_competitor_prices(product_id)

    in_stock = [float(cp["price"]) for cp in competitor_prices if cp["is_in_stock"]]
    price_analysis = {
        "our_price": float(product["current_price"]),
        "min_competitor": min(in_stock) if in_stock else None,
        "max_competitor": max(in_stock) if in_stock else None,
        "avg_competitor": sum(in_stock) / len(in_stock) if in_stock else None,
        "is_cheapest": (
            float(product["current_price"]) <= min(in_stock) if in_stock else True
        ),
        "savings": None,
    }
    if in_stock:
        price_analysis["savings"] = max(in_stock) - float(product["current_price"])

    return render_template(
        "shop/product_detail.html",
        product=product,
        competitor_prices=competitor_prices,
        analysis=price_analysis,
    )


@shop_bp.route("/api/search")
def api_search():
    """API tìm kiếm sản phẩm (cho autocomplete)."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    results = search_products(q)
    return jsonify([{
        "id": p["id"],
        "name": p["name"],
        "brand": p["brand"],
        "price": float(p["current_price"]),
        "image_url": p.get("image_url", ""),
    } for p in results[:8]])
