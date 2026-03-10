"""
Cấu hình chung cho hệ thống Multi-Agent Laptop Store.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Cấu hình cơ sở."""

    # ── Flask ──────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")

    # ── MySQL Database ────────────────────────────────────
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "laptop_shop")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "shop123")
    DB_NAME = os.getenv("DB_NAME", "laptop_pricing")

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
