"""
Quick Price Check – Lấy giá realtime từ Google Search.

Flow:
1. Search Google: "{tên sản phẩm} giá bán"
2. Lấy top 10 kết quả (URL + title)
3. Vào từng trang, trích xuất giá
4. Trả về: tên web, logo (favicon), giá, link

Sử dụng Selenium headless cho cả Google lẫn các trang kết quả.
"""

import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse

MIN_LAPTOP_PRICE = 3_000_000
MIN_REASONABLE_PRICE = 5_000_000
MAX_REASONABLE_PRICE = 200_000_000

_NEGATIVE_KEYWORDS = {
    # Linh kiện / phụ kiện dễ dính nhầm
    "linh kiện", "linh kien", "phụ kiện", "phu kien", "phụ kiện laptop", "phu kien laptop",
    "sạc", "sac", "charger", "adapter", "nguồn", "nguon",
    "pin", "battery", "bàn phím", "ban phim", "keyboard",
    "chuột", "chuot", "mouse", "tai nghe", "headphone",
    "ram", "ssd", "hdd", "ổ cứng", "o cung", "ổ cứng laptop", "o cung laptop",
    "màn hình", "man hinh", "screen", "lcd",
    "card đồ họa", "card do hoa", "vga", "gpu",
    "case", "vỏ", "vo", "tản nhiệt", "tan nhiet", "cooler",
}

# Selenium driver (thread-local)
_thread_local = threading.local()


def _new_driver():
    """Tạo Chrome headless driver mới (không tái sử dụng giữa threads)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )
    opts.add_argument("--lang=vi-VN")
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)

    # Stealth
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opts.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(15)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    })
    return driver


def _get_driver():
    """Lấy driver cho thread hiện tại (tạo mới nếu chưa có)."""
    driver = getattr(_thread_local, "driver", None)
    if driver is not None:
        try:
            _ = driver.title
            return driver
        except Exception:
            _thread_local.driver = None
    driver = _new_driver()
    _thread_local.driver = driver
    return driver


def _parse_vn_price(text: str) -> float:
    """
    Parse chuỗi giá VN → số (Clean & Split).

    Tìm các cụm số có cấu trúc tiền tệ VN (VD: 24.990.000 hoặc 24,990,000),
    lọc theo range hợp lý, và lấy giá **đầu tiên** xuất hiện (web thường đặt
    giá khuyến mãi / giá hiện tại trước giá cũ).
    """
    if not text:
        return 0.0

    text = re.sub(r"\s+", " ", str(text))

    candidates = re.findall(r"\b\d{1,3}(?:[.,]\d{3}){1,3}\b", text)

    for c in candidates:
        num = int(c.replace(".", "").replace(",", ""))
        if MIN_REASONABLE_PRICE < num < MAX_REASONABLE_PRICE:
            return float(num)

    return 0.0


def _get_domain(url: str) -> str:
    """Lấy domain từ URL. VD: 'https://www.lazada.vn/abc' → 'lazada.vn'"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _get_site_name(domain: str) -> str:
    """Chuyển domain → tên hiển thị."""
    name_map = {
        "shopee.vn": "Shopee",
        "lazada.vn": "Lazada",
        "tiki.vn": "Tiki",
        "gearvn.com": "GearVN",
        "cellphones.com.vn": "CellphoneS",
        "phongvu.vn": "Phong Vũ",
        "fptshop.com.vn": "FPT Shop",
        "nguyenkim.com": "Nguyễn Kim",
        "hacom.vn": "Hacom",
        "thegioididong.com": "Thế Giới Di Động",
        "dienmayxanh.com": "Điện Máy Xanh",
        "anphatpc.com.vn": "An Phát",
        "memoryzone.com.vn": "Memory Zone",
        "phucanh.vn": "Phúc Anh",
        "hanoicomputer.vn": "Hanoi Computer",
        "laptopworld.vn": "Laptop World",
    }
    return name_map.get(domain, domain.split(".")[0].capitalize())


def _get_favicon_url(domain: str) -> str:
    """Lấy URL favicon/logo qua Google Favicon Service."""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=32"


def _is_negative_result(title: str, snippet: str = "") -> bool:
    """Lọc kết quả phụ kiện/linh kiện để tránh lấy nhầm khi search tên máy."""
    hay = f"{title} {snippet}".lower()
    return any(kw in hay for kw in _NEGATIVE_KEYWORDS)



# ═══════════════════════════════════════════════════════════
#  BƯỚC 1: SEARCH GOOGLE
# ═══════════════════════════════════════════════════════════

def _google_search(keyword: str, max_results: int = 10) -> list[dict]:
    """
    Search Google và trả về danh sách kết quả.
    Returns: [{"title": str, "url": str, "snippet": str, "domain": str}, ...]
    """
    results = []
    driver = _get_driver()

    query = f"{keyword} giá bán"
    url = f"https://www.google.com/search?q={quote(query)}&hl=vi&gl=vn&num={max_results}"

    try:
        print(f"[Google] Searching: {query}")
        driver.get(url)
        time.sleep(2)

        from selenium.webdriver.common.by import By

        # Consent page (nếu có)
        try:
            consent = driver.find_elements(By.CSS_SELECTOR,
                "button[id='L2AGLb'], form[action*='consent'] button")
            if consent:
                consent[0].click()
                time.sleep(1)
        except Exception:
            pass

        # Lấy search results
        result_elements = driver.find_elements(By.CSS_SELECTOR, "div.g, div[data-hveid]")

        for el in result_elements:
            try:
                # URL
                link_el = el.find_element(By.CSS_SELECTOR, "a[href^='http']")
                link_url = link_el.get_attribute("href") or ""

                # Bỏ Google internal links
                if "google.com" in link_url or not link_url.startswith("http"):
                    continue

                # Title
                title = ""
                for sel in ["h3", "a h3", "div[role='heading']"]:
                    try:
                        title = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if title:
                            break
                    except Exception:
                        continue

                # Snippet (có thể chứa giá)
                snippet = ""
                for sel in ["div.VwiC3b", "span.aCOpRe", "div[data-sncf]"]:
                    try:
                        snippet = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if snippet:
                            break
                    except Exception:
                        continue

                domain = _get_domain(link_url)
                if title and domain:
                    results.append({
                        "title": title,
                        "url": link_url,
                        "snippet": snippet,
                        "domain": domain,
                    })

            except Exception:
                continue

        print(f"[Google] Found {len(results)} results")

    except Exception as e:
        print(f"[Google] Error: {e}")

    return results[:max_results]


# ═══════════════════════════════════════════════════════════
#  BƯỚC 2: VÀO TỪNG TRANG LẤY GIÁ
# ═══════════════════════════════════════════════════════════

def _extract_price_from_page(url: str) -> float:
    """
    Truy cập URL và trích xuất giá sản phẩm.

    Thứ tự ưu tiên:
      P1 – Metadata:  JSON-LD (offers.price) → meta[product:price:amount]
      P2 – Specific CSS selectors (current/sale price, loại trừ old-price)
      P3 – Regex giá VN trên visible text (fallback)
    """
    driver = _get_driver()
    try:
        driver.get(url)
        time.sleep(3)

        from selenium.webdriver.common.by import By
        import json as _json

        # ── P1: JSON-LD structured data (offers.price) ────────
        try:
            scripts = driver.find_elements(
                By.CSS_SELECTOR, "script[type='application/ld+json']")
            for sc in scripts:
                try:
                    raw = _json.loads(sc.get_attribute("innerHTML"))
                    items = raw if isinstance(raw, list) else [raw]
                    for item in items:
                        offers = item.get("offers", item.get("Offers", {}))
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        for key in ("price", "lowPrice"):
                            p = offers.get(key)
                            if p is not None:
                                price = _parse_vn_price(str(p))
                                if price >= MIN_LAPTOP_PRICE:
                                    return price
                except Exception:
                    continue
        except Exception:
            pass

        # ── P1b: meta tag price ───────────────────────────────
        meta_selectors = [
            "meta[property='product:price:amount']",
            "meta[property='og:price:amount']",
            "meta[itemprop='price']",
        ]
        for ms in meta_selectors:
            try:
                meta = driver.find_element(By.CSS_SELECTOR, ms)
                price = _parse_vn_price(meta.get_attribute("content") or "")
                if price >= MIN_LAPTOP_PRICE:
                    return price
            except Exception:
                continue

        # ── P2: Specific CSS selectors (loại trừ old-price) ──
        current_price_selectors = [
            ".current-price",
            ".giaban",
            "span.price-new",
            "[class*='product-price'] [class*='current']",
            "[class*='price-current']",
            "[class*='sale-price']",
            "[class*='special-price']",
            "[class*='final-price']",
            "[class*='box-price'] [class*='current']",
            "[class*='pro-price']",
            "span.pdp-price",
            "span.product-price__current-price",
            "div.pqTWkA",
            "[itemprop='price']",
            "[data-price]",
        ]
        generic_price_selectors = [
            "[class*='product-price']",
            "[class*='box-price']",
            "[class*='detail'] [class*='price']",
            "span.price",
            "p.price",
            "div.price",
        ]

        for sel in current_price_selectors + generic_price_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    cls = (el.get_attribute("class") or "").lower()
                    if any(neg in cls for neg in
                           ("old-price", "discount-amount", "original",
                            "list-price", "compare-price")):
                        continue

                    text = el.text.strip()
                    price = _parse_vn_price(text)
                    if price >= MIN_LAPTOP_PRICE:
                        return price

                    dp = el.get_attribute("data-price") or el.get_attribute("content")
                    if dp:
                        price = _parse_vn_price(dp)
                        if price >= MIN_LAPTOP_PRICE:
                            return price
            except Exception:
                continue

        # ── P3: Regex giá VN trong visible text (fallback) ────
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            price = _parse_vn_price(body_text)
            if price >= MIN_LAPTOP_PRICE:
                return price
        except Exception:
            pass

    except Exception as e:
        print(f"[Extract] Error on {url[:50]}: {e}")

    return 0.0


def _extract_price_from_page_isolated(url: str) -> float:
    """
    Dùng cho multithreading: tạo driver riêng, extract, rồi quit.
    Tránh chia sẻ driver giữa threads.
    """
    driver = None
    try:
        driver = _new_driver()
        # tạm gán vào thread_local để _extract_price_from_page dùng đúng driver
        _thread_local.driver = driver
        return _extract_price_from_page(url)
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        _thread_local.driver = None


# ═══════════════════════════════════════════════════════════
#  BƯỚC 3: HÀM TỔNG HỢP
# ═══════════════════════════════════════════════════════════

def _extract_model_keywords(product_name: str, brand: str = "") -> list[str]:
    """Trích model keywords để lọc kết quả."""
    stop = {"laptop", "gaming", "máy", "tính", "xách", "tay",
            "notebook", "pc", "new", "mới", "chính", "hãng",
            brand.lower() if brand else ""}
    stop.discard("")
    words = re.findall(r'[A-Za-z0-9]+', product_name)
    kws = []
    for w in words:
        wl = w.lower()
        if wl in stop or len(wl) < 2:
            continue
        if len(wl) > 8 and any(c.isdigit() for c in wl) and any(c.isalpha() for c in wl):
            continue
        kws.append(wl)
    return kws


def _score(result_title: str, model_kws: list[str], brand: str) -> float:
    """Tính điểm khớp."""
    name = result_title.lower()
    if brand and brand.lower() not in name:
        return 0.0
    if not model_kws:
        return 0.3 if brand and brand.lower() in name else 0.0
    matched = sum(1 for kw in model_kws if kw in name)
    return round(matched / len(model_kws), 3)


def fetch_all_competitor_prices(keyword: str, brand: str = "",
                                limit: int = 8) -> dict:
    """
    Tìm giá sản phẩm từ Google → vào từng trang lấy giá.

    Returns:
        dict: {
            "results": [{
                "site_name": str,
                "domain": str,
                "favicon_url": str,
                "product_title": str,
                "price": float,
                "url": str,
                "match_score": float,
            }, ...],
            "all_prices": [float],
            "stats": {...},
        }
    """
    model_kws = _extract_model_keywords(keyword, brand)
    print(f"[PriceCheck] Product: '{keyword}' | Brand: '{brand}' | Keywords: {model_kws}")

    # ── Bước 1: Google Search ─────────────────────────────
    google_results = _google_search(keyword, max_results=limit + 5)

    # ── Bước 2: Chuẩn hoá + lọc kết quả ───────────────────
    filtered = []
    visited_domains = set()
    skip_domains = {"google.com", "youtube.com", "wikipedia.org", "facebook.com", "tiktok.com", "reddit.com"}

    for gr in google_results:
        domain = gr.get("domain", "")
        if not domain or domain in visited_domains:
            continue
        if any(sd in domain for sd in skip_domains):
            continue
        if _is_negative_result(gr.get("title", ""), gr.get("snippet", "")):
            continue
        visited_domains.add(domain)
        filtered.append(gr)

    # ── Bước 3: Lấy giá (ưu tiên snippet, còn lại crawl song song) ──
    price_results: list[dict] = []
    to_visit: list[dict] = []

    for gr in filtered:
        # Kiểm tra relevance từ title/snippet
        score = max(_score(gr.get("title", ""), model_kws, brand),
                    _score(gr.get("snippet", ""), model_kws, brand))

        snippet = gr.get("snippet", "") or ""
        snippet_price = _parse_vn_price(snippet)
        if snippet_price >= MIN_LAPTOP_PRICE:
            print(f"[PriceCheck] Snippet price from {gr['domain']}: {snippet_price:,.0f}")
            price_results.append({
                "site_name": _get_site_name(gr["domain"]),
                "domain": gr["domain"],
                "favicon_url": _get_favicon_url(gr["domain"]),
                "product_title": gr.get("title", ""),
                "price": snippet_price,
                "url": gr.get("url", ""),
                "match_score": score,
            })
        else:
            to_visit.append({**gr, "match_score": score})

        if len(price_results) >= limit:
            break

    if len(price_results) < limit and to_visit:
        # Chạy song song 3-5 browser để tăng tốc
        remaining = limit - len(price_results)
        candidates = to_visit[: max(remaining * 2, remaining)]
        max_workers = min(5, max(3, remaining), len(candidates))

        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for gr in candidates:
                futures[ex.submit(_extract_price_from_page_isolated, gr["url"])] = gr

            for fut in as_completed(futures):
                gr = futures[fut]
                try:
                    page_price = fut.result()
                except Exception:
                    continue

                if page_price >= MIN_LAPTOP_PRICE:
                    price_results.append({
                        "site_name": _get_site_name(gr["domain"]),
                        "domain": gr["domain"],
                        "favicon_url": _get_favicon_url(gr["domain"]),
                        "product_title": gr.get("title", ""),
                        "price": page_price,
                        "url": gr.get("url", ""),
                        "match_score": gr.get("match_score", 0.0),
                    })

                if len(price_results) >= limit:
                    break

    # Sắp xếp theo match_score giảm dần
    price_results.sort(key=lambda x: x["match_score"], reverse=True)

    # ── Stats ─────────────────────────────────────────────
    all_prices = [r["price"] for r in price_results]
    stats = {
        "min_price": min(all_prices) if all_prices else None,
        "max_price": max(all_prices) if all_prices else None,
        "avg_price": sum(all_prices) / len(all_prices) if all_prices else None,
        "total_results": len(price_results),
    }

    if stats["avg_price"]:
        sites = ", ".join(set(r["site_name"] for r in price_results))
        print(f"[PriceCheck] OK: {len(price_results)} gia tu {sites}")
        print(f"[PriceCheck] Min: {stats['min_price']:,.0f} | "
              f"Avg: {stats['avg_price']:,.0f} | Max: {stats['max_price']:,.0f}")
    else:
        print(f"[PriceCheck] Khong tim thay gia")

    return {
        "keyword": keyword,
        "results": price_results,
        "all_prices": all_prices,
        "stats": stats,
    }


def cleanup_driver():
    """Đóng Selenium driver."""
    driver = getattr(_thread_local, "driver", None)
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        _thread_local.driver = None
