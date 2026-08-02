/**
 * MAIA PWA service worker —— 極簡：讓 app 可安裝、離線時至少給殼。
 *
 * ⚠ 交易 app 的鐵律：**/api/* 永遠走網路、絕不快取**。餘額、掛單、行情、
 *   下單全都要即時，拿到一份快取的舊帳戶資料比拿不到更危險。這支只快取
 *   「殼」（HTML/JS/圖示），資料一律穿透。
 *
 * 只在正式環境註冊（見 main.tsx 的 import.meta.env.PROD 守衛）——
 * dev 註冊會攔截 Vite HMR。
 */
const CACHE = 'maia-shell-v1';
const SHELL = ['/', '/index.html', '/config.js', '/icon-192.png', '/icon-512.png', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  // addAll 對單一資源失敗會整批失敗，逐一放進去比較耐命
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => undefined))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;               // POST（下單/對話 SSE）一律穿透
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // 跨源（若有）不插手
  if (url.pathname.startsWith('/api/')) return;    // ★ API 永不快取，永遠走網路

  // 殼資源：網路優先、成功就更新快取，離線才回快取；連 '/' 都拿不到時退回首頁殼
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((m) => m || caches.match('/'))),
  );
});
