const CACHE_NAME = 'lovers-space-v3';
const URLS_TO_CACHE = [
    '/static/manifest.json'
];

// 安装：立即激活 + 只缓存确定能成功的资源
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(URLS_TO_CACHE))
            .then(() => self.skipWaiting())
            .catch((err) => {
                console.error('SW install cache error:', err);
                // 即使缓存失败也继续激活
                return self.skipWaiting();
            })
    );
});

// 激活：立即接管所有页面
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n)))
        ).then(() => self.clients.claim())
    );
});

// 请求拦截：网络优先，缓存兜底
self.addEventListener('fetch', (event) => {
    // 非 GET 请求不缓存
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // 只缓存成功的页面请求
                if (response.ok && response.type === 'basic') {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});

// 接收推送通知
self.addEventListener('push', (event) => {
    let data = { title: '情侣小窝', body: '你有新消息！' };
    if (event.data) {
        try { data = event.data.json(); } catch(e) { data.body = event.data.text(); }
    }
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/icon.png',
            badge: '/static/icon.png',
            vibrate: [200, 100, 200]
        })
    );
});

// 点击通知后打开页面
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if (client.url.includes('zyxcookforzyj') && 'focus' in client) {
                    return client.focus();
                }
            }
            return clients.openWindow('/');
        })
    );
});
