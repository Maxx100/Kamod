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
    other: 'orange-tag',
    online: 'blue-tag'
  };
  return classes[category] || 'orange-tag';
}

function getCategoryName(key) {
  const categories = {
    hackathon: 'Хакатон',
    conference: 'Конференция',
    workshop: 'Мастер-класс',
    meetup: 'Митап',
    competition: 'Конкурс',
    other: 'Другое',
    online: 'Онлайн'
  };
  return categories[key] || 'Другое';
}

function getEventTagKeys(event) {
  if (Array.isArray(event.tags) && event.tags.length) {
    return event.tags;
  }

  const tags = [event.category || 'other'];
  if (event.format === 'online') {
    tags.push('online');
  }
  return tags;
}

function renderEventTags(event, className = 'event-tag') {
  return getEventTagKeys(event)
    .map((tag) => `<span class="${className} ${getTagClassByCategory(tag)}">${getCategoryName(tag)}</span>`)
    .join('');
}

function renderEventCard(event) {
  const coverUrl = resolveEventCover(event);

  return `
    <div class="event-card">
      <a href="/event?id=${event.id}">
        <div class="event-image-wrapper">
          <img src="${coverUrl}" alt="${event.title}" class="event-image" onerror="this.onerror=null;this.src='${getDefaultCoverById(event.id)}'">
          <div class="event-tags">
            ${renderEventTags(event)}
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

function renderHero(event) {
  const heroContainer = document.getElementById('heroEvent');
  if (!heroContainer) return;

  if (!event) {
    heroContainer.innerHTML = `
      <div class="carousel-item">
        <img src="/img/1.jpeg" alt="Событие" class="carousel-bg">
        <div class="carousel-content">
          <h1 class="carousel-title">Пока нет популярных мероприятий</h1>
        </div>
      </div>
    `;
    return;
  }

  const coverUrl = resolveEventCover(event);
  heroContainer.innerHTML = `
    <a href="/event?id=${event.id}" class="hero-link" aria-label="Открыть событие ${event.title}">
      <div class="carousel-item">
        <img src="${coverUrl}" alt="${event.title}" class="carousel-bg" onerror="this.onerror=null;this.src='${getDefaultCoverById(event.id)}'">
        <div class="carousel-content">
          <div class="carousel-tags">
            ${renderEventTags(event, 'tag')}
          </div>
          <h1 class="carousel-title">${event.title}</h1>
          <div class="carousel-info">
            <span>${formatDate(event.eventDate)}</span>
            <span>•</span>
            <span>${truncateAddress(event.address, 48)}</span>
          </div>
        </div>
      </div>
    </a>
  `;
}

function renderPopular(events) {
  const popularGrid = document.getElementById('popularEventsGrid');
  if (!popularGrid) return;

  const topEvents = events.slice(0, 3);
  if (!topEvents.length) {
    popularGrid.innerHTML = '<div class="card">Пока нет популярных мероприятий</div>';
    return;
  }
  popularGrid.innerHTML = topEvents.map(renderEventCard).join('');
}

function getPopularEvents(events) {
  const now = new Date();
  const upcomingEvents = events.filter((event) => new Date(event.eventDate) >= now);
  const source = upcomingEvents.length ? upcomingEvents : events;

  return [...source].sort((left, right) => {
    const registrationsDiff = (right.registeredCount || 0) - (left.registeredCount || 0);
    if (registrationsDiff !== 0) {
      return registrationsDiff;
    }

    const dateDiff = new Date(left.eventDate) - new Date(right.eventDate);
    if (dateDiff !== 0) {
      return dateDiff;
    }

    return String(left.title || '').localeCompare(String(right.title || ''), 'ru');
  });
}

async function loadPopularEvents() {
  const popularGrid = document.getElementById('popularEventsGrid');
  if (!popularGrid) return;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  try {
    const response = await fetch('/api/events', { signal: controller.signal });
    const events = await response.json();
    if (!Array.isArray(events)) {
      throw new Error('Некорректный формат ответа');
    }

    const popularEvents = getPopularEvents(events);
    renderHero(popularEvents[0] || null);
    renderPopular(popularEvents);
  } catch (err) {
    console.error('Ошибка загрузки популярных мероприятий:', err);
    renderHero(null);
    popularGrid.innerHTML = '<p style="color: var(--red-color);">Не удалось загрузить популярные события</p>';
  } finally {
    clearTimeout(timeoutId);
  }
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

function getSelectedTags() {
  return Array.from(document.querySelectorAll('.filter-chip.active'))
    .map((button) => button.dataset.tag)
    .filter(Boolean);
}

function normalizeSearchText(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function levenshteinDistance(left, right) {
  if (left === right) return 0;
  if (!left.length) return right.length;
  if (!right.length) return left.length;

  const rows = left.length + 1;
  const cols = right.length + 1;
  const matrix = Array.from({ length: rows }, () => new Array(cols).fill(0));

  for (let row = 0; row < rows; row += 1) matrix[row][0] = row;
  for (let col = 0; col < cols; col += 1) matrix[0][col] = col;

  for (let row = 1; row < rows; row += 1) {
    for (let col = 1; col < cols; col += 1) {
      const cost = left[row - 1] === right[col - 1] ? 0 : 1;
      matrix[row][col] = Math.min(
        matrix[row - 1][col] + 1,
        matrix[row][col - 1] + 1,
        matrix[row - 1][col - 1] + cost
      );
    }
  }

  return matrix[rows - 1][cols - 1];
}

function getTypoTolerance(queryLength) {
  if (queryLength <= 4) return 0;
  if (queryLength <= 8) return 1;
  return 2;
}

function titleMatchesQuery(eventTitle, rawQuery) {
  const query = normalizeSearchText(rawQuery);
  if (!query) {
    return true;
  }

  const normalizedTitle = normalizeSearchText(eventTitle);
  if (!normalizedTitle) {
    return false;
  }

  if (normalizedTitle.includes(query)) {
    return true;
  }

  const titleWords = normalizedTitle.split(' ').filter(Boolean);
  const queryWords = query.split(' ').filter(Boolean);

  const fullDistance = levenshteinDistance(normalizedTitle, query);
  const fullTolerance = getTypoTolerance(query.length);
  if (fullDistance <= fullTolerance) {
    return true;
  }

  return queryWords.every((queryWord) => {
    const wordTolerance = getTypoTolerance(queryWord.length);
    return titleWords.some((titleWord) => {
      if (titleWord.includes(queryWord) || queryWord.includes(titleWord)) {
        return true;
      }
      return levenshteinDistance(titleWord, queryWord) <= wordTolerance;
    });
  });
}

function getCurrentFilters() {
  return {
    title: document.getElementById('titleFilter')?.value || '',
    dateFrom: document.getElementById('dateFromFilter')?.value || '',
    dateTo: document.getElementById('dateToFilter')?.value || '',
    tags: getSelectedTags()
  };
}

function hasActiveFilters(filters = {}) {
  return Boolean(
    normalizeSearchText(filters.title || '')
      || filters.dateFrom
      || filters.dateTo
      || (Array.isArray(filters.tags) && filters.tags.length)
  );
}

async function loadEvents(filters = {}) {
  const grid = document.getElementById('eventsGrid');
  if (!grid) return;

  grid.innerHTML = '';
  renderedCount = 0;

  try {
    const params = new URLSearchParams();
    if (filters.dateFrom) params.append('dateFrom', filters.dateFrom);
    if (filters.dateTo) params.append('dateTo', filters.dateTo);
    if (Array.isArray(filters.tags)) {
      filters.tags.forEach((tag) => params.append('tags', tag));
    }

    const response = await fetch(`/api/events?${params.toString()}`);
    const events = await response.json();

    if (!Array.isArray(events)) {
      throw new Error('Некорректный формат ответа');
    }

    allLoadedEvents = [...events]
      .filter((event) => titleMatchesQuery(event.title, filters.title))
      .sort((a, b) => new Date(a.eventDate) - new Date(b.eventDate));

    if (!hasActiveFilters(filters)) {
      const popularEvents = getPopularEvents(allLoadedEvents);
      renderHero(popularEvents[0] || null);
      renderPopular(popularEvents);
    }
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

function applyFilters() {
  loadEvents(getCurrentFilters());
}

function resetFilters() {
  const titleFilter = document.getElementById('titleFilter');
  const dateFromFilter = document.getElementById('dateFromFilter');
  const dateToFilter = document.getElementById('dateToFilter');

  if (titleFilter) titleFilter.value = '';
  if (dateFromFilter) dateFromFilter.value = '';
  if (dateToFilter) dateToFilter.value = '';

  document.querySelectorAll('.filter-chip.active').forEach((button) => {
    button.classList.remove('active');
    button.setAttribute('aria-pressed', 'false');
  });

  loadEvents({});
  loadPopularEvents();
}

function formatDate(dateString) {
  return new Date(dateString).toLocaleString('ru-RU', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow'
  });
}

function truncateAddress(address, maxLength = 30) {
  return address.length > maxLength
    ? address.substring(0, maxLength) + '...'
    : address;
}

document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('eventsGrid')) {
    return;
  }

  loadEvents({});
  loadPopularEvents();

  const loadMoreBtn = document.getElementById('loadMoreBtn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', renderNextPage);
  }

  document.getElementById('titleFilter')?.addEventListener('input', applyFilters);
  document.getElementById('dateFromFilter')?.addEventListener('change', applyFilters);
  document.getElementById('dateToFilter')?.addEventListener('change', applyFilters);

  document.querySelectorAll('.filter-chip').forEach((button) => {
    button.addEventListener('click', () => {
      button.classList.toggle('active');
      button.setAttribute('aria-pressed', button.classList.contains('active') ? 'true' : 'false');
      applyFilters();
    });
  });
});
