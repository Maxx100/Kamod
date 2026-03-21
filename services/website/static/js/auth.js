// Проверка статуса авторизации и обновление UI
function updateAuthUI() {
  const user = JSON.parse(localStorage.getItem('user'));
  const authButtons = document.getElementById('authButtons');
  const createEventBtn = document.getElementById('createEventBtn');
  const profileNavLink = document.getElementById('profileNavLink');
  
  if (!authButtons) return;
  
  if (user) {
    // Пользователь авторизован
    const firstName = (user.fullName || 'Пользователь').split(' ')[0];
    authButtons.innerHTML = `
      <span style="font-weight: 500;">👋 ${firstName}</span>
      <button class="btn btn-outline" onclick="logout()">Выйти</button>
    `;
    
    // Показать кнопку создания мероприятия на главной
    if (createEventBtn) {
      createEventBtn.classList.remove('hidden');
    }
    if (profileNavLink) {
      profileNavLink.classList.remove('hidden');
    }
  } else {
    // Пользователь не авторизован
    authButtons.innerHTML = `
      <a href="/login" class="btn btn-outline">Войти</a>
      <a href="/register" class="btn btn-primary">Регистрация</a>
    `;
    
    if (createEventBtn) {
      createEventBtn.classList.add('hidden');
    }
    if (profileNavLink) {
      profileNavLink.classList.add('hidden');
    }
  }
}

// Выход из системы
function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.href = '/main';
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', updateAuthUI);

// Проверка токена при инициализации
async function validateToken() {
  const token = localStorage.getItem('token');
  if (!token) return null;
  
  try {
    const response = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      return await response.json();
    } else {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      return null;
    }
  } catch {
    return null;
  }
}