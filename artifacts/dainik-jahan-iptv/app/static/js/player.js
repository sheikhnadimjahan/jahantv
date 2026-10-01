/**
 * DAINIK JAHAN IPTV — BROADCAST PLAYER ENGINE
 * Supports: HLS (m3u8), Native HTML5 Video, Authorized Official Embeds
 * Pipeline: Channel → Authorized Source → Validation → Health Check → Player → Live Playback
 */

class DainikJahanPlayer {
  constructor(options = {}) {
    this.container = document.getElementById(options.containerId || 'djPlayerContainer');
    this.videoElement = document.getElementById(options.videoId || 'djVideoElement');
    this.iframeElement = document.getElementById(options.iframeId || 'djIframeElement');
    this.metaContainer = document.getElementById(options.metaId || 'djPlayerMeta');
    this.diagnosticsBox = document.getElementById('djDiagnosticsHud');
    this.currentChannel = null;
    this.hlsInstance = null;
    this.currentQuality = 'auto';
    this.isMuted = false;
    this.statsTimer = null;
    this.fallbackAttempted = false;
    
    this.initControls();
  }

  initControls() {
    const playPauseBtn = document.getElementById('djBtnPlayPause');
    const theaterBtn = document.getElementById('djBtnTheater');
    const pipBtn = document.getElementById('djBtnPip');
    const diagBtn = document.getElementById('djBtnDiag');
    const fullscreenBtn = document.getElementById('djBtnFullscreen');
    const volumeBtn = document.getElementById('djBtnVolume');
    const fallbackBtn = document.getElementById('djBtnFallback');

    if (playPauseBtn) {
      playPauseBtn.addEventListener('click', () => this.togglePlayPause());
    }
    if (theaterBtn) {
      theaterBtn.addEventListener('click', () => this.toggleTheater());
    }
    if (pipBtn) {
      pipBtn.addEventListener('click', () => this.togglePip());
    }
    if (diagBtn) {
      diagBtn.addEventListener('click', () => this.toggleDiagnostics());
    }
    if (fullscreenBtn) {
      fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
    }
    if (volumeBtn) {
      volumeBtn.addEventListener('click', () => this.toggleMute());
    }
    if (fallbackBtn) {
      fallbackBtn.addEventListener('click', () => this.triggerFallback());
    }

    // Video error detection
    if (this.videoElement) {
      this.videoElement.addEventListener('error', (e) => {
        console.warn('Video element encountered error:', e);
        this.reportStatus('degraded', 'স্ট্রিম পুনরুদ্ধার করা হচ্ছে (স্বয়ংক্রিয় ফলব্যাক)');
        this.triggerFallback();
      });
      this.videoElement.addEventListener('playing', () => {
        this.reportStatus('live', 'সরাসরি সম্প্রচারিত (Live)');
        this.updatePlayBtn(true);
      });
      this.videoElement.addEventListener('pause', () => {
        this.updatePlayBtn(false);
      });
    }
  }

  async loadChannel(channelData) {
    if (!channelData) return;
    this.currentChannel = channelData;
    this.fallbackAttempted = false;
    console.log(`[DJ-IPTV] Loading Channel: ${channelData.name} (${channelData.id})`);

    // Step 1: Validation
    this.reportStatus('validating', 'উৎস যাচাই করা হচ্ছে...');
    this.updateMeta(channelData);

    // Step 2: Health Check & Routing
    const source = channelData.primary_source || channelData.secondary_source || channelData.fallback_source;
    if (!source) {
      this.reportStatus('offline', 'অনুমোদিত স্ট্রিম ঠিকানা পাওয়া যায়নি');
      if (window.djShowToast) window.djShowToast('এই চ্যানেলের জন্য কোনো স্ট্রিম ঠিকানা দেওয়া নেই');
      return;
    }
    const isEmbed = channelData.stream_type === 'embed' || (source && source.includes('youtube'));

    if (isEmbed) {
      this.playEmbed(source);
    } else {
      this.playDirect(source);
    }

    // Record user history
    if (window.DainikJahanUser) {
      window.DainikJahanUser.recordHistory(
        channelData.user_content_type || 'channel',
        channelData.id,
        channelData.name
      );
    }

    this.startDiagnosticsHUD();
  }

  playDirect(streamUrl) {
    if (this.iframeElement) {
      this.iframeElement.style.display = 'none';
      this.iframeElement.src = '';
    }
    if (this.videoElement) {
      this.videoElement.style.display = 'block';

      // Check if HLS stream (.m3u8)
      if (streamUrl.includes('.m3u8') && window.Hls && window.Hls.isSupported()) {
        if (this.hlsInstance) {
          this.hlsInstance.destroy();
        }
        this.hlsInstance = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
          backBufferLength: 90
        });
        this.hlsInstance.loadSource(streamUrl);
        this.hlsInstance.attachMedia(this.videoElement);
        this.hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
          this.videoElement.play().catch(e => console.log('Autoplay deferred:', e));
        });
        this.hlsInstance.on(Hls.Events.ERROR, (event, data) => {
          if (data.fatal) {
            console.warn('Fatal HLS error, switching to fallback:', data);
            this.triggerFallback();
          }
        });
      } else {
        // Direct MP4 / WebM / HTML5 supported stream
        this.videoElement.src = streamUrl;
        this.videoElement.load();
        this.videoElement.play().catch(e => {
          console.log('Autoplay waiting for user interaction:', e);
        });
      }
    }
    this.reportStatus('validating', 'স্ট্রিমে সংযোগ করা হচ্ছে...');
  }

  playEmbed(embedUrl) {
    if (this.videoElement) {
      this.videoElement.pause();
      this.videoElement.style.display = 'none';
    }
    if (this.iframeElement) {
      this.iframeElement.style.display = 'block';
      // Append autoplay if needed
      let finalUrl = embedUrl;
      if (!finalUrl.includes('autoplay=')) {
        finalUrl += (finalUrl.includes('?') ? '&' : '?') + 'autoplay=1&mute=0&rel=0&modestbranding=1';
      }
      this.iframeElement.src = finalUrl;
      this.reportStatus('live', 'অনুমোদিত এমবেড সম্প্রচার (Live Embed)');
    }
  }

  triggerFallback() {
    if (!this.currentChannel) return;
    if (this.fallbackAttempted) {
      this.reportStatus('offline', 'বর্তমানে সিগন্যাল পাওয়া যাচ্ছে না');
      this.updatePlayBtn(false);
      return;
    }
    this.fallbackAttempted = true;
    const fallback = this.currentChannel.fallback_source || '/static/images/sample_media/dainik_jahan_live.mp4';
    console.log('[DJ-IPTV] Switching to authorized fallback:', fallback);
    this.reportStatus('fallback', 'বিকল্প ব্যাকআপ সিগন্যাল সক্রিয়');
    if (this.iframeElement) {
      this.iframeElement.style.display = 'none';
    }
    if (this.videoElement) {
      this.videoElement.style.display = 'block';
      this.videoElement.src = fallback;
      this.videoElement.load();
      this.videoElement.play().catch(() => {});
    }
    if (window.djShowToast) {
      window.djShowToast('বিকল্প ব্যাকআপ সম্প্রচার চ্যানেল চালু করা হয়েছে');
    }
  }

  reportStatus(type, label) {
    const badge = document.getElementById('djPlayerStatusBadge');
    if (!badge) return;
    badge.className = `dj-player-status-badge dj-status-${type}`;
    badge.textContent = label;
  }

  updatePlayBtn(isPlaying) {
    const btn = document.getElementById('djBtnPlayPause');
    if (btn) {
      btn.innerHTML = isPlaying ? '<span>⏸ বিরতি</span>' : '<span>▶ চালু</span>';
    }
  }

  togglePlayPause() {
    if (this.videoElement && this.videoElement.style.display !== 'none') {
      if (this.videoElement.paused) {
        this.videoElement.play().catch(() => {
          if (window.djShowToast) window.djShowToast('এই স্ট্রিমটি এখন চালানো যাচ্ছে না');
        });
      } else {
        this.videoElement.pause();
      }
    } else if (window.djShowToast) {
      window.djShowToast('এমবেড প্লেয়ারের নিজস্ব চালু/বিরতি কন্ট্রোল ব্যবহার করুন');
    }
  }

  toggleTheater() {
    const theater = document.querySelector('.dj-player-theater');
    if (theater) {
      theater.classList.toggle('theater-mode');
      if (theater.classList.contains('theater-mode')) {
        theater.style.gridTemplateColumns = '1fr';
      } else {
        theater.style.gridTemplateColumns = '1fr 360px';
      }
    }
  }

  async togglePip() {
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else if (this.videoElement && document.pictureInPictureEnabled) {
        await this.videoElement.requestPictureInPicture();
      } else if (window.djShowToast) {
        window.djShowToast('এই ব্রাউজার বা এমবেড স্ট্রিমে পিকচার-ইন-পিকচার সমর্থিত নয়');
      }
    } catch (err) {
      console.warn('PiP not available:', err);
      if (window.djShowToast) window.djShowToast('পিকচার-ইন-পিকচার চালু করা যায়নি');
    }
  }

  async toggleFullscreen() {
    const viewport = document.querySelector('.dj-player-viewport');
    try {
      if (!document.fullscreenElement && viewport && viewport.requestFullscreen) {
        await viewport.requestFullscreen();
      } else if (document.fullscreenElement && document.exitFullscreen) {
        await document.exitFullscreen();
      } else if (window.djShowToast) {
        window.djShowToast('এই ব্রাউজারে ফুলস্ক্রিন সমর্থিত নয়');
      }
    } catch (err) {
      console.warn('Fullscreen unavailable:', err);
      if (window.djShowToast) window.djShowToast('ফুলস্ক্রিন চালু করা যায়নি');
    }
  }

  toggleMute() {
    if (this.videoElement && this.videoElement.style.display !== 'none') {
      this.videoElement.muted = !this.videoElement.muted;
      this.isMuted = this.videoElement.muted;
      const btn = document.getElementById('djBtnVolume');
      if (btn) {
        btn.innerHTML = this.isMuted ? '<span>🔇 শব্দ বন্ধ</span>' : '<span>🔊 শব্দ চালু</span>';
      }
    } else if (window.djShowToast) {
      window.djShowToast('এমবেড প্লেয়ারের নিজস্ব শব্দ কন্ট্রোল ব্যবহার করুন');
    }
  }

  toggleDiagnostics() {
    if (this.diagnosticsBox) {
      const isVisible = this.diagnosticsBox.style.display === 'grid';
      this.diagnosticsBox.style.display = isVisible ? 'none' : 'grid';
    }
  }

  startDiagnosticsHUD() {
    if (this.statsTimer) clearInterval(this.statsTimer);
    this.statsTimer = setInterval(() => {
      const nodeEl = document.getElementById('hudNode');
      const resEl = document.getElementById('hudRes');
      const latEl = document.getElementById('hudLatency');
      const bitEl = document.getElementById('hudBitrate');

      if (nodeEl && this.currentChannel) {
        nodeEl.textContent = this.currentChannel.federation_node || 'উৎসের তথ্য নেই';
      }
      if (resEl && this.currentChannel) {
        const width = this.videoElement && this.videoElement.videoWidth;
        const height = this.videoElement && this.videoElement.videoHeight;
        resEl.textContent = width && height
          ? `${width}×${height}`
          : (this.currentChannel.resolution || 'উৎসের তথ্য নেই');
      }
      if (latEl) {
        const rtt = navigator.connection && navigator.connection.rtt;
        latEl.textContent = Number.isFinite(rtt) ? `${rtt} ms` : 'মাপা যায়নি';
      }
      if (bitEl && this.currentChannel) {
        const level = this.hlsInstance && this.hlsInstance.levels[this.hlsInstance.currentLevel];
        bitEl.textContent = level && level.bitrate
          ? `${Math.round(level.bitrate / 1000)} kbps`
          : 'উৎসের তথ্য নেই';
      }
    }, 2000);
  }

  updateMeta(channel) {
    const titleEl = document.getElementById('djMetaTitle');
    const descEl = document.getElementById('djMetaDesc');
    const catEl = document.getElementById('djMetaCategory');
    const authEl = document.getElementById('djMetaAuth');
    const resEl = document.getElementById('djMetaRes');
    const favoriteBtn = document.getElementById('djMetaFavBtn');

    if (titleEl) titleEl.textContent = channel.name;
    if (descEl) descEl.textContent = channel.description_bn || channel.description_en;
    if (catEl) catEl.textContent = channel.category_bn || channel.category;
    if (authEl) authEl.textContent = channel.authorized_by;
    if (resEl) resEl.textContent = channel.resolution;

    if (favoriteBtn && window.DainikJahanUser) {
      const contentType = channel.user_content_type || 'channel';
      const isFav = window.DainikJahanUser.isFavorite(contentType, channel.id);
      favoriteBtn.innerHTML = isFav ? '❤️ ফেভারিট থেকে সরান' : '🤍 প্রিয় চ্যানেলে যোগ করুন';
      favoriteBtn.onclick = () => {
        window.DainikJahanUser.toggleFavorite(contentType, channel.id, channel.name);
        this.updateMeta(channel);
      };
    }
  }
}

// Global player instantiator
window.initDainikJahanPlayer = function(options) {
  window.djPlayer = new DainikJahanPlayer(options);
  return window.djPlayer;
};
