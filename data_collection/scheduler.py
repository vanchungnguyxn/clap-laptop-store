"""
Scheduler tự động thu thập giá đối thủ theo chu kỳ.
Sử dụng APScheduler để lập lịch chạy scraper.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Config


scheduler = BackgroundScheduler()


def run_scraping_job():
    """
    Job thu thập giá đối thủ.
    Chạy tất cả scraper cho tất cả sản phẩm được theo dõi.
    """
    from data_collection.shopee_scraper import ShopeeScraper
    from data_collection.lazada_scraper import LazadaScraper
    from data_collection.tiki_scraper import TikiScraper
    from database.crud import get_all_products

    print("Bat dau thu thap gia doi thu...")

    products = get_all_products()

    # ── Shopee: https://shopee.vn/search?keyword=... ──
    try:
        with ShopeeScraper() as shopee:
            for product in products:
                keyword = f"{product['brand']} {product['model']}"
                results = shopee.search_and_scrape(keyword)
                print(f"  Shopee - {product['name']}: {len(results)} ket qua")
    except Exception as e:
        print(f"Loi scrape Shopee: {e}")

    # ── Lazada: https://www.lazada.vn/tag/.../?q=... ──
    try:
        with LazadaScraper() as lazada:
            for product in products:
                keyword = f"{product['brand']} {product['model']}"
                results = lazada.search_and_scrape(keyword)
                print(f"  Lazada - {product['name']}: {len(results)} ket qua")
    except Exception as e:
        print(f"Loi scrape Lazada: {e}")

    # ── Tiki: https://tiki.vn/search?q=... ──
    try:
        with TikiScraper() as tiki:
            for product in products:
                keyword = f"{product['brand']} {product['model']}"
                results = tiki.search_and_scrape(keyword)
                print(f"  Tiki - {product['name']}: {len(results)} ket qua")
    except Exception as e:
        print(f"Loi scrape Tiki: {e}")

    print("Hoan tat thu thap gia doi thu!")

    # Sau khi scrape xong, chạy Multi-Agent để phân tích
    try:
        from agents.coordinator import run_pricing_analysis
        run_pricing_analysis()
    except Exception as e:
        print(f"❌ Lỗi chạy agent phân tích giá: {e}")


def start_scheduler():
    """Khởi động scheduler thu thập dữ liệu."""
    scheduler.add_job(
        func=run_scraping_job,
        trigger=IntervalTrigger(minutes=Config.SCRAPE_INTERVAL_MINUTES),
        id="scraping_job",
        name="Thu thập giá đối thủ",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[Scheduler] Da khoi dong – Chu ky: {Config.SCRAPE_INTERVAL_MINUTES} phut")


def stop_scheduler():
    """Dừng scheduler."""
    scheduler.shutdown(wait=False)
    print("⏹️  Scheduler đã dừng.")
