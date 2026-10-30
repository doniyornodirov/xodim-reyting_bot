// Service Worker for Xodim-Reyting CRM PWA
const CACHE_NAME = 'xodim-crm-cache-v2';

const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon.svg'
];

// O'rnatish bosqichi (Install)
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Statik fayllarni keshga olishda ogohlantirish:', err);
      });
    })
  );
  self.skipWaiting();
});

// Faollashish bosqichi (Activate) - eski keshlarni tozalash
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// So'rovlarni tutib olish (Fetch)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // MUHIM XAVFSIZLIK VA MA'LUMOTLAR ANIQLIGI QOIDASI:
  // /api/ so'rovlari va barcha POST, PUT, DELETE, PATCH so'rovlari KESHGA OLINMAYDI.
  // Har doim to'g'ridan-to'g'ri real-vaqtdagi serverga (Render/Supabase) yuboriladi.
  if (event.request.method !== 'GET' || url.pathname.startsWith('/api/')) {
    return; // Tarmoqqa to'g'ridan-to'g'ri o'tkaziladi
  }

  // Statik fayllar (HTML, CSS, JS, Ikonkalar) uchun Network-First strategiyasi:
  // Avval yangi versiyani tarmoqdan oladi, agar internet yo'q bo'lsa keshdan ko'rsatadi.
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Internet yo'q bo'lsa keshdan qaytaradi
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          if (event.request.destination === 'document') {
            return caches.match('/');
          }
        });
      })
  );
});
