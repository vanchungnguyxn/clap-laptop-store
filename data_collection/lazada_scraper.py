"""
Selenium scraper cho Lazada Vietnam.
Thu thập giá laptop từ lazada.vn.
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


class LazadaScraper(BaseScraper):
    """Thu thập giá sản phẩm laptop từ Lazada."""

    BASE_URL = "https://www.lazada.vn"
    SEARCH_URL = "https://www.lazada.vn/tag/{keyword}/?q={keyword}&catalog_redirect_tag=true"
    COMPETITOR_ID = 2  # ID của Lazada trong bảng competitors

    # CSS selectors (với fallback cho nhiều layout)
    PRICE_SELECTORS = [
        "span.pdp-price",                      # Product detail page
        "span[class*='pdp-price']",             # Alternative PDP
        "span.price-current",                   # Search result
        "span[data-spm-anchor-id*='price']",    # SPM tracking
        "span.currency",                        # Currency span
    ]

    PRODUCT_NAME_SELECTORS = [
        "h1.pdp-mod-product-badge-title",       # PDP title
        "h1[class*='product-title']",           # Alternative
        "span.pdp-mod-product-badge-title",     # Span variant
    ]

    SEARCH_ITEM_SELECTORS = [
        "div[data-qa-locator='product-item']",  # Data attribute
        "div.Bm3ON",                            # Layout 2024
        "div[class*='product-card']",           # Generic
    ]

    def _parse_price(self, price_text: str) -> float | None:
        """
        Chuyển chuỗi giá Lazada thành số.
        Ví dụ: '15.990.000₫' -> 15990000.0
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
        Quét giá một sản phẩm cụ thể trên Lazada.

        Args:
            product_url: URL trang sản phẩm Lazada.

        Returns:
            dict: {"name", "price", "is_in_stock", "url"} hoặc None.
        """
        if not self.driver:
            self.start()

        if not self._safe_get(product_url):
            print(f"❌ Không thể truy cập Lazada: {product_url}")
            return None

        self._scroll_page(2)

        # Lấy tên sản phẩm
        name = self._try_selectors(self.PRODUCT_NAME_SELECTORS)
        if not name:
            name = self.driver.title.replace(" | Lazada.vn", "").strip()

        # Lấy giá
        price_text = self._try_selectors(self.PRICE_SELECTORS)
        price = self._parse_price(price_text) if price_text else None

        # Kiểm tra còn hàng
        is_in_stock = True
        try:
            page_source = self.driver.page_source.lower()
            out_keywords = ["hết hàng", "out of stock", "sold out", "không khả dụng"]
            if any(kw in page_source for kw in out_keywords):
                is_in_stock = False
        except Exception:
            pass

        if price is None:
            print(f"⚠️  Không lấy được giá Lazada: {product_url}")
            return None

        return {
            "name": name or "Unknown Product",
            "price": price,
            "is_in_stock": is_in_stock,
            "url": product_url,
        }

    def search_and_scrape(self, keyword: str) -> list[dict]:
        """
        Tìm kiếm sản phẩm trên Lazada và quét giá.

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
            print(f"❌ Không thể tìm kiếm Lazada: {keyword}")
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
                for sel in ["a[title]", "div[class*='title']", "span[class*='name']"]:
                    try:
                        el = item.find_element(By.CSS_SELECTOR, sel)
                        name = el.get_attribute("title") or el.text.strip()
                        if name:
                            break
                    except NoSuchElementException:
                        continue

                # Giá
                price_text = None
                for sel in ["span.price", "span[class*='price']", "div[class*='price']"]:
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
                print(f"⚠️  Lỗi parse item Lazada: {e}")
                continue

        print(f"📦 Lazada: Tìm thấy {len(results)} sản phẩm cho '{keyword}'")
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
