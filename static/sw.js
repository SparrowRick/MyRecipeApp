const CACHE_NAME = 'lovers-space-static-v9';
const STATIC_ASSETS = [
    '/static/manifest.json',
    '/static/icon.png',
    '/static/lucide.min.js',
    '/static/app.css',
    '/static/app.js'
];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((names) => Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) return;
    event.respondWith(
        caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
            if (response.ok) caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
            return response;
        }))
    );
});

self.addEventListener('push', (event) => {
    let data = { title: '情侣小窝', body: '你有新消息', url: '/' };
    if (event.data) {
        try { data = { ...data, ...event.data.json() }; }
        catch (_) { data.body = event.data.text(); }
    }
    event.waitUntil(self.registration.showNotification(data.title, {
        body: data.body,
        icon: '/static/icon.png',
        badge: '/static/icon.png',
        data: { url: data.url || '/' },
        vibrate: [160, 80, 160]
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const target = new URL(event.notification.data?.url || '/', self.location.origin).href;
    event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
        const existing = clientList.find((client) => client.url.startsWith(self.location.origin));
        if (existing) {
            existing.navigate(target);
            return existing.focus();
        }
        return clients.openWindow(target);
    }));
});
