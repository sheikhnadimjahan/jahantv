/**
 * DAINIK JAHAN IPTV — MAIN APPLICATION LOGIC
 */

document.addEventListener('DOMContentLoaded', () => {
  console.log('[DJ-IPTV] Platform initialized.');

  // Toast helper
  window.djShowToast = function(msg) {
    let toast = document.getElementById('djGlobalToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'djGlobalToast';
      toast.className = 'dj-toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.display = 'flex';
    setTimeout(() => {
      toast.style.display = 'none';
    }, 3200);
  };

  // Search and channel filters share one state so combining them stays predictable.
  const searchInput = document.getElementById('djGlobalSearch');
  const searchCount = document.getElementById('djSearchCount');
  const searchCards = document.querySelectorAll('[data-search-card]');
  const filterChips = document.querySelectorAll('#channelFilters .dj-chip');
  let activeFilter = 'all';

  function applyHomeFilters() {
    const query = searchInput ? searchInput.value.toLocaleLowerCase().trim() : '';
    let matched = 0;

    searchCards.forEach(card => {
      const isChannel = card.hasAttribute('data-channel-json');
      const searchableText = [
        card.getAttribute('data-title') || '',
        card.getAttribute('data-category') || '',
        card.getAttribute('data-language') || '',
        card.getAttribute('data-country') || '',
        card.textContent || ''
      ].join(' ').toLocaleLowerCase();
      const matchesQuery = !query || searchableText.includes(query);

      let matchesFilter = true;
      if (isChannel && activeFilter === 'bangladesh') {
        matchesFilter = card.getAttribute('data-bangladesh') === 'true';
      } else if (isChannel && activeFilter === 'international') {
        matchesFilter = card.getAttribute('data-bangladesh') === 'false';
      } else if (isChannel && activeFilter !== 'all') {
        matchesFilter = (card.getAttribute('data-category') || '').toLowerCase() === activeFilter.toLowerCase();
      }

      const visible = matchesQuery && matchesFilter;
      card.style.display = visible ? '' : 'none';
      if (visible) matched += 1;
    });

    if (searchCount) {
      searchCount.textContent = query ? `${matched}টি মিল পাওয়া গেছে` : '';
    }
  }

  if (searchInput) searchInput.addEventListener('input', applyHomeFilters);
  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(item => item.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.getAttribute('data-filter') || 'all';
      applyHomeFilters();
    });
  });
  if (searchCards.length > 0) applyHomeFilters();

  // Channel Card Click handler -> Switch channel in player
  const channelCards = document.querySelectorAll('.dj-card[data-channel-json]');
  channelCards.forEach(card => {
    const playBtn = card.querySelector('.dj-card-play-btn');
    const channelJson = card.getAttribute('data-channel-json');
    if (channelJson && playBtn) {
      try {
        const channelData = JSON.parse(channelJson);
        playBtn.addEventListener('click', (e) => {
          e.preventDefault();
          if (window.djPlayer) {
            window.djPlayer.loadChannel(channelData);
            window.scrollTo({ top: 0, behavior: 'smooth' });
            window.djShowToast(`'${channelData.name}' চালু করা হয়েছে`);
          }
        });
      } catch (e) {
        console.error('Invalid channel JSON on card:', e);
      }
    }
  });

  // Favorite button on cards
  const favBtns = document.querySelectorAll('.dj-icon-btn[data-fav-id]');
  favBtns.forEach(btn => {
    const id = btn.getAttribute('data-fav-id');
    const title = btn.getAttribute('data-fav-title');
    if (window.DainikJahanUser && window.DainikJahanUser.isFavorite('channel', id)) {
      btn.classList.add('active');
      btn.innerHTML = '❤️';
    }
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (window.DainikJahanUser) {
        const isFav = window.DainikJahanUser.toggleFavorite('channel', id, title);
        btn.classList.toggle('active', isFav);
        btn.innerHTML = isFav ? '❤️' : '🤍';
      }
    });
  });

  // Sidebar Channel Click
  const sideItems = document.querySelectorAll('.dj-side-item[data-channel-json]');
  sideItems.forEach(item => {
    item.addEventListener('click', () => {
      sideItems.forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      const channelJson = item.getAttribute('data-channel-json');
      if (channelJson && window.djPlayer) {
        try {
          const data = JSON.parse(channelJson);
          window.djPlayer.loadChannel(data);
          window.djShowToast(`'${data.name}' চালু হয়েছে`);
        } catch (err) {}
      }
    });
  });
});
