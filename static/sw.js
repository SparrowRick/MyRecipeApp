const CACHE_NAME = 'lovers-space-v1';
const URLS_TO_CACHE = [
  '/',
  '/static/manifest.json',
  // 这里可以添加其他静态资源，如 CSS 或 JS
  // 注意：不要缓存动态页面（如 /recipes），否则更新了数据也看不到
];

// 安装 Service Worker
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Opened cache');
        return cache.addAll(URLS_TO_CACHE);
      })
  );
});

// 拦截网络请求
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        // 如果缓存里有，就用缓存的
        if (response) {
          return response;
        }
        // 否则去网络请求
        return fetch(event.request);
      })
  );
});

// 更新 Service Worker (清理旧缓存)
self.addEventListener('activate', (event) => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});
```

---

### 第4步：修改 `base.html` (引入 PWA)

我们需要告诉浏览器：“嘿，我有 PWA 功能哦！”

请修改您本地的 `templates/base.html`。

**1. 在 `<head>` 标签内（`<title>` 下方）添加：**

```html
    <!-- PWA Manifest -->
    <link rel="manifest" href="{{ url_for('static', filename='manifest.json') }}">
    <!-- iOS 支持 -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="我们的小窝">
    <link rel="apple-touch-icon" href="{{ url_for('static', filename='icon.png') }}">
    <!-- 主题色 (匹配 Tailwind 的 rose-500) -->
    <meta name="theme-color" content="#f43f5e">
```

**2. 在 `<body>` 标签的最底部（`</html>` 之前）添加注册脚本：**

```html
    <!-- 注册 Service Worker -->
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register("{{ url_for('static', filename='sw.js') }}")
                    .then((registration) => {
                        console.log('ServiceWorker registration successful with scope: ', registration.scope);
                    }, (err) => {
                        console.log('ServiceWorker registration failed: ', err);
                    });
            });
        }
    </script>
```

---

### 第5步：部署与体验

1.  **提交代码：**
    ```powershell
    git add .
    git commit -m "Feat: Add PWA support"
    git push
    ```

2.  **服务器更新：**
    ```bash
    cd /var/www/MyRecipeApp
    git pull
    # 不需要重启服务，因为只改了静态文件和模板，但重启一下更稳妥
    systemctl restart recipeapp