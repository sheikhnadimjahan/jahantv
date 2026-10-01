/**
 * DAINIK JAHAN IPTV — USER PREFERENCES & PERSONALIZATION
 * Manages: Favorites, Watchlist, Recently Watched History
 */

const DJ_STORAGE_KEYS = {
  FAVORITES: 'dj_iptv_favorites',
  WATCHLIST: 'dj_iptv_watchlist',
  HISTORY: 'dj_iptv_history'
};

class DainikJahanUserManager {
  constructor() {
    this.favorites = this.load(DJ_STORAGE_KEYS.FAVORITES);
    this.watchlist = this.load(DJ_STORAGE_KEYS.WATCHLIST);
    this.history = this.load(DJ_STORAGE_KEYS.HISTORY);
  }

  load(key) {
    try {
      const data = localStorage.getItem(key);
      return data ? JSON.parse(data) : [];
    } catch (e) {
      console.warn('Storage read error:', e);
      return [];
    }
  }

  save(key, data) {
    try {
      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
      console.warn('Storage write error:', e);
    }
  }

  // Favorites
  isFavorite(type, id) {
    return this.favorites.some(item => item.id === id && item.type === type);
  }

  toggleFavorite(type, id, title) {
    if (this.isFavorite(type, id)) {
      this.favorites = this.favorites.filter(item => !(item.id === id && item.type === type));
      this.save(DJ_STORAGE_KEYS.FAVORITES, this.favorites);
      if (window.djShowToast) window.djShowToast(`'${title}' প্রিয় তালিকা থেকে সরানো হয়েছে`);
      return false;
    } else {
      this.favorites.unshift({ type, id, title, added_at: new Date().toISOString() });
      this.save(DJ_STORAGE_KEYS.FAVORITES, this.favorites);
      if (window.djShowToast) window.djShowToast(`'${title}' প্রিয় চ্যানেলে যুক্ত হয়েছে ❤️`);
      return true;
    }
  }

  // Watchlist
  isWatchlist(type, id) {
    return this.watchlist.some(item => item.id === id && item.type === type);
  }

  toggleWatchlist(type, id, title) {
    if (this.isWatchlist(type, id)) {
      this.watchlist = this.watchlist.filter(item => !(item.id === id && item.type === type));
      this.save(DJ_STORAGE_KEYS.WATCHLIST, this.watchlist);
      if (window.djShowToast) window.djShowToast(`'${title}' ওয়াচলিস্ট থেকে মুছে ফেলা হয়েছে`);
      return false;
    } else {
      this.watchlist.unshift({ type, id, title, added_at: new Date().toISOString() });
      this.save(DJ_STORAGE_KEYS.WATCHLIST, this.watchlist);
      if (window.djShowToast) window.djShowToast(`'${title}' পরে দেখার তালিকায় রাখা হয়েছে 🔖`);
      return true;
    }
  }

  // History
  recordHistory(type, id, title) {
    // Avoid duplicate head
    this.history = this.history.filter(item => !(item.id === id && item.type === type));
    this.history.unshift({ type, id, title, watched_at: new Date().toISOString() });
    if (this.history.length > 30) this.history.pop();
    this.save(DJ_STORAGE_KEYS.HISTORY, this.history);
  }

  clearHistory() {
    this.history = [];
    this.save(DJ_STORAGE_KEYS.HISTORY, []);
    if (window.djShowToast) window.djShowToast('দেখার ইতিহাস সম্পূর্ণ মুছে ফেলা হয়েছে');
  }
}

window.DainikJahanUser = new DainikJahanUserManager();
