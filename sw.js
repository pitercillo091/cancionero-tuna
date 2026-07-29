const CACHE_NAME = 'tuna-v6';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './img/banner.jpg',
  './img/banner-sm.jpg',
  './img/icon-192.jpg',
  './img/icon-512.jpg',
  './img/logo-header.jpg',
  './img/whatsapp.png',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
