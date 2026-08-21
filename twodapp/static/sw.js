const CACHE_NAME = '2d-parser-v1';
const STATIC_ASSETS = [
    '/',
    '/static/icon-192.png',
    '/static/icon-512.png',
    '/static/manifest.json',
    'https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6/css/all.min.css',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap'
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);

    // Always fetch API, login, and admin requests from network
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/') || url.pathname.startsWith('/login')) {
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
        return;
    }

    // Network-first for navigation
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).then((resp) => {
                const clone = resp.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
                return resp;
            }).catch(() => caches.match(e.request))
        );
        return;
    }

    // Cache-first for static assets
    e.respondWith(
        caches.match(e.request).then((cached) => {
            if (cached) return cached;
            return fetch(e.request).then((resp) => {
                if (resp.ok && e.request.method === 'GET' && url.origin === self.location.origin) {
                    const clone = resp.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
                }
                return resp;
            });
        })
    );
});
