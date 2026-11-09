// A media load failure must restore the preview and expose the source link.
document.addEventListener('error', (event) => {
  const video = event.target;
  if (!(video instanceof HTMLVideoElement)) return;
  const media = video.closest('[data-detail-video], [data-feature-media]');
  if (!media) return;
  media.classList.remove('loading', 'playing');
  media.querySelectorAll('.detail-video-loading, .featured-video-loading, .detail-video-error, .featured-video-error').forEach(el => el.remove());
  const message = document.createElement('div');
  message.className = 'detail-video-error';
  message.textContent = 'Não foi possível carregar o vídeo. ';
  const source = media.dataset.originalVideo || '';
  if (/^https:\/\//.test(source)) {
    const link = document.createElement('a');
    link.href = source;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Abrir vídeo original';
    message.append(link);
  }
  media.append(message);
}, true);

new MutationObserver(records => {
  for (const record of records) for (const node of record.addedNodes) {
    if (!(node instanceof Element)) continue;
    const videos = node.matches('video') ? [node] : node.querySelectorAll('video');
    for (const video of videos) {
      if (!video.closest('[data-detail-video], [data-feature-media]')) continue;
      setTimeout(() => {
        if (video.isConnected && video.readyState < 2) video.dispatchEvent(new Event('error'));
      }, 15000);
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });
