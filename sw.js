const CACHE = 'pitchiq-cache-v10';
const CORE = ['./', './index.html', './manifest.json', './icon-192.png', './icon-512.png', './logo-banner-512.png'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(CORE.map(path => new URL(path, self.registration.scope).href)))
      .catch(error => console.warn('PitchIQ offline shell cache incomplete:', error))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith('pitchiq-cache-') && key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const isData = /\/(data|predictions|odds|international)\.json$/.test(url.pathname) || url.pathname.endsWith('/daily/published_picks.json');
  if (isData) {
    // Ignore the page's cache-busting query string so offline copies remain reusable.
    const key = new Request(url.origin + url.pathname);
    event.respondWith(
      fetch(request)
        .then(async response => {
          if (response.ok) {
            const cache = await caches.open(CACHE);
            await cache.put(key, response.clone());
            return response;
          }
          // A server error or missing file should not discard a usable offline
          // snapshot. The page reads the snapshot's own updated timestamp and
          // labels old data as stale instead of presenting it as current.
          const cached = await caches.match(key);
          return cached || response;
        })
        .catch(async () => {
          const cached = await caches.match(key);
          if (cached) return cached;
          const empty = url.pathname.endsWith('/daily/published_picks.json') ? {version: 1, pending: [], results: [], sent_ids: []} :
            url.pathname.endsWith('/predictions.json') ? {} :
            url.pathname.endsWith('/odds.json') ? {events: []} :
            url.pathname.endsWith('/international.json') ? {fixtures: []} :
            {updated: null, matches: [], tables: {}};
          return new Response(JSON.stringify(empty), {
            headers: {'Content-Type': 'application/json; charset=utf-8'}
          });
        })
    );
    return;
  }

  if (request.mode === 'navigate') {
    const indexUrl = new URL('index.html', self.registration.scope).href;
    event.respondWith(
      fetch(request)
        .then(async response => {
          if (response.ok) {
            const cache = await caches.open(CACHE);
            await cache.put(indexUrl, response.clone());
          }
          return response;
        })
        .catch(async () => (await caches.match(request)) || (await caches.match(indexUrl)) || Response.error())
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(async response => {
        if (response.ok) {
          const cache = await caches.open(CACHE);
          await cache.put(request, response.clone());
        }
        return response;
      });
    })
  );
});
