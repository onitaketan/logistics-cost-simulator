/* 在庫管理PWA Service Worker
   方針: 同一オリジンのファイルはネットワーク優先＋キャッシュ退避（オフライン耐性）。
   Supabase/CDN等の外部通信はそのままネットワークへ通す。 */
const CACHE = "inv-pwa-v5";
const SHELL = [
  "inventory-staff.html",
  "inventory-cloud.html",
  "icon-192.png",
  "icon-512.png",
  "icon-180.png",
  "app-staff.webmanifest",
  "app-cloud.webmanifest"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // 外部(API/CDN)はSWで触らない
  const isNav = req.mode === "navigate";
  // ナビゲーションは常に再検証して最新HTMLを取得（配信直後の古いHTML回避）
  const fetchReq = isNav ? new Request(req, { cache: "no-cache" }) : req;
  e.respondWith(
    fetch(fetchReq)
      .then(res => {
        // 正常な自サイト応答のみキャッシュ（404/5xx や不透明応答は退避しない）
        if (res && res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then(m => {
        if (m) return m;
        // 最終フォールバック: 要求先に応じて店長/スタッフ画面を出し分け
        const fallback = url.pathname.includes("cloud") ? "inventory-cloud.html" : "inventory-staff.html";
        return caches.match(fallback);
      }))
  );
});
