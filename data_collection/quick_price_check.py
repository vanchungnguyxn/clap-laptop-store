"""
Quick Price Check – Lay gia realtime tu Google Search.

Flow:
1. Search Google: "{ten san pham} gia ban"  (Selenium)
2. Lay top 10 ket qua (URL + title)
3. Round 1: requests+BS4 (fast ~0.5s/page)
4. Round 2: Selenium fallback cho trang can JS (Shopee, Lazada...)
5. Tra ve: ten web, logo (favicon), gia, link

Optimized: requests fast-path, cached ChromeDriver, driver pool reuse.
"""

import json as _json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse

import requests as _requests
from bs4 import BeautifulSoup

MIN_LAPTOP_PRICE = 3_000_000
MIN_REASONABLE_PRICE = 5_000_000
MAX_REASONABLE_PRICE = 200_000_000

_NEGATIVE_KEYWORDS = {
    "linh kien", "linh kiện", "phu kien", "phụ kiện",
    "sac", "sạc", "charger", "adapter", "nguon", "nguồn",
    "pin", "battery", "ban phim", "bàn phím", "keyboard",
    "chuot", "chuột", "mouse", "tai nghe", "headphone",
    "ram", "ssd", "hdd", "o cung", "ổ cứng",
    "man hinh", "màn hình", "screen", "lcd",
    "card do hoa", "card đồ họa", "vga", "gpu",
    "case", "vo", "vỏ", "tan nhiet", "tản nhiệt", "cooler",
}

_REQUESTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Cached ChromeDriver path (install once)
_chromedriver_path: str | None = None
_chromedriver_lock = threading.Lock()

# Selenium driver (thread-local)
_thread_local = threading.local()


# ═══════════════════════════════════════════════════════════
#  CHROME DRIVER (cached + pooled)
# ═══════════════════════════════════════════════════════════

def _get_chromedriver_path() -> str:
    """Install ChromeDriver once, cache the path globally."""
    global _chromedriver_path
    if _chromedriver_path:
        return _chromedriver_path
    with _chromedriver_lock:
        if _chromedriver_path:
            return _chromedriver_path
        from webdriver_manager.chrome import ChromeDriverManager
        _chromedriver_path = ChromeDriverManager().install()
        return _chromedriver_path


def _new_driver():
    """Tao Chrome headless driver moi (dung cached chromedriver path)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--user-agent=" + _REQUESTS_HEADERS["User-Agent"])
    opts.add_argument("--lang=vi-VN")
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
    })

    service = Service(_get_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(12)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    })
    return driver


def _get_driver():
    """Lay driver cho thread hien tai (tao moi neu chua co)."""
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


# ═══════════════════════════════════════════════════════════
#  UTILS
# ═══════════════════════════════════════════════════════════

def _parse_vn_price(text: str) -> float:
    """Parse chuoi gia VN -> so. Lay gia dau tien trong range hop ly."""
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
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _get_site_name(domain: str) -> str:
    name_map = {
        "shopee.vn": "Shopee",
        "lazada.vn": "Lazada",
        "tiki.vn": "Tiki",
        "gearvn.com": "GearVN",
        "cellphones.com.vn": "CellphoneS",
        "phongvu.vn": "Phong Vu",
        "fptshop.com.vn": "FPT Shop",
        "nguyenkim.com": "Nguyen Kim",
        "hacom.vn": "Hacom",
        "thegioididong.com": "The Gioi Di Dong",
        "dienmayxanh.com": "Dien May Xanh",
        "anphatpc.com.vn": "An Phat",
        "memoryzone.com.vn": "Memory Zone",
        "phucanh.vn": "Phuc Anh",
        "hanoicomputer.vn": "Hanoi Computer",
        "laptopworld.vn": "Laptop World",
    }
    return name_map.get(domain, domain.split(".")[0].capitalize())


def _get_favicon_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=32"


def _is_negative_result(title: str, snippet: str = "") -> bool:
    hay = f"{title} {snippet}".lower()
    return any(kw in hay for kw in _NEGATIVE_KEYWORDS)


# ═══════════════════════════════════════════════════════════
#  STEP 1: GOOGLE SEARCH (Selenium)
# ═══════════════════════════════════════════════════════════

def _google_search(keyword: str, max_results: int = 10) -> list[dict]:
    results = []
    driver = _get_driver()

    query = f"{keyword} gia ban"
    url = f"https://www.google.com/search?q={quote(query)}&hl=vi&gl=vn&num={max_results}"

    try:
        print(f"[Google] Searching: {query}")
        driver.get(url)
        time.sleep(1)

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.g, div[data-hveid]"))
            )
        except Exception:
            pass

        # Consent page
        try:
            consent = driver.find_elements(By.CSS_SELECTOR,
                "button[id='L2AGLb'], form[action*='consent'] button")
            if consent:
                consent[0].click()
                time.sleep(0.5)
        except Exception:
            pass

        result_elements = driver.find_elements(By.CSS_SELECTOR, "div.g, div[data-hveid]")

        for el in result_elements:
            try:
                link_el = el.find_element(By.CSS_SELECTOR, "a[href^='http']")
                link_url = link_el.get_attribute("href") or ""
                if "google.com" in link_url or not link_url.startswith("http"):
                    continue

                title = ""
                for sel in ["h3", "a h3", "div[role='heading']"]:
                    try:
                        title = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if title:
                            break
                    except Exception:
                        continue

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
                        "title": title, "url": link_url,
                        "snippet": snippet, "domain": domain,
                    })
            except Exception:
                continue

        print(f"[Google] Found {len(results)} results")

    except Exception as e:
        print(f"[Google] Error: {e}")

    return results[:max_results]


# ═══════════════════════════════════════════════════════════
#  STEP 2a: FAST PRICE EXTRACTION (requests + BeautifulSoup)
# ═══════════════════════════════════════════════════════════

def _parse_price_flexible(value) -> float:
    """Parse price from JSON-LD: handles both plain int (15990000) and VN format (15.990.000)."""
    try:
        num = float(value)
        if MIN_LAPTOP_PRICE <= num < MAX_REASONABLE_PRICE:
            return num
    except (ValueError, TypeError):
        pass
    return _parse_vn_price(str(value))


def _extract_price_from_html(html: str) -> float:
    """Extract gia tu raw HTML bang BeautifulSoup (P1: JSON-LD, P2: meta, P3: CSS, P4: regex)."""
    soup = BeautifulSoup(html, "lxml")

    # P1: JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = _json.loads(script.string or "")
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                offers = item.get("offers", item.get("Offers", {}))
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                for key in ("price", "lowPrice"):
                    p = offers.get(key)
                    if p is not None:
                        price = _parse_price_flexible(p)
                        if price >= MIN_LAPTOP_PRICE:
                            return price
        except Exception:
            continue

    # P2: meta tags (content can be plain int "14290000" or formatted "14.290.000")
    for attr in [
        {"property": "product:price:amount"},
        {"property": "og:price:amount"},
        {"attrs": {"itemprop": "price"}},
    ]:
        tag = soup.find("meta", **attr) if "attrs" in attr else soup.find("meta", attrs=attr)
        if tag:
            price = _parse_price_flexible(tag.get("content", ""))
            if price >= MIN_LAPTOP_PRICE:
                return price

    # P3: CSS selectors for current/sale price
    neg_classes = ("old-price", "discount-amount", "original", "list-price", "compare-price")
    price_selectors = [
        ".current-price", ".giaban", "span.price-new",
        "[class*='price-current']", "[class*='sale-price']",
        "[class*='special-price']", "[class*='final-price']",
        "[class*='pro-price']", "span.pdp-price",
        "span.product-price__current-price",
        "[itemprop='price']", "[data-price]",
        "[class*='product-price']", "[class*='box-price']",
        "span.price", "p.price", "div.price",
    ]
    for sel in price_selectors:
        try:
            for el in soup.select(sel):
                cls = " ".join(el.get("class", [])).lower()
                if any(neg in cls for neg in neg_classes):
                    continue
                price = _parse_vn_price(el.get_text())
                if price >= MIN_LAPTOP_PRICE:
                    return price
                for attr_name in ("data-price", "content"):
                    val = el.get(attr_name)
                    if val:
                        price = _parse_price_flexible(val)
                        if price >= MIN_LAPTOP_PRICE:
                            return price
        except Exception:
            continue

    # P4: regex fallback on visible text
    body = soup.find("body")
    if body:
        price = _parse_vn_price(body.get_text(separator=" "))
        if price >= MIN_LAPTOP_PRICE:
            return price

    return 0.0


def _extract_price_requests(url: str) -> float:
    """Fast path: fetch page via requests + extract price from HTML. ~0.5-1s."""
    try:
        resp = _requests.get(url, headers=_REQUESTS_HEADERS, timeout=6, allow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 500:
            return _extract_price_from_html(resp.text)
    except Exception:
        pass
    return 0.0


# ═══════════════════════════════════════════════════════════
#  STEP 2b: SELENIUM FALLBACK (for JS-rendered pages)
# ═══════════════════════════════════════════════════════════

_JS_REQUIRED_DOMAINS = {"shopee.vn", "lazada.vn", "tiki.vn"}


def _extract_price_selenium(url: str) -> float:
    """Selenium fallback for pages that require JS rendering."""
    driver = _get_driver()
    try:
        driver.get(url)

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "[class*='price'], [itemprop='price'], script[type='application/ld+json']"))
            )
        except Exception:
            pass

        html = driver.page_source
        return _extract_price_from_html(html)

    except Exception as e:
        print(f"[Selenium] Error on {url[:60]}: {e}")
    return 0.0


def _extract_price_selenium_isolated(url: str) -> float:
    """Selenium extraction in thread pool: reuse thread-local driver."""
    try:
        _get_driver()
        return _extract_price_selenium(url)
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════
#  STEP 3: SCORING & MAIN FUNCTION
# ═══════════════════════════════════════════════════════════

def _extract_model_keywords(product_name: str, brand: str = "") -> list[str]:
    stop = {"laptop", "gaming", "may", "tinh", "xach", "tay",
            "notebook", "pc", "new", "moi", "chinh", "hang",
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
    Tim gia san pham tu Google -> vao tung trang lay gia.

    Optimized flow:
      1. Google Search (Selenium)
      2. Extract from snippet (instant)
      3. Round 1: requests+BS4 (fast, parallel)
      4. Round 2: Selenium fallback (only for JS pages that failed round 1)
    """
    t_start = time.time()
    model_kws = _extract_model_keywords(keyword, brand)
    print(f"[PriceCheck] Product: '{keyword}' | Brand: '{brand}' | Keywords: {model_kws}")

    # -- Step 1: Google Search --
    google_results = _google_search(keyword, max_results=limit + 5)

    # -- Step 2: Filter --
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

    # -- Step 3: Extract prices --
    price_results: list[dict] = []
    to_visit: list[dict] = []

    for gr in filtered:
        score = max(_score(gr.get("title", ""), model_kws, brand),
                    _score(gr.get("snippet", ""), model_kws, brand))

        # Try snippet price first (instant)
        snippet = gr.get("snippet", "") or ""
        snippet_price = _parse_vn_price(snippet)
        if snippet_price >= MIN_LAPTOP_PRICE:
            print(f"  [Snippet] {gr['domain']}: {snippet_price:,.0f}")
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

    # -- Round 1: requests + BS4 (fast, parallel ~1-3s total) --
    if len(price_results) < limit and to_visit:
        remaining = limit - len(price_results)
        candidates = to_visit[:remaining + 3]

        print(f"  [Round1] requests+BS4 for {len(candidates)} pages...")
        t1 = time.time()

        selenium_fallback: list[dict] = []

        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as ex:
            future_map = {ex.submit(_extract_price_requests, gr["url"]): gr for gr in candidates}
            for fut in as_completed(future_map):
                gr = future_map[fut]
                try:
                    page_price = fut.result()
                except Exception:
                    page_price = 0.0

                if page_price >= MIN_LAPTOP_PRICE:
                    print(f"  [Fast] {gr['domain']}: {page_price:,.0f}")
                    price_results.append({
                        "site_name": _get_site_name(gr["domain"]),
                        "domain": gr["domain"],
                        "favicon_url": _get_favicon_url(gr["domain"]),
                        "product_title": gr.get("title", ""),
                        "price": page_price,
                        "url": gr.get("url", ""),
                        "match_score": gr.get("match_score", 0.0),
                    })
                else:
                    selenium_fallback.append(gr)

        print(f"  [Round1] Done in {time.time() - t1:.1f}s, got {len(price_results)} prices")

        # -- Round 2: Selenium fallback (only for failed pages) --
        if len(price_results) < limit and selenium_fallback:
            remaining = limit - len(price_results)
            sel_candidates = selenium_fallback[:remaining + 1]

            print(f"  [Round2] Selenium fallback for {len(sel_candidates)} pages...")
            t2 = time.time()

            max_workers = min(3, len(sel_candidates))
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {
                    ex.submit(_extract_price_selenium_isolated, gr["url"]): gr
                    for gr in sel_candidates
                }
                for fut in as_completed(future_map):
                    gr = future_map[fut]
                    try:
                        page_price = fut.result()
                    except Exception:
                        continue

                    if page_price >= MIN_LAPTOP_PRICE:
                        print(f"  [Selenium] {gr['domain']}: {page_price:,.0f}")
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

            print(f"  [Round2] Done in {time.time() - t2:.1f}s")

    price_results.sort(key=lambda x: x["match_score"], reverse=True)

    # -- Stats --
    all_prices = [r["price"] for r in price_results]
    stats = {
        "min_price": min(all_prices) if all_prices else None,
        "max_price": max(all_prices) if all_prices else None,
        "avg_price": sum(all_prices) / len(all_prices) if all_prices else None,
        "total_results": len(price_results),
    }

    elapsed = time.time() - t_start
    if stats["avg_price"]:
        sites = ", ".join(set(r["site_name"] for r in price_results))
        print(f"[PriceCheck] OK: {len(price_results)} prices from {sites} ({elapsed:.1f}s)")
        print(f"[PriceCheck] Min: {stats['min_price']:,.0f} | "
              f"Avg: {stats['avg_price']:,.0f} | Max: {stats['max_price']:,.0f}")
    else:
        print(f"[PriceCheck] No prices found ({elapsed:.1f}s)")

    return {
        "keyword": keyword,
        "results": price_results,
        "all_prices": all_prices,
        "stats": stats,
    }


def cleanup_driver():
    """Dong Selenium driver cua thread hien tai."""
    driver = getattr(_thread_local, "driver", None)
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        _thread_local.driver = None
