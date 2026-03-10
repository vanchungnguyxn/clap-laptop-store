-- ============================================
-- Schema MySQL cho hệ thống Multi-Agent Laptop Store
-- Database: laptop_pricing (tạo bởi Docker)
-- ============================================

-- Database được chọn tự động bởi connection (Config.DB_NAME)
-- Trên Railway: database = "railway"
-- Trên local:   database = "laptop_pricing"

-- ── Bảng sản phẩm ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    brand           VARCHAR(100),
    model           VARCHAR(100),
    specs           TEXT                            COMMENT 'Cấu hình chi tiết dạng JSON',
    current_price   DECIMAL(15, 2) NOT NULL         COMMENT 'Giá bán hiện tại (VNĐ)',
    cost_price      DECIMAL(15, 2)                  COMMENT 'Giá vốn',
    stock_quantity  INT DEFAULT 0                   COMMENT 'Số lượng tồn kho',
    category        VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_brand (brand),
    INDEX idx_category (category),
    INDEX idx_active (is_active)
) ENGINE=InnoDB;

-- ── Bảng đối thủ cạnh tranh ───────────────────────────
CREATE TABLE IF NOT EXISTS competitors (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL           COMMENT 'Tên đối thủ (Shopee, Lazada, ...)',
    base_url        VARCHAR(500)                    COMMENT 'URL gốc của đối thủ',
    platform        ENUM('shopee', 'lazada', 'tiki', 'other') DEFAULT 'other',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ── Bảng giá đối thủ (thu thập bằng Selenium) ────────
CREATE TABLE IF NOT EXISTS competitor_prices (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    product_id      INT NOT NULL,
    competitor_id   INT NOT NULL,
    competitor_product_name VARCHAR(500)             COMMENT 'Tên sản phẩm trên trang đối thủ',
    competitor_url  VARCHAR(1000)                    COMMENT 'Link sản phẩm đối thủ',
    price           DECIMAL(15, 2)                   COMMENT 'Giá đối thủ (VNĐ)',
    is_in_stock     BOOLEAN DEFAULT TRUE             COMMENT 'Đối thủ còn hàng không',
    scraped_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (competitor_id) REFERENCES competitors(id) ON DELETE CASCADE,
    INDEX idx_product_competitor (product_id, competitor_id),
    INDEX idx_scraped_at (scraped_at)
) ENGINE=InnoDB;

-- ── Bảng lịch sử thay đổi giá (nhật ký) ──────────────
CREATE TABLE IF NOT EXISTS price_change_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    product_id      INT NOT NULL,
    old_price       DECIMAL(15, 2) NOT NULL,
    new_price       DECIMAL(15, 2) NOT NULL,
    change_percent  DECIMAL(5, 2)                   COMMENT '% thay đổi',
    reason          TEXT                             COMMENT 'Lý do thay đổi giá',
    triggered_by    ENUM('pricing_agent', 'inventory_agent', 'manual') DEFAULT 'manual',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    INDEX idx_product_date (product_id, created_at)
) ENGINE=InnoDB;

-- ── Bảng lịch sử tồn kho ─────────────────────────────
CREATE TABLE IF NOT EXISTS inventory_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    product_id      INT NOT NULL,
    quantity_before INT,
    quantity_after  INT,
    change_type     ENUM('import', 'export', 'adjustment') DEFAULT 'adjustment',
    note            TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    INDEX idx_product_date (product_id, created_at)
) ENGINE=InnoDB;

-- ── Bảng quy tắc kinh doanh ──────────────────────────
CREATE TABLE IF NOT EXISTS business_rules (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    rule_name               VARCHAR(255) NOT NULL,
    inventory_threshold     INT DEFAULT 100          COMMENT 'Ngưỡng tồn kho để kích hoạt',
    discount_percent        DECIMAL(5, 2) DEFAULT 5.0 COMMENT '% giảm giá khi vượt ngưỡng tồn kho',
    competitor_out_markup   DECIMAL(5, 2) DEFAULT 10.0 COMMENT '% tăng giá khi đối thủ hết hàng',
    high_demand_markup      DECIMAL(5, 2) DEFAULT 8.0  COMMENT '% tăng giá khi nhu cầu cao',
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ── Bảng nhân viên admin ─────────────────────────────
CREATE TABLE IF NOT EXISTS admin_users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(100) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL          COMMENT 'bcrypt hash',
    employee_code   VARCHAR(50)  NOT NULL UNIQUE   COMMENT 'Mã nhân viên (VD: NV001)',
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(50)  DEFAULT 'staff'   COMMENT 'staff | manager | admin',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_username (username),
    INDEX idx_employee_code (employee_code)
) ENGINE=InnoDB;

-- ── Bảng nhật ký hoạt động admin ────────────────────
CREATE TABLE IF NOT EXISTS admin_activity_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT,
    employee_code   VARCHAR(50)  NOT NULL,
    full_name       VARCHAR(255),
    action_type     VARCHAR(50)  NOT NULL            COMMENT 'login|add_product|edit_product|hide_product|delete_product|...',
    description     TEXT         NOT NULL,
    ip_address      VARCHAR(45),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_employee (employee_code),
    INDEX idx_action (action_type),
    INDEX idx_created (created_at DESC)
) ENGINE=InnoDB;

-- ── Dữ liệu mẫu ──────────────────────────────────────
INSERT INTO competitors (name, base_url, platform) VALUES
    ('Shopee Vietnam', 'https://shopee.vn', 'shopee'),
    ('Lazada Vietnam', 'https://www.lazada.vn', 'lazada'),
    ('Tiki', 'https://tiki.vn', 'tiki');

INSERT INTO business_rules (rule_name, inventory_threshold, discount_percent, competitor_out_markup, high_demand_markup) VALUES
    ('Default Rule', 100, 5.00, 10.00, 8.00);

INSERT INTO admin_users (username, password_hash, employee_code, full_name, role) VALUES
    ('admin', '$2b$12$9vfLsCyM8NmPalTdN46FmOi26PM9Fy9azurabZVpa6jN4nVKmgH6a', 'NV001', 'Quản trị viên', 'admin');

INSERT INTO products (name, brand, model, current_price, cost_price, stock_quantity, category) VALUES
    ('Dell Inspiron 15 3520', 'Dell', 'Inspiron 15 3520', 15990000, 13000000, 50, 'Laptop'),
    ('HP Pavilion 14-dv2035TU', 'HP', 'Pavilion 14', 17490000, 14500000, 30, 'Laptop'),
    ('MacBook Air M2 2022', 'Apple', 'Air M2', 27990000, 24000000, 20, 'Laptop'),
    ('Asus VivoBook 15 X1502ZA', 'Asus', 'VivoBook 15', 13990000, 11000000, 80, 'Laptop'),
    ('Lenovo IdeaPad Slim 3 15IAH8', 'Lenovo', 'IdeaPad Slim 3', 12490000, 10000000, 60, 'Laptop');

-- ── Dữ liệu giá đối thủ mẫu ─────────────────────────
INSERT INTO competitor_prices (product_id, competitor_id, competitor_product_name, competitor_url, price, is_in_stock) VALUES
    (1, 1, 'Dell Inspiron 15 3520 - Shopee', 'https://shopee.vn/dell-inspiron-15', 15490000, TRUE),
    (1, 2, 'Dell Inspiron 15 3520 - Lazada', 'https://lazada.vn/dell-inspiron-15', 16290000, TRUE),
    (1, 3, 'Dell Inspiron 15 3520 - Tiki', 'https://tiki.vn/dell-inspiron-15', 15790000, TRUE),
    (2, 1, 'HP Pavilion 14 - Shopee', 'https://shopee.vn/hp-pavilion-14', 16990000, TRUE),
    (2, 2, 'HP Pavilion 14 - Lazada', 'https://lazada.vn/hp-pavilion-14', 17290000, TRUE),
    (2, 3, 'HP Pavilion 14 - Tiki', 'https://tiki.vn/hp-pavilion-14', 17690000, FALSE),
    (3, 1, 'MacBook Air M2 - Shopee', 'https://shopee.vn/macbook-air-m2', 27490000, TRUE),
    (3, 2, 'MacBook Air M2 - Lazada', 'https://lazada.vn/macbook-air-m2', 28490000, FALSE),
    (3, 3, 'MacBook Air M2 - Tiki', 'https://tiki.vn/macbook-air-m2', 27790000, TRUE),
    (4, 1, 'Asus VivoBook 15 - Shopee', 'https://shopee.vn/asus-vivobook', 13490000, TRUE),
    (4, 2, 'Asus VivoBook 15 - Lazada', 'https://lazada.vn/asus-vivobook', 14290000, TRUE),
    (4, 3, 'Asus VivoBook 15 - Tiki', 'https://tiki.vn/asus-vivobook', 13790000, TRUE),
    (5, 1, 'Lenovo IdeaPad Slim 3 - Shopee', 'https://shopee.vn/lenovo-ideapad', 12190000, TRUE),
    (5, 2, 'Lenovo IdeaPad Slim 3 - Lazada', 'https://lazada.vn/lenovo-ideapad', 12690000, FALSE),
    (5, 3, 'Lenovo IdeaPad Slim 3 - Tiki', 'https://tiki.vn/lenovo-ideapad', 12390000, TRUE);

-- ── Lịch sử thay đổi giá mẫu ────────────────────────
INSERT INTO price_change_log (product_id, old_price, new_price, change_percent, reason, triggered_by) VALUES
    (1, 16490000, 15990000, -3.03, 'Giảm giá cạnh tranh với Shopee', 'pricing_agent'),
    (2, 17990000, 17490000, -2.78, 'Tồn kho cao → giảm 5%', 'inventory_agent'),
    (4, 14490000, 13990000, -3.45, 'Tồn kho > 200 sp → giảm giá đẩy hàng', 'inventory_agent'),
    (3, 26990000, 27990000, 3.70, 'Đối thủ Lazada hết hàng → tăng giá', 'pricing_agent'),
    (5, 12990000, 12490000, -3.85, 'Giá cao hơn đối thủ → giảm để cạnh tranh', 'pricing_agent');
