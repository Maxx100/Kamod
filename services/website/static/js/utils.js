// Вспомогательные функции для всех страниц

function getInitials(fullName) {
  if (!fullName) return '?';
  return fullName.split(' ').map(n => n[0]?.toUpperCase()).filter(Boolean).slice(0, 2).join('');
}

function formatDate(dateString, options = {}) {
  const defaultOptions = {
    day: '2-digit', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow'
  };
  return new Date(dateString).toLocaleString('ru-RU', { ...defaultOptions, ...options });
}

function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

function showToast(message, type = 'info', duration = 3000) {
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed; bottom: 20px; right: 20px;
    padding: 12px 20px; border-radius: 12px;
    background: ${type === 'success' ? '#03ad3f' : type === 'error' ? '#d2342d' : '#0b68fe'};
    color: white; font-weight: 500; z-index: 1000;
    animation: slideIn 0.3s ease;
  `;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Анимации
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
  @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
`;
document.head.appendChild(style);