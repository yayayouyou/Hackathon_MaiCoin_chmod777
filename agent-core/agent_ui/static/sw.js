/* MAIA PWA service worker — 讓網頁可安裝、離線可開 app shell。
   API 一律走網路（即時行情不快取）；其餘 network-first、失敗回快取。 */
const CACHE = "maia-v1";
const SHELL = ["/", "https://cdn.jsdelivr.net/npm/chart.js",
  "/static/icon-192.png", "/static/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) return;   // 即時資料：交給網路，不攔截
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok && url.origin === location.origin) {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(req, clone));
        }
        return res;
      })
      .catch(() => caches.match(req).then((m) => m || caches.match("/")))
  );
});
