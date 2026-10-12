/* Shared YouTube player for every version of the site.
   Any link to a YouTube video (watch?v=, youtu.be/, shorts/) opens in an
   on-page player instead of leaving the site. Channel links are left alone.
   Embeds need the page served over http(s); from file:// YouTube refuses to play. */
(() => {
  const ID_RE = /(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([\w-]{11})/;

  const css = `
  .ytm{border:0;padding:0;background:transparent;max-width:none;max-height:none;width:100%;height:100%;margin:0;overflow:hidden}
  .ytm::backdrop{background:rgba(6,10,14,.86);backdrop-filter:blur(4px)}
  .ytm[open]{display:grid;place-items:center}
  .ytm .ytm-box{position:relative;width:min(1100px,92vw);display:grid;gap:12px}
  .ytm.short .ytm-box{width:min(420px,88vw)}
  .ytm .ytm-frame{position:relative;aspect-ratio:16/9;max-width:100%;max-height:78vh;background:#000;border-radius:10px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.5)}
  .ytm.short .ytm-frame{aspect-ratio:9/16;max-height:80vh;margin-inline:auto;height:80vh;width:auto}
  .ytm iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
  .ytm .ytm-bar{display:flex;justify-content:space-between;align-items:center;gap:16px;color:#F2F4F6;font:500 14px/1.3 system-ui,-apple-system,sans-serif}
  .ytm .ytm-bar a{color:#F2F4F6;opacity:.75}
  .ytm .ytm-x{all:unset;cursor:pointer;width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.12);color:#fff;font:400 22px/1 system-ui;flex:none}
  .ytm .ytm-x:hover{background:rgba(255,255,255,.24)}
  .ytm .ytm-x:focus-visible{outline:3px solid #fff;outline-offset:2px}
  .ytm .ytm-t{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const dlg = document.createElement('dialog');
  dlg.className = 'ytm';
  dlg.setAttribute('aria-label', 'Video player');
  dlg.innerHTML = `<div class="ytm-box">
      <div class="ytm-bar"><span class="ytm-t"></span><button class="ytm-x" type="button" aria-label="Close video">×</button></div>
      <div class="ytm-frame"></div>
      <div class="ytm-bar"><a class="ytm-out" target="_blank" rel="noopener">Watch on YouTube ↗</a></div>
    </div>`;
  document.body.appendChild(dlg);
  const frame = dlg.querySelector('.ytm-frame');

  function open(id, title, isShort){
    dlg.classList.toggle('short', !!isShort);
    dlg.querySelector('.ytm-t').textContent = title || '';
    dlg.querySelector('.ytm-out').href = isShort ? `https://www.youtube.com/shorts/${id}` : `https://www.youtube.com/watch?v=${id}`;
    frame.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&modestbranding=1&playsinline=1"
      title="${(title || 'YouTube video').replace(/"/g, '&quot;')}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
      referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>`;
    dlg.showModal();
    if (window.umami) window.umami.track('Video played', {title: title || id});
  }
  function close(){ frame.innerHTML = ''; if (dlg.open) dlg.close(); }

  dlg.querySelector('.ytm-x').addEventListener('click', close);
  dlg.addEventListener('click', e => { if (e.target === dlg) close(); });
  dlg.addEventListener('close', () => { frame.innerHTML = ''; });

  document.addEventListener('click', e => {
    const a = e.target.closest('a[href]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const m = a.href.match(ID_RE);
    if (!m) return;
    e.preventDefault();
    const title = a.dataset.title || (a.querySelector('h3')?.textContent) || a.textContent.replace(/^[▶\s]+/, '').trim();
    open(m[1], title, /\/shorts\//.test(a.href));
  });

  window.ABVideo = { open, close };
})();
