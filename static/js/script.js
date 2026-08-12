console.log("Le maison yelo Lane initialized.");

function togglePasswordVisibility(inputId, iconElement) {
    const passwordInput = document.getElementById(inputId);
    if (!passwordInput) return;

    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        iconElement.classList.remove('fa-eye');
        iconElement.classList.add('fa-eye-slash');
    } else {
        passwordInput.type = 'password';
        iconElement.classList.remove('fa-eye-slash');
        iconElement.classList.add('fa-eye');
    }
}

// ── Premium Toast Notification System ──────────────────────────────────────
window.showToast = function(category, message) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    // Toast notification feedback (Auto-drawer opening disabled for frictionless ordering)

    const cfg = {
        success: { icon: '✅', title: 'Success',     color: '#2E7D32', bg: '#E8F5E9' },
        danger:  { icon: '❌', title: 'Error',       color: '#C62828', bg: '#FFEBEE' },
        warning: { icon: '⚠️', title: 'Warning',     color: '#E65100', bg: '#FFF3E0' },
        info:    { icon: 'ℹ️', title: 'Info',        color: '#1565C0', bg: '#E3F2FD' },
    };
    const c = cfg[category] || cfg.info;

    const toast = document.createElement('div');
    toast.className = 'toast-notif';
    toast.style.borderLeftColor = c.color;
    toast.innerHTML = `
        <div class="toast-icon" style="color:${c.color};">${c.icon}</div>
        <div class="toast-body">
            <div class="toast-title" style="color:${c.color};">${c.title}</div>
            <div class="toast-msg">${message}</div>
        </div>
        <button class="toast-close" onclick="dismissToast(this.parentElement)">✕</button>
        <div class="toast-progress" style="background:${c.color}; animation-duration: 3s;"></div>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => { requestAnimationFrame(() => toast.classList.add('show')); });

    // Auto dismiss toast after 3 seconds for clean UX
    const timer = setTimeout(() => dismissToast(toast), 3000);
    toast._timer = timer;
};

window.dismissToast = function(toast) {
    if (!toast) return;
    clearTimeout(toast._timer);
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 400);
};
