"""
Cấu hình chung cho hệ thống Multi-Agent Laptop Store.
Hỗ trợ cả local development (.env) và Railway (MYSQL_URL).
"""

import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _parse_mysql_url() -> dict:
    """Parse MYSQL_URL (Railway cung cấp) thành các thành phần riêng lẻ."""
    url = (
        os.getenv("MYSQL_URL")
        or os.getenv("MYSQL_PRIVATE_URL")
        or os.getenv("MYSQL_PUBLIC_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )
    if url:
        print(f"[config] Found DB URL (length={len(url)}, scheme={url.split('://')[0] if '://' in url else '?'})")
    else:
        print("[config] No MYSQL_URL / DATABASE_URL found – falling back to individual env vars")
    if not url:
        return {}
    try:
        p = urlparse(url)
        return {
            "host": p.hostname or "localhost",
            "port": p.port or 3306,
            "user": p.username or "",
            "password": p.password or "",
            "database": p.path.lstrip("/") if p.path else "",
        }
    except Exception:
        return {}


_db = _parse_mysql_url()


class Config:
    """Cấu hình cơ sở."""

    # ── Flask ──────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")

    # ── MySQL Database ────────────────────────────────────
    # Railway cung cấp MYSQL_URL hoặc các biến MYSQL* riêng lẻ.
    # Fallback về giá trị local nếu không có.
    DB_HOST = _db.get("host") or os.getenv("MYSQLHOST", os.getenv("DB_HOST", "localhost"))
    DB_PORT = int(_db.get("port") or os.getenv("MYSQLPORT", os.getenv("DB_PORT", 3306)))
    DB_USER = _db.get("user") or os.getenv("MYSQLUSER", os.getenv("DB_USER", "laptop_shop"))
    DB_PASSWORD = _db.get("password") or os.getenv("MYSQLPASSWORD", os.getenv("DB_PASSWORD", "shop123"))
    DB_NAME = _db.get("database") or os.getenv("MYSQLDATABASE", os.getenv("DB_NAME", "laptop_pricing"))

    print(f"[config] DB → {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── OpenAI (cho CrewAI) ───────────────────────────────
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── Scraping ──────────────────────────────────────────
    SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", 60))
    HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "True").lower() in ("true", "1")

    # ── Business Rules (mặc định) ─────────────────────────
    INVENTORY_THRESHOLD = int(os.getenv("INVENTORY_THRESHOLD", 100))
    OVERSTOCK_DISCOUNT_PERCENT = float(os.getenv("OVERSTOCK_DISCOUNT_PERCENT", 5.0))
    COMPETITOR_OUT_MARKUP_PERCENT = float(
        os.getenv("COMPETITOR_OUT_MARKUP_PERCENT", 10.0)
    )
    HIGH_DEMAND_MARKUP_PERCENT = float(os.getenv("HIGH_DEMAND_MARKUP_PERCENT", 8.0))

    # ── Railway / Production ──────────────────────────────
    PORT = int(os.getenv("PORT", 5000))
