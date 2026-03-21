let allLoadedEvents = [];
let renderedCount = 0;
const PAGE_SIZE = 12;

function hashString(value) {
  const raw = String(value || 'default');
  let hash = 0;
  for (let i = 0; i < raw.length; i += 1) {
    hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function getDefaultCoverById(eventId) {
  const covers = ['/img/1.jpeg', '/img/2.jpeg', '/img/3.jpeg', '/img/4.jpeg', '/img/5.jpeg', '/img/6.jpeg'];
  return covers[hashString(eventId) % covers.length];
}

function resolveEventCover(event) {
  return event.coverUrl || getDefaultCoverById(event.id);
}

function getTagClassByCategory(category) {
  const classes = {
    hackathon: 'pink-tag',
    conference: 'lilac-tag',
    workshop: 'blue-tag',
    meetup: 'pink-tag',
    competition: 'lilac-tag',
    other: 'orange-tag'
  };
  return classes[category] || 'orange-tag';
}

function renderEventCard(event) {
  const tagClass = getTagClassByCategory(event.category);
  const tagName = getCategoryName(event.category);
  const coverUrl = resolveEventCover(event);

  return `
    <div class="event-card">
      <a href="/event?id=${event.id}">
        <div class="event-image-wrapper">
          <img src="${coverUrl}" alt="${event.title}" class="event-image" onerror="this.onerror=null;this.src='${getDefaultCoverById(event.id)}'">
          <div class="event-tags">
            <span class="event-tag ${tagClass}">${tagName}</span>
          </div>
        </div>
        <div class="event-name">${event.title}</div>
        <div class="event-info">
          <span>${formatDate(event.eventDate)}</span>
          <span>•</span>
          <div class="event-address">
            <p>${truncateAddress(event.address)}</p>
          </div>
        </div>
      </a>
    </div>
  `;
}

function renderHero(events) {
  const heroContainer = document.getElementById('heroEvent');
  if (!heroContainer || events.length === 0) return;

  const event = events[0];
  const coverUrl = resolveEventCover(event);
  heroContainer.innerHTML = `
    <div class="carousel-item">
      <img src="${coverUrl}" alt="${event.title}" class="carousel-bg" onerror="this.onerror=null;this.src='${getDefaultCoverById(event.id)}'">
      <div class="carousel-content">
        <div class="carousel-tags">
          <span class="tag ${getTagClassByCategory(event.category)}">${getCategoryName(event.category)}</span>
        </div>
        <h1 class="carousel-title">${event.title}</h1>
        <div class="carousel-info">
          <span>${formatDate(event.eventDate)}</span>
          <span>•</span>
          <span>${truncateAddress(event.address, 48)}</span>
        </div>
      </div>
    </div>
  `;
}

function renderPopular(events) {
  const popularGrid = document.getElementById('popularEventsGrid');
  if (!popularGrid) return;

  const topEvents = events.slice(0, 3);
  popularGrid.innerHTML = topEvents.map(renderEventCard).join('');
}

function renderNextPage() {
  const grid = document.getElementById('eventsGrid');
  const loadMoreBtn = document.getElementById('loadMoreBtn');
  if (!grid) return;

  const nextChunk = allLoadedEvents.slice(renderedCount, renderedCount + PAGE_SIZE);
  grid.insertAdjacentHTML('beforeend', nextChunk.map(renderEventCard).join(''));
  renderedCount += nextChunk.length;

  if (loadMoreBtn) {
    loadMoreBtn.classList.toggle('hidden', renderedCount >= allLoadedEvents.length);
  }
}

// Загрузка и отображение мероприятий
async function loadEvents(filters = {}) {
  const grid = document.getElementById('eventsGrid');
  if (!grid) return;

  grid.innerHTML = '';
  renderedCount = 0;
  
  try {
    const params = new URLSearchParams();
    if (filters.date) params.append('date', filters.date);
    if (filters.category) params.append('category', filters.category);
    
    const response = await fetch(`/api/events?${params.toString()}`);
    const events = await response.json();

    if (!Array.isArray(events)) {
      throw new Error('Некорректный формат ответа');
    }

    allLoadedEvents = [...events].sort((a, b) => new Date(a.eventDate) - new Date(b.eventDate));

    renderHero(allLoadedEvents);
    renderPopular(allLoadedEvents);

    if (allLoadedEvents.length === 0) {
      grid.innerHTML = '<p style="color: var(--black-600);">Пока нет опубликованных событий</p>';
      const loadMoreBtn = document.getElementById('loadMoreBtn');
      if (loadMoreBtn) loadMoreBtn.classList.add('hidden');
      return;
    }

    renderNextPage();
  } catch (err) {
    console.error('Ошибка загрузки мероприятий:', err);
    grid.innerHTML = '<p style="color: var(--red-color);">Ошибка загрузки данных</p>';
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

    const loadMoreBtn = document.getElementById('loadMoreBtn');
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener('click', renderNextPage);
    }
    
    // Авто-применение фильтров при изменении
    document.getElementById('dateFilter')?.addEventListener('change', applyFilters);
    document.getElementById('categoryFilter')?.addEventListener('change', applyFilters);
  }
});