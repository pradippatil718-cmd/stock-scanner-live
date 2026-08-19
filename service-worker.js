// Minimal service worker — just enough to make the app installable
// (Chrome requires a registered service worker with a fetch handler).
// This app always needs fresh live market data, so we deliberately do NOT
// cache API responses — only a pass-through fetch handler is registered.

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Pass-through: always go to network. No offline caching of market data.
  event.respondWith(fetch(event.request));
});
