// ig-saves-to-notion: read YOUR OWN saved posts inside YOUR OWN logged-in instagram.com tab.
// No passwords, cookies or tokens are copied anywhere. The tab asks Instagram for your saved feed,
// the same request instagram.com makes when you open Saved, and keeps the results in this tab.
//
// Claude runs this with the browser's javascript tool, in this order:
//   0. window.__savesConfig = {...}   the line printed by `python3 saves.py browser-config`
//   1. this whole file                starts the walk. Poll JSON.stringify(window.__sync) until running is false.
//   2. window.__download()            saves instagram-saves-<date>.json to Downloads (one file, easiest), or
//      window.__show(i)               shows chunk i (10 saves) as text on the page, to read with get_page_text.
//   3. window.__commit()              once the saves are safely in saves.json or Notion. The next run skips them.
//
// First ever run in this browser: window.__seedKnown('') says "nothing synced yet".
// New browser, saves already in Notion: window.__seedKnown('id1,id2,...') with the Media IDs you have.

(function (root) {
  'use strict';
  const KNOWN_KEY = 'rocha_coded_saves_known';
  const TYPES = {1: 'Post', 2: 'Reel', 8: 'Carousel'};
  const PAGE_CAP = 100;        // a hard ceiling: your saves, never a crawl
  const PAUSE_MS = 1500;       // a calm pace between pages, like scrolling

  const pad = n => String(n).padStart(2, '0');
  const iso = ts => {
    if (typeof ts !== 'number' || ts <= 0) return '';
    const d = new Date(ts * 1000);
    return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) + 'T' +
      pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()) + ':' + pad(d.getUTCSeconds()) + '.000Z';
  };
  const num = v => (Number.isInteger(v) ? v : null);

  // One media object from the saved feed -> one plain save record. Mirrors parse_media() in saves_core.py.
  function toSave(media) {
    const code = media && (media.code || media.shortcode);
    if (!code || !media.id) return null;
    const cap = media.caption && typeof media.caption === 'object' ? media.caption : null;
    const user = media.user || {};
    return {
      id: String(media.id),
      code: String(code),
      url: 'https://www.instagram.com/p/' + code + '/',
      type: TYPES[media.media_type] || 'Post',
      author: String(user.username || ''),
      caption: cap ? String(cap.text || '') : '',
      posted: iso(media.taken_at),
      likes: num(media.like_count),
      comments: num(media.comment_count),
      plays: num(media.play_count || media.ig_play_count || media.view_count),
    };
  }

  function parseFeedPage(data) {
    const items = (data && data.items) || [];
    return items.map(item => toSave(item && item.media ? item.media : item)).filter(Boolean);
  }

  const sinceTs = since => (since ? Date.parse(since + 'T00:00:00Z') / 1000 : 0);

  // One page of the walk. Returns a stop reason, or '' to keep going. Mirrors walk() in saves_core.py.
  function step(data, known, out, state, cutoff) {
    const medias = ((data && data.items) || []).map(i => (i && i.media ? i.media : i));
    if (!medias.length) return 'end of saved feed';
    if (cutoff && medias.every(m => m && m.taken_at && m.taken_at < cutoff)) return 'reached posts older than since';
    let fresh = 0;
    for (const save of parseFeedPage(data)) {
      if (known.has(save.id)) continue;
      known.add(save.id);
      out.push(save);
      fresh++;
    }
    state.knownRun = fresh ? 0 : state.knownRun + 1;
    if (state.knownRun === 2) return 'caught up';
    if (!data.more_available) return 'end of saved feed';
    return '';
  }

  // The same walk over pages already in hand (tests use this; the browser fetches page by page).
  function walk(pages, knownIds, cfg) {
    const known = new Set(knownIds), out = [], state = {knownRun: 0};
    const max = Math.min((cfg && cfg.maxPages) || 20, PAGE_CAP), cutoff = sinceTs(cfg && cfg.since);
    for (let n = 0; n < pages.length; n++) {
      if (n >= max) return {saves: out, stop: 'page limit reached'};
      const stop = step(pages[n], known, out, state, cutoff);
      if (stop) return {saves: out, stop};
    }
    return {saves: out, stop: 'no more pages'};
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {toSave, parseFeedPage, walk, iso};
    return;
  }

  // ---------- in the browser ----------
  const cfg = root.__savesConfig || {};
  const status = root.__sync = {running: true, feedPages: 0, fresh: 0, chunks: 0, stop: ''};
  root.__saves = [];

  root.__seedKnown = ids => {
    const list = String(ids || '').split(',').map(s => s.trim()).filter(Boolean);
    localStorage.setItem(KNOWN_KEY, JSON.stringify(list));
    return 'known saves: ' + list.length;
  };

  root.__show = i => {
    const chunk = root.__saves.slice(i * 10, i * 10 + 10);
    document.title = 'chunk ' + i;
    document.body.innerHTML = '<article><pre id="saves-chunk" style="white-space:pre-wrap"></pre></article>';
    document.getElementById('saves-chunk').textContent = JSON.stringify(chunk);
    return 'chunk ' + i + ': ' + chunk.length + ' saves';
  };

  root.__download = () => {
    const blob = new Blob([JSON.stringify({saves: root.__saves}, null, 1)], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'instagram-saves-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    return 'downloaded ' + root.__saves.length + ' saves as ' + a.download;
  };

  root.__commit = () => {
    const known = new Set(JSON.parse(localStorage.getItem(KNOWN_KEY) || '[]'));
    root.__saves.forEach(s => known.add(s.id));
    localStorage.setItem(KNOWN_KEY, JSON.stringify([...known]));
    return 'known saves: ' + known.size;
  };

  (async () => {
    try {
      const stored = localStorage.getItem(KNOWN_KEY);
      if (stored === null) {
        status.stop = "no known list in this browser: run window.__seedKnown('') on your first ever run, " +
          "or window.__seedKnown('id1,id2') with the Media IDs already in Notion";
        return;
      }
      const known = new Set(JSON.parse(stored));
      const state = {knownRun: 0}, cutoff = sinceTs(cfg.since);
      const max = Math.min(Number(cfg.maxPages) || 20, PAGE_CAP);
      let maxId = null;
      for (let page = 0; page < max; page++) {
        const url = '/api/v1/feed/saved/posts/' + (maxId ? '?max_id=' + encodeURIComponent(maxId) : '');
        // X-IG-App-ID is the public id instagram.com itself sends with this request. It is not a secret.
        const response = await fetch(url, {headers: {'X-IG-App-ID': '936619743392459'},
          credentials: 'include', redirect: 'manual'});
        if (response.status !== 200) {
          status.stop = response.type === 'opaqueredirect' ? 'not logged in to Instagram in this browser'
            : 'Instagram returned HTTP ' + response.status + '. Wait a while and try again.';
          return;
        }
        const data = await response.json();
        status.feedPages++;
        const stop = step(data, known, root.__saves, state, cutoff);
        status.fresh = root.__saves.length;
        status.chunks = Math.ceil(root.__saves.length / 10);
        if (stop) { status.stop = stop; return; }
        maxId = data.next_max_id;
        await new Promise(resolve => setTimeout(resolve, PAUSE_MS));
      }
      status.stop = 'page limit reached (max_pages in config.json)';
    } catch (error) {
      status.stop = 'error: ' + String(error);
    } finally {
      status.running = false;
    }
  })();
  return 'sync started';
})(typeof window !== 'undefined' ? window : globalThis);
