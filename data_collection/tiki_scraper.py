"""
Selenium scraper cho Tiki Vietnam.
Thu thập giá laptop từ tiki.vn.
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


class TikiScraper(BaseScraper):
    """Thu thập giá sản phẩm laptop từ Tiki."""

    BASE_URL = "https://tiki.vn"
    SEARCH_URL = "https://tiki.vn/search?q={keyword}"
    COMPETITOR_ID = 3  # ID của Tiki trong bảng competitors

    # CSS selectors (với fallback cho nhiều layout)
    PRICE_SELECTORS = [
        "div[class*='product-price'] span",     # PDP price
        "span[class*='price']",                  # Generic price
        "div.flash-sale-price span",             # Flash sale
        "span.product-price__current-price",     # Current price
    ]

    PRODUCT_NAME_SELECTORS = [
        "h1.title",                              # PDP title
        "h1[class*='title']",                    # Alt title
        "span[class*='title']",                  # Span title
    ]

    SEARCH_ITEM_SELECTORS = [
        "a[class*='product-item']",              # Product item link
        "div[class*='product-item']",            # Product item div
        "div[data-view-id='product_list_item']", # Data attribute
    ]

    def _parse_price(self, price_text: str) -> float | None:
        """
        Chuyển chuỗi giá Tiki thành số.
        Ví dụ: '15.990.000 ₫' -> 15990000.0
        """
        if not price_text:
            return None
        cleaned = re.sub(r"[₫đ\s]", "", price_text.strip())
        cleaned = cleaned.replace(".", "").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _try_selectors(self, selectors: list[str], parent=None) -> str | None:
        """Thử nhiều CSS selector, trả về text đầu tiên tìm được."""
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
        Quét giá một sản phẩm cụ thể trên Tiki.

        Args:
            product_url: URL trang sản phẩm Tiki.

        Returns:
            dict: {"name", "price", "is_in_stock", "url"} hoặc None.
        """
        if not self.driver:
            self.start()

        if not self._safe_get(product_url):
            print(f"Khong the truy cap Tiki: {product_url}")
            return None

        self._scroll_page(2)

        # Lấy tên sản phẩm
        name = self._try_selectors(self.PRODUCT_NAME_SELECTORS)
        if not name:
            name = self.driver.title.replace(" | Tiki.vn", "").strip()

        # Lấy giá
        price_text = self._try_selectors(self.PRICE_SELECTORS)
        price = self._parse_price(price_text) if price_text else None

        # Kiểm tra còn hàng
        is_in_stock = True
        try:
            page_source = self.driver.page_source.lower()
            out_keywords = ["hết hàng", "out of stock", "ngừng kinh doanh"]
            if any(kw in page_source for kw in out_keywords):
                is_in_stock = False
        except Exception:
            pass

        if price is None:
            print(f"Khong lay duoc gia Tiki: {product_url}")
            return None

        return {
            "name": name or "Unknown Product",
            "price": price,
            "is_in_stock": is_in_stock,
            "url": product_url,
        }

    def search_and_scrape(self, keyword: str) -> list[dict]:
        """
        Tìm kiếm sản phẩm trên Tiki và quét giá.

        Args:
            keyword: Từ khóa tìm kiếm.

        Returns:
            Danh sách dict sản phẩm.
        """
        if not self.driver:
            self.start()

        results = []
        search_url = self.SEARCH_URL.format(keyword=quote(keyword))

        if not self._safe_get(search_url):
            print(f"Khong the tim kiem Tiki: {keyword}")
            return results

        self._random_delay(3, 5)
        self._scroll_page(3)

        # Tìm product items
        items = []
        for selector in self.SEARCH_ITEM_SELECTORS:
            try:
                items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    break
            except Exception:
                continue

        for item in items[:10]:
            try:
                # Tên sản phẩm
                name = None
                for sel in ["span.name", "h3", "div[class*='name']", "span[class*='name']"]:
                    try:
                        el = item.find_element(By.CSS_SELECTOR, sel)
                        name = el.text.strip()
                        if name:
                            break
                    except NoSuchElementException:
                        continue

                # Giá
                price_text = None
                for sel in ["span[class*='price']", "div[class*='price'] span"]:
                    try:
                        price_text = item.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if price_text:
                            break
                    except NoSuchElementException:
                        continue

                price = self._parse_price(price_text) if price_text else None

                # Link
                url = ""
                try:
                    if item.tag_name == "a":
                        url = item.get_attribute("href") or ""
                    else:
                        link = item.find_element(By.TAG_NAME, "a")
                        url = link.get_attribute("href") or ""
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
                print(f"Loi parse item Tiki: {e}")
                continue

        print(f"Tiki: Tim thay {len(results)} san pham cho '{keyword}'")
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
