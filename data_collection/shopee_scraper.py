"""
Selenium scraper cho Shopee Vietnam.
Thu thập giá laptop từ shopee.vn.
"""

import re
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)

from data_collection.scraper_base import BaseScraper
from database.crud import save_competitor_price


class ShopeeScraper(BaseScraper):
    """Thu thập giá sản phẩm laptop từ Shopee."""

    BASE_URL = "https://shopee.vn"
    SEARCH_URL = "https://shopee.vn/search?keyword={keyword}"
    COMPETITOR_ID = 1  # ID của Shopee trong bảng competitors

    # Danh sách CSS selector (fallback khi cấu trúc HTML thay đổi)
    PRICE_SELECTORS = [
        "div.pqTWkA",                          # Layout 2024-2025
        "div.HLQqkk span",                     # Layout cũ hơn
        "div[class*='price'] span",             # Generic price class
        "div.product-price span",               # Alternative
        "span[class*='price']",                 # Fallback
    ]

    PRODUCT_NAME_SELECTORS = [
        "div.attM6y span",                      # Layout 2024-2025
        "div[class*='product-name'] span",      # Alternative
        "h1.product-name",                      # Direct name tag
        "span[class*='name']",                  # Generic fallback
    ]

    STOCK_SELECTORS = [
        "div.G3mfhx",                           # Quantity section
        "div[class*='stock']",                  # Generic stock
        "div[class*='quantity']",               # Quantity indicator
    ]

    SEARCH_ITEM_SELECTORS = [
        "div.shopee-search-item-result__item",  # Layout 2024
        "li.shopee-search-item-result__item",   # Layout cũ
        "div[data-sqe='item']",                 # Data attribute
    ]

    def _parse_price(self, price_text: str) -> float | None:
        """
        Chuyển đổi chuỗi giá Shopee thành số.
        Ví dụ: '15.990.000' -> 15990000.0
                '₫15.990.000' -> 15990000.0
                '15,990,000' -> 15990000.0
        """
        if not price_text:
            return None
        # Loại bỏ ký tự tiền tệ và khoảng trắng
        cleaned = re.sub(r"[₫đ\s]", "", price_text.strip())
        # Thử parse với dấu chấm (VN format)
        cleaned = cleaned.replace(".", "").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _try_selectors(self, selectors: list[str], parent=None) -> str | None:
        """Thử nhiều CSS selector, trả về text của phần tử đầu tiên tìm thấy."""
        target = parent or self.driver
        for selector in selectors:
            try:
                element = target.find_element(By.CSS_SELECTOR, selector)
                text = element.text.strip()
                if text:
                    return text
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        return None

    def scrape_product_price(self, product_url: str) -> dict | None:
        """
        Quét giá một sản phẩm cụ thể trên Shopee.

        Args:
            product_url: URL trang sản phẩm Shopee.

        Returns:
            dict với keys: name, price, is_in_stock, url
            hoặc None nếu thất bại.
        """
        if not self.driver:
            self.start()

        if not self._safe_get(product_url):
            print(f"❌ Không thể truy cập: {product_url}")
            return None

        # Cuộn trang để load dynamic content
        self._scroll_page(2)

        # Lấy tên sản phẩm
        name = self._try_selectors(self.PRODUCT_NAME_SELECTORS)
        if not name:
            # Fallback: lấy từ title page
            name = self.driver.title.replace(" | Shopee Việt Nam", "").strip()

        # Lấy giá
        price_text = self._try_selectors(self.PRICE_SELECTORS)
        price = self._parse_price(price_text) if price_text else None

        # Kiểm tra tình trạng còn hàng
        is_in_stock = True
        try:
            page_source = self.driver.page_source.lower()
            out_of_stock_keywords = ["hết hàng", "sold out", "không còn hàng"]
            if any(kw in page_source for kw in out_of_stock_keywords):
                is_in_stock = False
        except Exception:
            pass

        if price is None:
            print(f"⚠️  Không lấy được giá từ: {product_url}")
            return None

        return {
            "name": name or "Unknown Product",
            "price": price,
            "is_in_stock": is_in_stock,
            "url": product_url,
        }

    def search_and_scrape(self, keyword: str) -> list[dict]:
        """
        Tìm kiếm sản phẩm trên Shopee theo từ khóa và quét giá.

        Args:
            keyword: Từ khóa tìm kiếm (ví dụ: "laptop dell inspiron 15").

        Returns:
            Danh sách dict sản phẩm tìm được.
        """
        if not self.driver:
            self.start()

        results = []
        search_url = self.SEARCH_URL.format(keyword=quote(keyword))

        if not self._safe_get(search_url):
            print(f"❌ Không thể tìm kiếm trên Shopee: {keyword}")
            return results

        # Đợi trang load kết quả
        self._random_delay(3, 5)
        self._scroll_page(3)

        # Tìm các item trong kết quả tìm kiếm
        items = []
        for selector in self.SEARCH_ITEM_SELECTORS:
            try:
                items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    break
            except Exception:
                continue

        for item in items[:10]:  # Giới hạn 10 sản phẩm đầu
            try:
                # Lấy tên sản phẩm
                name = None
                for sel in ["div.ie3A\\+n", "div[data-sqe='name']", "div.yQmmFK"]:
                    try:
                        name = item.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if name:
                            break
                    except NoSuchElementException:
                        continue

                # Lấy giá
                price_text = None
                for sel in ["span.ZEgDH9", "div.vioxXd", "span[class*='price']"]:
                    try:
                        price_text = item.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if price_text:
                            break
                    except NoSuchElementException:
                        continue

                price = self._parse_price(price_text) if price_text else None

                # Lấy link sản phẩm
                url = ""
                try:
                    link_el = item.find_element(By.TAG_NAME, "a")
                    url = link_el.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = self.BASE_URL + url
                except NoSuchElementException:
                    pass

                if name and price:
                    results.append({
                        "name": name,
                        "price": price,
                        "is_in_stock": True,
                        "url": url,
                    })

            except StaleElementReferenceException:
                continue
            except Exception as e:
                print(f"⚠️  Lỗi parse item Shopee: {e}")
                continue

        print(f"📦 Shopee: Tìm thấy {len(results)} sản phẩm cho '{keyword}'")
        return results

    def scrape_and_save(self, product_id: int, product_url: str) -> bool:
        """Quét giá và lưu vào database."""
        result = self.scrape_product_price(product_url)
        if result:
            return save_competitor_price(
                product_id=product_id,
                competitor_id=self.COMPETITOR_ID,
                competitor_product_name=result["name"],
                competitor_url=result["url"],
                price=result["price"],
                is_in_stock=result["is_in_stock"],
            )
        return False
