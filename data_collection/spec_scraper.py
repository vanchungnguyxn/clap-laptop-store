"""
Spec Scraper – Tự động tra cứu thông số kỹ thuật laptop từ các web VN.

Flow:
1. Google search: "{tên sản phẩm} thông số kỹ thuật"
2. Ưu tiên kết quả từ các trang uy tín (thegioididong, cellphones, fptshop…)
3. Vào trang, trích bảng spec
4. Map label tiếng Việt → field name trong form
"""

import re
import time
import threading
from urllib.parse import quote, urlparse

_thread_local = threading.local()

_TRUSTED_DOMAINS = [
    "thegioididong.com", "cellphones.com.vn", "fptshop.com.vn",
    "phongvu.vn", "gearvn.com", "laptopworld.vn", "nguyenkim.com",
    "hacom.vn", "anphatpc.com.vn", "phucanh.vn", "hanoicomputer.vn",
    "dienmayxanh.com", "notebookspec.com", "laptopaz.vn",
]

_LABEL_MAP: dict[str, str] = {}
_RAW = {
    "cpu": [
        "cpu", "vi xử lý", "bộ xử lý", "processor", "chip xử lý",
        "bộ vi xử lý", "loại cpu",
    ],
    "gpu": [
        "card đồ họa", "gpu", "vga", "chip đồ họa", "card màn hình",
        "đồ họa", "card rời", "card onboard",
    ],
    "ram": [
        "ram", "bộ nhớ trong", "bộ nhớ ram", "memory", "bộ nhớ",
    ],
    "storage": [
        "ổ cứng", "ssd", "hdd", "lưu trữ", "bộ nhớ lưu trữ",
        "dung lượng ổ cứng", "ổ lưu trữ", "ổ đĩa cứng",
    ],
    "screen_size": [
        "kích thước màn hình", "màn hình", "display", "screen",
        "kích cỡ màn hình", "loại màn hình",
    ],
    "screen_detail": [
        "độ phân giải", "resolution", "tấm nền", "panel", "tần số quét",
        "độ phân giải màn hình", "công nghệ màn hình",
    ],
    "battery": [
        "pin", "battery", "dung lượng pin", "thời lượng pin",
    ],
    "weight": [
        "trọng lượng", "khối lượng", "cân nặng", "weight", "nặng",
    ],
    "os": [
        "hệ điều hành", "os", "operating system", "phần mềm",
    ],
    "ports": [
        "cổng kết nối", "cổng giao tiếp", "kết nối", "i/o", "cổng",
        "cổng xuất hình", "cổng usb", "khe cắm",
    ],
    "warranty": [
        "bảo hành", "warranty",
    ],
    "color": [
        "màu sắc", "màu", "color",
    ],
}
for field, labels in _RAW.items():
    for lbl in labels:
        _LABEL_MAP[lbl] = field


def _new_driver():
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
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )
    opts.add_argument("--lang=vi-VN")
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)

    from data_collection.quick_price_check import _get_chromedriver_path
    service = Service(_get_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(12)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    })
    return driver


def _get_driver():
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


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def _match_label(label: str) -> str | None:
    """Map label tiếng Việt → field name (hoặc None)."""
    lbl = label.strip().lower()
    lbl = re.sub(r"\s+", " ", lbl).rstrip(":")
    if lbl in _LABEL_MAP:
        return _LABEL_MAP[lbl]
    for key, field in _LABEL_MAP.items():
        if key in lbl or lbl in key:
            return field
    return None


def _google_search_specs(product_name: str, max_results: int = 12) -> list[dict]:
    """Google search cho spec."""
    driver = _get_driver()
    query = f"{product_name} thông số kỹ thuật"
    url = f"https://www.google.com/search?q={quote(query)}&hl=vi&gl=vn&num={max_results}"
    results = []
    try:
        print(f"[SpecSearch] Searching: {query}")
        driver.get(url)
        time.sleep(2)
        from selenium.webdriver.common.by import By
        try:
            consent = driver.find_elements(By.CSS_SELECTOR,
                "button[id='L2AGLb'], form[action*='consent'] button")
            if consent:
                consent[0].click()
                time.sleep(1)
        except Exception:
            pass

        elements = driver.find_elements(By.CSS_SELECTOR, "div.g, div[data-hveid]")
        for el in elements:
            try:
                link = el.find_element(By.CSS_SELECTOR, "a[href^='http']")
                href = link.get_attribute("href") or ""
                if "google.com" in href:
                    continue
                title = ""
                for sel in ["h3", "a h3", "div[role='heading']"]:
                    try:
                        title = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if title:
                            break
                    except Exception:
                        continue
                domain = _domain(href)
                if title and domain:
                    results.append({"title": title, "url": href, "domain": domain})
            except Exception:
                continue
        print(f"[SpecSearch] Found {len(results)} results")
    except Exception as e:
        print(f"[SpecSearch] Error: {e}")
    return results[:max_results]


def _extract_specs_from_page(url: str) -> dict[str, str]:
    """Vào trang sản phẩm và trích xuất spec table/list."""
    driver = _get_driver()
    specs: dict[str, str] = {}
    try:
        driver.get(url)
        time.sleep(3)
        from selenium.webdriver.common.by import By

        pairs: list[tuple[str, str]] = []

        # Strategy 1: <table> rows with 2 cells (label | value)
        rows = driver.find_elements(By.CSS_SELECTOR,
            "table tr, .parameter tr, .specifications tr, "
            "[class*='spec'] tr, [class*='tskt'] tr, [class*='config'] tr")
        for row in rows:
            cells = row.find_elements(By.CSS_SELECTOR, "td, th")
            if len(cells) >= 2:
                lbl = cells[0].text.strip()
                val = cells[1].text.strip()
                if lbl and val and len(lbl) < 80:
                    pairs.append((lbl, val))

        # Strategy 2: <li> or <div> with label/value children
        containers = driver.find_elements(By.CSS_SELECTOR,
            "[class*='spec'] li, [class*='parameter'] li, "
            "[class*='tskt'] li, [class*='config'] li, "
            "[class*='detail'] li, [class*='info-list'] li, "
            "ul.specificationList li, "
            ".box-specifi li, .specifi li")
        for c in containers:
            text = c.text.strip()
            if not text or len(text) > 300:
                continue
            # pattern "Label: Value" or "Label\nValue"
            parts = re.split(r"[:\n]", text, maxsplit=1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                pairs.append((parts[0].strip(), parts[1].strip()))
            else:
                subs = c.find_elements(By.CSS_SELECTOR, "span, strong, b, p, div, em")
                if len(subs) >= 2:
                    lbl = subs[0].text.strip()
                    val = subs[-1].text.strip()
                    if lbl and val and lbl != val:
                        pairs.append((lbl, val))

        # Strategy 3: Definition lists <dl>
        dls = driver.find_elements(By.CSS_SELECTOR, "dl")
        for dl in dls:
            dts = dl.find_elements(By.TAG_NAME, "dt")
            dds = dl.find_elements(By.TAG_NAME, "dd")
            for dt, dd in zip(dts, dds):
                lbl = dt.text.strip()
                val = dd.text.strip()
                if lbl and val:
                    pairs.append((lbl, val))

        # Strategy 4: Divs with adjacent label/value
        blocks = driver.find_elements(By.CSS_SELECTOR,
            "[class*='spec-item'], [class*='param-item'], "
            "[class*='boxSpecifi'] .item, .box-content .item-spec")
        for blk in blocks:
            children = blk.find_elements(By.CSS_SELECTOR, "*")
            texts = [ch.text.strip() for ch in children if ch.text.strip()]
            if len(texts) >= 2:
                pairs.append((texts[0], texts[-1]))

        print(f"[SpecScrape] Extracted {len(pairs)} raw pairs from {_domain(url)}")

        for lbl, val in pairs:
            field = _match_label(lbl)
            if field and field not in specs and val:
                clean = re.sub(r"\s+", " ", val).strip()
                if len(clean) > 2:
                    specs[field] = clean

    except Exception as e:
        print(f"[SpecScrape] Error on {url[:60]}: {e}")

    return specs


def fetch_product_specs(product_name: str) -> dict:
    """
    Tra cứu thông số kỹ thuật sản phẩm từ web.

    Returns:
        dict: {
            "success": bool,
            "specs": {field_name: value, ...},
            "source": str,
            "source_url": str,
        }
    """
    results = _google_search_specs(product_name)

    trusted = [r for r in results
               if any(td in r["domain"] for td in _TRUSTED_DOMAINS)]
    others = [r for r in results if r not in trusted]
    ordered = trusted + others

    best_specs: dict[str, str] = {}
    best_source = ""
    best_url = ""

    for r in ordered[:6]:
        print(f"[SpecScrape] Trying: {r['domain']} – {r['title'][:50]}")
        specs = _extract_specs_from_page(r["url"])
        if len(specs) > len(best_specs):
            best_specs = specs
            best_source = r["domain"]
            best_url = r["url"]
        if len(best_specs) >= 6:
            break

    if best_specs:
        print(f"[SpecScrape] Best: {best_source} with {len(best_specs)} fields")
    else:
        print(f"[SpecScrape] No specs found for '{product_name}'")

    return {
        "success": bool(best_specs),
        "specs": best_specs,
        "source": best_source,
        "source_url": best_url,
    }


def cleanup_driver():
    driver = getattr(_thread_local, "driver", None)
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        _thread_local.driver = None
