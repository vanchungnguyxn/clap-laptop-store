/**
 * Dashboard JavaScript – Multi-Agent Laptop Store
 * Xử lý tương tác giao diện: sidebar toggle, chạy phân tích, notifications.
 */

// ═══════════════════════════════════════════════════════════
//  SIDEBAR TOGGLE
// ═══════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const wrapper = document.getElementById('wrapper');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            wrapper.classList.toggle('sidebar-collapsed');
            // Lưu trạng thái sidebar
            localStorage.setItem(
                'sidebarCollapsed',
                wrapper.classList.contains('sidebar-collapsed')
            );
        });

        // Khôi phục trạng thái sidebar
        if (localStorage.getItem('sidebarCollapsed') === 'true') {
            wrapper.classList.add('sidebar-collapsed');
        }
    }
});


// ═══════════════════════════════════════════════════════════
//  CHẠY PHÂN TÍCH MULTI-AGENT
// ═══════════════════════════════════════════════════════════

async function runAnalysis() {
    const btn = document.getElementById('btnRunAnalysis');
    const originalText = btn.innerHTML;

    try {
        // Hiển thị loading
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Đang phân tích...';

        const response = await fetch('/admin/api/run-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        const data = await response.json();

        if (data.success) {
            showNotification(
                'success',
                `✅ Phân tích hoàn tất! ` +
                `Đã thay đổi giá ${data.data.price_changes_applied} sản phẩm. ` +
                `Tồn kho cao: ${data.data.overstock_products} sp.`
            );
            // Reload trang sau 2 giây
            setTimeout(() => location.reload(), 2000);
        } else {
            showNotification('error', `❌ Lỗi: ${data.error}`);
        }
    } catch (error) {
        showNotification('error', `❌ Lỗi kết nối: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}


// ═══════════════════════════════════════════════════════════
//  NOTIFICATIONS
// ═══════════════════════════════════════════════════════════

function showNotification(type, message) {
    const alertClass = type === 'success' ? 'alert-success' :
                       type === 'error' ? 'alert-danger' : 'alert-warning';

    const alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert"
             style="position: fixed; top: 20px; right: 20px; z-index: 10000; min-width: 350px;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15); animation: slideIn 0.3s ease;">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', alertHtml);

    // Tự động ẩn sau 5 giây
    setTimeout(() => {
        const alerts = document.querySelectorAll('.alert[style*="position: fixed"]');
        alerts.forEach(alert => {
            alert.style.opacity = '0';
            alert.style.transform = 'translateX(100px)';
            setTimeout(() => alert.remove(), 300);
        });
    }, 5000);
}


// ═══════════════════════════════════════════════════════════
//  FORMAT HELPERS
// ═══════════════════════════════════════════════════════════

/**
 * Format số thành tiền VNĐ.
 * @param {number} amount - Số tiền
 * @returns {string} - Chuỗi đã format
 */
function formatCurrency(amount) {
    return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: 'VND',
    }).format(amount);
}

/**
 * Format số lượng.
 * @param {number} num - Số
 * @returns {string} - Chuỗi đã format
 */
function formatNumber(num) {
    return new Intl.NumberFormat('vi-VN').format(num);
}


// ═══════════════════════════════════════════════════════════
//  AUTO-REFRESH (tuỳ chọn)
// ═══════════════════════════════════════════════════════════

// Tự động refresh dashboard mỗi 5 phút (nếu muốn)
// setInterval(() => {
//     if (document.visibilityState === 'visible') {
//         location.reload();
//     }
// }, 5 * 60 * 1000);
