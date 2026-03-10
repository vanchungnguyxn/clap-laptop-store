"""
Base class cho tất cả scraper.
Cung cấp khởi tạo Selenium WebDriver, xử lý anti-bot, retry logic.
"""

import time
import random
from abc import ABC, abstractmethod

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager
from fake_useragent import UserAgent

from config import Config


class BaseScraper(ABC):
    """
    Lớp cơ sở cho việc thu thập dữ liệu giá.
    Xử lý: khởi tạo driver, anti-detection, retry, đóng driver.
    """

    MAX_RETRIES = 3
    PAGE_LOAD_TIMEOUT = 30

    def __init__(self):
        self.driver = None
        self.wait = None

    def _create_driver(self) -> webdriver.Chrome:
        """Tạo Chrome WebDriver với các tùy chọn chống phát hiện bot."""
        options = Options()

        if Config.HEADLESS_BROWSER:
            options.add_argument("--headless=new")

        # Chống phát hiện bot
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Hiệu suất
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # User-Agent ngẫu nhiên
        try:
            ua = UserAgent()
            options.add_argument(f"--user-agent={ua.random}")
        except Exception:
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

        # Tắt thông báo & hình ảnh để tăng tốc
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.images": 2,
        }
        options.add_experimental_option("prefs", prefs)

        from data_collection.quick_price_check import _get_chromedriver_path
        service = Service(_get_chromedriver_path())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(self.PAGE_LOAD_TIMEOUT)

        # Che giấu webdriver flag
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'languages', {get: () => ['vi-VN', 'vi', 'en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            """
            },
        )

        return driver

    def start(self):
        """Khởi động WebDriver."""
        if self.driver is None:
            self.driver = self._create_driver()
            self.wait = WebDriverWait(self.driver, 15)
        return self

    def stop(self):
        """Đóng WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
                self.wait = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Delay ngẫu nhiên để tránh bị phát hiện là bot."""
        time.sleep(random.uniform(min_sec, max_sec))

    def _safe_get(self, url: str) -> bool:
        """Truy cập URL với retry logic."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.driver.get(url)
                self._random_delay(2, 4)
                return True
            except TimeoutException:
                print(f"⏱️  Timeout lần {attempt}/{self.MAX_RETRIES}: {url}")
                if attempt == self.MAX_RETRIES:
                    return False
            except WebDriverException as e:
                print(f"🌐 Lỗi WebDriver lần {attempt}/{self.MAX_RETRIES}: {e}")
                if attempt == self.MAX_RETRIES:
                    return False
            self._random_delay(3, 6)
        return False

    def _scroll_page(self, scroll_count: int = 3):
        """Cuộn trang để load lazy content."""
        for _ in range(scroll_count):
            self.driver.execute_script(
                "window.scrollBy(0, window.innerHeight);"
            )
            self._random_delay(0.5, 1.5)

    @abstractmethod
    def scrape_product_price(self, product_url: str) -> dict | None:
        """
        Quét giá một sản phẩm cụ thể.

        Returns:
            dict: {"name": str, "price": float, "is_in_stock": bool, "url": str}
            hoặc None nếu thất bại.
        """
        pass

    @abstractmethod
    def search_and_scrape(self, keyword: str) -> list[dict]:
        """
        Tìm kiếm sản phẩm theo từ khoá và quét giá.

        Returns:
            list[dict]: Danh sách sản phẩm tìm thấy.
        """
        pass
