"""Flask application factory."""

from flask import Flask
from config import Config


def create_app(config_class=Config):
    """Tạo và cấu hình Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Blueprint: Shop (khách hàng) – prefix /
    from app.routes_shop import shop_bp
    app.register_blueprint(shop_bp)

    # Blueprint: Admin (quản trị) – prefix /admin
    from app.routes_admin import admin_bp
    app.register_blueprint(admin_bp)

    return app
