// Загрузка и отображение мероприятий
async function loadEvents(filters = {}) {
  const grid = document.getElementById('eventsGrid');
  const emptyState = document.getElementById('emptyState');
  
  if (!grid) return;
  
  try {
    // Формирование query params
    const params = new URLSearchParams();
    if (filters.date) params.append('date', filters.date);
    if (filters.category) params.append('category', filters.category);
    
    const response = await fetch(`/api/events?${params}`);
    const events = await response.json();
    
    if (events.length === 0) {
      grid.innerHTML = '';
      emptyState?.classList.remove('hidden');
      return;
    }
    
    emptyState?.classList.add('hidden');
    
    grid.innerHTML = events.map(event => `
      <a href="event.html?id=${event.id}" class="event-card">
        <div class="event-cover">
          ${event.coverUrl 
            ? `<img src="${event.coverUrl}" alt="${event.title}">` 
            : '<i class="fas fa-calendar-alt"></i>'}
        </div>
        <div class="event-content">
          <span class="event-category">${getCategoryName(event.category)}</span>
          <h3 class="event-title">${event.title}</h3>
          <div class="event-meta">
            <span><i class="far fa-calendar"></i> ${formatDate(event.eventDate)}</span>
            <span><i class="fas fa-map-marker-alt"></i> ${truncateAddress(event.address)}</span>
          </div>
          <div class="event-price ${event.isPaid ? '' : 'free'}">
            ${event.isPaid ? `${event.price} ₽` : 'Бесплатно'}
          </div>
        </div>
      </a>
    `).join('');
    
  } catch (err) {
    console.error('Ошибка загрузки мероприятий:', err);
    grid.innerHTML = '<p style="color: var(--danger);">Ошибка загрузки данных</p>';
  }
}

// Применение фильтров
function applyFilters() {
  const date = document.getElementById('dateFilter')?.value;
  const category = document.getElementById('categoryFilter')?.value;
  
  loadEvents({ date, category });
}

// Сброс фильтров
function resetFilters() {
  if (document.getElementById('dateFilter')) {
    document.getElementById('dateFilter').value = '';
  }
  if (document.getElementById('categoryFilter')) {
    document.getElementById('categoryFilter').value = '';
  }
  loadEvents({});
}

// Вспомогательные функции
function getCategoryName(key) {
  const categories = {
    hackathon: 'Хакатон',
    conference: 'Конференция',
    workshop: 'Мастер-класс',
    meetup: 'Митап',
    competition: 'Конкурс',
    other: 'Другое'
  };
  return categories[key] || key;
}

function formatDate(dateString) {
  return new Date(dateString).toLocaleString('ru-RU', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
  });
}

function truncateAddress(address, maxLength = 30) {
  return address.length > maxLength 
    ? address.substring(0, maxLength) + '...' 
    : address;
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('eventsGrid')) {
    loadEvents({});
    
    // Авто-применение фильтров при изменении
    document.getElementById('dateFilter')?.addEventListener('change', applyFilters);
    document.getElementById('categoryFilter')?.addEventListener('change', applyFilters);
  }
});