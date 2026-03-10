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

-- ── Dữ liệu cần thiết (chỉ chạy 1 lần, bỏ qua nếu đã tồn tại) ──

INSERT INTO competitors (name, base_url, platform) VALUES
    ('Shopee Vietnam', 'https://shopee.vn', 'shopee'),
    ('Lazada Vietnam', 'https://www.lazada.vn', 'lazada'),
    ('Tiki', 'https://tiki.vn', 'tiki');

INSERT INTO business_rules (rule_name, inventory_threshold, discount_percent, competitor_out_markup, high_demand_markup) VALUES
    ('Default Rule', 100, 5.00, 10.00, 8.00);

INSERT INTO admin_users (username, password_hash, employee_code, full_name, role) VALUES
    ('admin', '$2b$12$9vfLsCyM8NmPalTdN46FmOi26PM9Fy9azurabZVpa6jN4nVKmgH6a', 'NV001', 'Quản trị viên', 'admin');
