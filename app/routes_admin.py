"""
Admin Blueprint – Quản lý sản phẩm, nhập hàng, AI gợi ý giá, dashboard.
Bảo vệ bằng đăng nhập: username + password + mã nhân viên.
URL prefix: /admin
"""

import os
import uuid
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, session, g,
)
from werkzeug.utils import secure_filename

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "products")
ALLOWED_IMG = {"png", "jpg", "jpeg", "webp", "gif"}

from database.crud import (
    get_all_products,
    get_product_by_id,
    create_product,
    update_product,
    delete_product,
    delete_all_products,
    hard_delete_product,
    hard_delete_all_products,
    get_latest_competitor_prices,
    get_competitor_price_history,
    get_price_change_history,
    get_active_rules,
    update_business_rule,
    save_competitor_prices_bulk,
    save_ai_scraped_prices,
    update_product_price,
    authenticate_admin,
    get_admin_user_by_id,
    log_admin_activity,
    get_activity_log,
)
from agents.inventory_controller import check_inventory_status
from agents.coordinator import run_pricing_analysis

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ═══════════════════════════════════════════════════════════
#  AUTH HELPERS
# ═══════════════════════════════════════════════════════════

def _current_user() -> dict | None:
    """Lấy user hiện tại từ session (cache trong g)."""
    if "admin_user" not in g:
        uid = session.get("admin_user_id")
        g.admin_user = get_admin_user_by_id(uid) if uid else None
    return g.admin_user


def login_required(f):
    """Decorator: yêu cầu đăng nhập trước khi truy cập."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _current_user():
            flash("Vui lòng đăng nhập để truy cập trang quản trị.", "warning")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


def _log(action_type: str, description: str):
    """Ghi nhật ký hoạt động (shortcut)."""
    user = _current_user()
    if user:
        log_admin_activity(
            user_id=user["id"],
            employee_code=user["employee_code"],
            full_name=user["full_name"],
            action_type=action_type,
            description=description,
            ip_address=request.remote_addr or "",
        )


@admin_bp.before_request
def _inject_user():
    """Đưa user vào g và template context."""
    g.admin_user = None
    uid = session.get("admin_user_id")
    if uid:
        g.admin_user = get_admin_user_by_id(uid)


@admin_bp.context_processor
def _ctx():
    """Inject current_user vào mọi template admin."""
    return {"current_user": g.get("admin_user")}


# ═══════════════════════════════════════════════════════════
#  LOGIN / LOGOUT
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if _current_user():
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        employee_code = request.form.get("employee_code", "").strip().upper()

        user = authenticate_admin(username, password, employee_code)
        if user:
            session["admin_user_id"] = user["id"]
            session.permanent = True
            _log("login", f"Đăng nhập thành công")
            flash(f"Chào mừng {user['full_name']} ({user['employee_code']})!", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Sai tên đăng nhập, mật khẩu hoặc mã nhân viên.", "error")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    _log("logout", "Đăng xuất")
    session.pop("admin_user_id", None)
    flash("Đã đăng xuất.", "success")
    return redirect(url_for("admin.login"))


# ═══════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/")
@login_required
def dashboard():
    """Admin Dashboard – tổng quan hệ thống."""
    try:
        products = get_all_products()
        inventory_status = check_inventory_status()
        recent_changes = get_price_change_history(limit=10)
        rules = get_active_rules()
        return render_template(
            "admin/dashboard.html",
            products=products,
            inventory=inventory_status,
            recent_changes=recent_changes,
            rules=rules,
        )
    except Exception as e:
        return render_template(
            "admin/dashboard.html", error=str(e),
            products=[], inventory={}, recent_changes=[], rules=[],
        )


# ═══════════════════════════════════════════════════════════
#  QUẢN LÝ SẢN PHẨM
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/products")
@login_required
def product_list():
    """Danh sách sản phẩm (quản lý)."""
    products = get_all_products(active_only=False)
    return render_template("admin/product_list.html", products=products)


def _save_upload(file_obj) -> str:
    """Lưu file upload, trả về URL path (hoặc '' nếu không có)."""
    if not file_obj or not file_obj.filename:
        return ""
    ext = file_obj.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMG:
        return ""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:12]}.{ext}"
    file_obj.save(os.path.join(UPLOAD_DIR, fname))
    return f"/static/uploads/products/{fname}"


def _form_detail_fields() -> dict:
    """Trích tất cả field chi tiết sản phẩm từ request.form."""
    keys = ("cpu", "gpu", "ram", "storage", "screen_size", "screen_detail",
            "battery", "weight", "os", "ports", "color", "warranty", "description")
    return {k: request.form.get(k, "").strip() for k in keys}


@admin_bp.route("/products/add", methods=["GET", "POST"])
@login_required
def product_add():
    """Thêm sản phẩm mới – có AI gợi ý giá."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        specs = request.form.get("specs", "").strip()
        cost_price = request.form.get("cost_price", type=float, default=0)
        current_price = request.form.get("current_price", type=float, default=0)
        stock_quantity = request.form.get("stock_quantity", type=int, default=0)
        category = request.form.get("category", "").strip()

        if not name or current_price <= 0:
            flash("Vui lòng nhập tên sản phẩm và giá bán hợp lệ.", "warning")
            return render_template("admin/product_form.html", mode="add",
                                   product=request.form)

        image_url = _save_upload(request.files.get("image"))
        details = _form_detail_fields()

        product_id = create_product(
            name=name, brand=brand, model=model, specs=specs,
            current_price=current_price, cost_price=cost_price,
            stock_quantity=stock_quantity, category=category,
            image_url=image_url, **details,
        )
        if product_id:
            # Lưu giá đối thủ AI đã scrape (nếu có)
            import json as _json
            ai_comp_raw = request.form.get("ai_competitors_json", "")
            if ai_comp_raw:
                try:
                    ai_comp = _json.loads(ai_comp_raw)
                    if ai_comp:
                        save_ai_scraped_prices(product_id, ai_comp)
                except Exception:
                    pass

            _log("add_product", f"Thêm sản phẩm \"{name}\" (ID: {product_id})")
            flash(f"Đã thêm sản phẩm \"{name}\" (ID: {product_id})!", "success")
            return redirect(url_for("admin.product_list"))
        else:
            flash("Lỗi khi thêm sản phẩm.", "error")

    return render_template("admin/product_form.html", mode="add", product={})


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id: int):
    """Sửa sản phẩm."""
    product = get_product_by_id(product_id)
    if not product:
        flash("Không tìm thấy sản phẩm.", "error")
        return redirect(url_for("admin.product_list"))

    if request.method == "POST":
        new_name = request.form.get("name", "").strip()

        image_url = _save_upload(request.files.get("image"))
        if not image_url:
            image_url = product.get("image_url", "") or ""
        details = _form_detail_fields()

        success = update_product(
            product_id=product_id,
            name=new_name,
            brand=request.form.get("brand", "").strip(),
            model=request.form.get("model", "").strip(),
            specs=request.form.get("specs", "").strip(),
            current_price=request.form.get("current_price", type=float),
            cost_price=request.form.get("cost_price", type=float),
            stock_quantity=request.form.get("stock_quantity", type=int),
            category=request.form.get("category", "").strip(),
            image_url=image_url, **details,
        )
        if success:
            _log("edit_product",
                 f"Sửa sản phẩm \"{new_name}\" (ID: {product_id})")
            flash("Đã cập nhật sản phẩm!", "success")
            return redirect(url_for("admin.product_list"))
        else:
            flash("Lỗi khi cập nhật.", "error")

    competitor_prices = get_latest_competitor_prices(product_id)
    return render_template("admin/product_form.html", mode="edit",
                           product=product, competitor_prices=competitor_prices)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def product_delete(product_id: int):
    """Ẩn sản phẩm (soft delete)."""
    product = get_product_by_id(product_id)
    pname = product["name"] if product else f"ID {product_id}"
    if delete_product(product_id):
        _log("hide_product", f"Ẩn sản phẩm \"{pname}\" (ID: {product_id})")
        flash("Đã ẩn sản phẩm.", "success")
    else:
        flash("Lỗi khi ẩn sản phẩm.", "error")
    return redirect(url_for("admin.product_list"))


@admin_bp.route("/products/<int:product_id>/hard-delete", methods=["POST"])
@login_required
def product_hard_delete(product_id: int):
    """Xóa vĩnh viễn sản phẩm (hard delete)."""
    product = get_product_by_id(product_id)
    pname = product["name"] if product else f"ID {product_id}"
    if hard_delete_product(product_id):
        _log("delete_product",
             f"Xóa vĩnh viễn sản phẩm \"{pname}\" (ID: {product_id})")
        flash("Đã xóa vĩnh viễn sản phẩm.", "success")
    else:
        flash("Không thể xóa vĩnh viễn.", "error")
    return redirect(url_for("admin.product_list"))


@admin_bp.route("/products/hard-delete-all", methods=["POST"])
@login_required
def product_hard_delete_all():
    """Xóa vĩnh viễn toàn bộ sản phẩm."""
    affected = hard_delete_all_products()
    if affected > 0:
        _log("delete_all_products",
             f"Xóa vĩnh viễn tất cả sản phẩm ({affected} sp)")
        flash(f"Đã xóa vĩnh viễn {affected} sản phẩm.", "success")
    else:
        flash("Không có sản phẩm nào để xóa.", "warning")
    return redirect(url_for("admin.product_list"))


@admin_bp.route("/products/delete-all", methods=["POST"])
@login_required
def product_delete_all():
    """Ẩn toàn bộ sản phẩm (soft delete hàng loạt)."""
    affected = delete_all_products()
    if affected > 0:
        _log("hide_all_products",
             f"Ẩn tất cả sản phẩm ({affected} sp)")
        flash(f"Đã ẩn {affected} sản phẩm.", "success")
    else:
        flash("Không có sản phẩm nào để ẩn.", "warning")
    return redirect(url_for("admin.product_list"))


# ═══════════════════════════════════════════════════════════
#  NHẬT KÝ HOẠT ĐỘNG (read-only)
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/activity-log")
@login_required
def activity_log():
    """Trang nhật ký hoạt động admin."""
    logs = get_activity_log(limit=500)
    return render_template("admin/activity_log.html", logs=logs)


# ═══════════════════════════════════════════════════════════
#  SO SÁNH GIÁ / LỊCH SỬ GIÁ
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/price-comparison")
@login_required
def price_comparison():
    products = get_all_products()
    comparison_data = []
    for product in products:
        competitor_prices = get_latest_competitor_prices(product["id"])
        comparison_data.append({
            "product": product,
            "competitor_prices": competitor_prices,
        })
    return render_template("admin/price_comparison.html",
                           comparison_data=comparison_data)


@admin_bp.route("/price-history")
@login_required
def price_history():
    product_id = request.args.get("product_id", type=int)
    changes = get_price_change_history(product_id=product_id, limit=100)
    products = get_all_products()
    return render_template("admin/price_history.html",
                           changes=changes, products=products,
                           selected_product_id=product_id)


# ═══════════════════════════════════════════════════════════
#  CÀI ĐẶT
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/settings")
@login_required
def settings():
    rules = get_active_rules()
    return render_template("admin/settings.html", rules=rules)


@admin_bp.route("/api/settings", methods=["POST"])
@login_required
def api_update_settings():
    """API: Cập nhật quy tắc kinh doanh (AJAX, realtime)."""
    data = request.get_json(silent=True) or {}
    rule_id = data.get("rule_id")
    inventory_threshold = data.get("inventory_threshold")
    discount_percent = data.get("discount_percent")
    competitor_out_markup = data.get("competitor_out_markup")
    high_demand_markup = data.get("high_demand_markup")

    if not all(v is not None for v in [rule_id, inventory_threshold,
                                        discount_percent, competitor_out_markup,
                                        high_demand_markup]):
        return jsonify({"success": False, "error": "Thiếu dữ liệu"}), 400

    success = update_business_rule(
        rule_id=int(rule_id),
        inventory_threshold=int(inventory_threshold),
        discount_percent=float(discount_percent),
        competitor_out_markup=float(competitor_out_markup),
        high_demand_markup=float(high_demand_markup),
    )
    if success:
        _log("update_settings", "Cập nhật quy tắc kinh doanh")
    return jsonify({"success": success})


# ═══════════════════════════════════════════════════════════
#  API – AI GỢI Ý GIÁ + CHẠY PHÂN TÍCH
# ═══════════════════════════════════════════════════════════

@admin_bp.route("/api/ai-suggest-price", methods=["POST"])
@login_required
def api_ai_suggest_price():
    """
    API: AI tìm giá từ Google → vào từng trang lấy giá + logo.
    Input JSON: {"product_name": str, "brand": str, "cost_price": float}
    """
    data = request.get_json(silent=True) or {}
    product_name = data.get("product_name", "")
    brand = data.get("brand", "")
    cost_price = data.get("cost_price", 0)
    product_id = data.get("product_id")

    if not product_name:
        return jsonify({"success": False, "error": "Thiếu tên sản phẩm"}), 400

    from data_collection.quick_price_check import fetch_all_competitor_prices

    market = fetch_all_competitor_prices(product_name, brand=brand, limit=8)

    results = market.get("results", [])
    all_prices = market.get("all_prices", [])
    stats = market.get("stats", {})

    if all_prices:
        avg_price = stats["avg_price"]
        min_price = stats["min_price"]
        max_price = stats["max_price"]

        suggested_price = round(avg_price * 0.97, -3)

        if cost_price > 0:
            min_margin = cost_price * 1.08
            if suggested_price < min_margin:
                suggested_price = round(min_margin, -3)

        sites = ", ".join(set(r["site_name"] for r in results))
        strategy = "competitive"
        reason = (
            f"Đã quét giá từ {len(results)} trang web ({sites}). "
            f"Giá: {min_price:,.0f}₫ – {max_price:,.0f}₫ (TB: {avg_price:,.0f}₫). "
            f"Gợi ý giá thấp hơn ~3% để cạnh tranh."
        )
    else:
        if cost_price > 0:
            suggested_price = round(cost_price * 1.25, -3)
            reason = "Không tìm thấy giá trên web. Gợi ý lãi 25% trên giá vốn."
        else:
            suggested_price = 0
            reason = "Không tìm thấy giá. Vui lòng nhập giá vốn để AI gợi ý."
        avg_price = min_price = max_price = None
        strategy = "margin_based"

    # Lưu giá đối thủ vào DB nếu có product_id (edit mode)
    if product_id and results:
        save_ai_scraped_prices(int(product_id), results)

    _log("ai_suggest_price", f"Gợi ý giá AI cho \"{product_name}\"")

    return jsonify({
        "success": True,
        "suggested_price": suggested_price,
        "strategy": strategy,
        "reason": reason,
        "market_data": {
            "avg_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "result_count": len(results),
        },
        "competitors": results,
    })


@admin_bp.route("/api/save-competitor-prices", methods=["POST"])
@login_required
def api_save_competitor_prices():
    """API: Lưu giá đối thủ đã scrape cho product (dùng sau khi add product)."""
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    competitors = data.get("competitors", [])
    if not product_id or not competitors:
        return jsonify({"success": False, "error": "Thiếu dữ liệu"}), 400
    ok = save_ai_scraped_prices(int(product_id), competitors)
    return jsonify({"success": ok})


@admin_bp.route("/api/ai-autofill-specs", methods=["POST"])
@login_required
def api_ai_autofill_specs():
    """API: AI tra cứu thông số kỹ thuật sản phẩm từ web."""
    data = request.get_json(silent=True) or {}
    product_name = data.get("product_name", "").strip()

    if not product_name:
        return jsonify({"success": False, "error": "Thiếu tên sản phẩm"}), 400

    from data_collection.spec_scraper import fetch_product_specs

    result = fetch_product_specs(product_name)

    if result["success"]:
        _log("ai_autofill_specs",
             f"AI tự điền thông số cho \"{product_name}\" từ {result['source']}")

    return jsonify(result)


@admin_bp.route("/api/run-analysis", methods=["POST"])
@login_required
def api_run_analysis():
    """API: Chạy Multi-Agent phân tích giá."""
    try:
        result = run_pricing_analysis()
        _log("run_analysis", f"Chạy phân tích AI – {result['price_changes_applied']} thay đổi giá")
        return jsonify({"success": True, "data": {
            "total_products": result["total_products"],
            "price_changes_applied": result["price_changes_applied"],
            "overstock_products": result["overstock_products"],
            "timestamp": result["timestamp"],
        }})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/products")
@login_required
def api_products():
    products = get_all_products()
    for p in products:
        if p.get("current_price"):
            p["current_price"] = float(p["current_price"])
        if p.get("cost_price"):
            p["cost_price"] = float(p["cost_price"])
    return jsonify(products)
