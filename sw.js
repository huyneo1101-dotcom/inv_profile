// BTC Tín Hiệu — service worker
// network-first cho dữ liệu mới, cache dự phòng để mở offline.
var C = 'btc-tin-hieu-v3';
// Chỉ precache vỏ app — KHÔNG cache data/ (để web luôn lấy JSON mới, tránh hiện số cũ).
var SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg'];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(caches.open(C).then(function (c) {
    // addAll fail nếu 1 file thiếu → nạp từng cái, bỏ qua cái lỗi
    return Promise.all(SHELL.map(function (u) {
      return c.add(u).catch(function () {});
    }));
  }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== C; }).map(function (k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  var url = e.request.url;
  // KHÔNG can thiệp: API bên thứ ba VÀ file data/ (luôn lấy trực tiếp, không cache)
  if (url.indexOf('/data/') !== -1
      || url.indexOf('api.coingecko.com') !== -1 || url.indexOf('alternative.me') !== -1
      || url.indexOf('binance.com') !== -1) return;
  e.respondWith(
    fetch(e.request).then(function (r) {
      var cp = r.clone();
      caches.open(C).then(function (c) { c.put(e.request, cp); });
      return r;
    }).catch(function () {
      return caches.match(e.request).then(function (m) { return m || caches.match('./index.html'); });
    })
  );
});
