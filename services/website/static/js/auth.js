let currentAvatarObjectUrl = null;

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('user'));
  } catch {
    return null;
  }
}

function getUserInitials(fullName) {
  if (!fullName) return '?';
  return fullName
    .split(' ')
    .map((part) => part[0]?.toUpperCase())
    .filter(Boolean)
    .slice(0, 2)
    .join('');
}

function clearAvatarObjectUrl() {
  if (currentAvatarObjectUrl) {
    URL.revokeObjectURL(currentAvatarObjectUrl);
    currentAvatarObjectUrl = null;
  }
}

async function applyHeaderAvatar(token) {
  const user = getStoredUser();
  const avatarImage = document.querySelector('[data-user-avatar-image]');
  const avatarFallback = document.querySelector('[data-user-avatar-fallback]');

  if (!user || !token || !avatarImage || !avatarFallback || !user.hasPhoto) {
    return;
  }

  try {
    const response = await fetch('/api/users/me/photo', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!response.ok) {
      throw new Error('avatar not found');
    }

    clearAvatarObjectUrl();
    currentAvatarObjectUrl = URL.createObjectURL(await response.blob());
    avatarImage.src = currentAvatarObjectUrl;
    avatarImage.classList.remove('hidden');
    avatarFallback.classList.add('hidden');
  } catch {
    avatarImage.removeAttribute('src');
    avatarImage.classList.add('hidden');
    avatarFallback.classList.remove('hidden');
  }
}

// Проверка статуса авторизации и обновление UI
async function updateAuthUI() {
  const user = getStoredUser();
  const token = localStorage.getItem('token');
  const authButtons = document.getElementById('authButtons');
  const profileNavLink = document.getElementById('profileNavLink');
  const myEventsNavLink = document.getElementById('myEventsNavLink');
  
  if (!authButtons) return;
  
  if (user) {
    const initials = getUserInitials(user.fullName);
    const displayName = user.firstName || (user.fullName || 'Пользователь').split(' ')[0];

    authButtons.innerHTML = `
      <a href="/profile" class="auth-user-chip auth-user-link" aria-label="Перейти в профиль">
        <div class="user-avatar">
          <img class="user-avatar-image hidden" data-user-avatar-image alt="Фото профиля">
          <span class="user-avatar-fallback" data-user-avatar-fallback>${initials}</span>
        </div>
        <span class="auth-user-name">${displayName}</span>
      </a>
      <button class="btn btn-outline" onclick="logout()">Выйти</button>
    `;
    
    if (myEventsNavLink) {
      myEventsNavLink.classList.remove('hidden');
    }

    if (profileNavLink) {
      profileNavLink.classList.remove('hidden');
    }

    if (user.hasPhoto && token) {
      await applyHeaderAvatar(token);
    }
  } else {
    clearAvatarObjectUrl();
    authButtons.innerHTML = `
      <a href="/login" class="btn btn-outline">Войти</a>
      <a href="/register" class="btn btn-primary">Регистрация</a>
    `;
    
    if (myEventsNavLink) {
      myEventsNavLink.classList.add('hidden');
    }

    if (profileNavLink) {
      profileNavLink.classList.add('hidden');
    }
  }
}

// Выход из системы
function logout() {
  clearAvatarObjectUrl();
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.href = '/main';
}

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
    }

    localStorage.removeItem('token');
    localStorage.removeItem('user');
    return null;
  } catch {
    return null;
  }
}

async function initAuthUI() {
  const freshUser = await validateToken();
  if (freshUser) {
    localStorage.setItem('user', JSON.stringify(freshUser));
  }
  await updateAuthUI();
}

window.updateAuthUI = updateAuthUI;
window.validateToken = validateToken;

document.addEventListener('DOMContentLoaded', initAuthUI);
