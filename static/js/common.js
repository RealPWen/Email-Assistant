/**
 * DeepMail Frontend Common Utilities
 */

const CommonUI = {
    /**
     * 显示全局 Toast 提示
     * @param {string} msg 
     * @param {string} type 'success' | 'error'
     */
    showToast(msg, type = 'success') {
        let toast = document.getElementById('toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'toast';
            // 基础样式
            Object.assign(toast.style, {
                position: 'fixed',
                bottom: '40px',
                left: '50%',
                transform: 'translateX(-50%)',
                background: '#1e293b',
                color: 'white',
                padding: '14px 28px',
                borderRadius: '16px',
                zIndex: '2000',
                boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
                fontWeight: '600',
                display: 'none'
            });
            document.body.appendChild(toast);
        }
        
        toast.textContent = msg;
        toast.style.display = 'block';
        toast.style.background = type === 'success' ? '#1e293b' : '#ef4444';
        
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    },

    /**
     * 格式化日期显示
     */
    formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }
        return date.toLocaleDateString([], {month: 'short', day: 'numeric'});
    }
};

window.CommonUI = CommonUI;
