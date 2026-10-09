/* Parcel Finder service worker: offline-ish use for Drive mode.
   - app shell (HTML/JS/CSS/icons/Leaflet): network-first, falls back to the cached copy offline
   - data/meta.json: network-first (so a new data build is picked up), cached copy offline
   - data packs (data/*.gz?v=<build>): cache-first; when a new build arrives, older versions of the same file are deleted
   - map tiles (Esri / OSM, CORS only): stale-while-revalidate, capped at ~1,500 tiles
   Nothing is sent anywhere: this only caches GET requests the page already makes. */
const SHELL = 'pf-shell-v2', DATA = 'pf-data', TILES = 'pf-tiles', MAX_TILES = 1500;
const SHELL_FILES = ['./', 'index.html', 'styles.css', 'app.js', 'saved.js', 'drive.js', 'lenders.js', 'lenders-page.js', 'manifest.webmanifest',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png', 'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css', 'vendor/leaflet/images/layers.png', 'vendor/leaflet/images/layers-2x.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => Promise.all(SHELL_FILES.map(u => c.add(new Request(u, { cache: 'reload' })).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('pf-shell-') && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
async function networkFirst(req, cacheName, key) {
  const c = await caches.open(cacheName);
  try {
    const r = await fetch(req);
    if (r && r.ok) c.put(key || req, r.clone());
    return r;
  } catch (err) {
    const hit = await c.match(key || req, { ignoreSearch: true });
    if (hit) return hit;
    if (req.mode === 'navigate') { const idx = await c.match('index.html', { ignoreSearch: true }); if (idx) return idx; }
    throw err;
  }
}
async function dataCacheFirst(req) {
  const c = await caches.open(DATA), hit = await c.match(req);
  if (hit) return hit;
  const r = await fetch(req);
  if (r && r.ok) {
    await c.put(req, r.clone());
    const u = new URL(req.url), path = u.pathname;   // prune other builds of this file
    for (const k of await c.keys()) { const ku = new URL(k.url); if (ku.pathname === path && ku.search !== u.search) c.delete(k); }
  }
  return r;
}
async function tileSWR(req) {
  const c = await caches.open(TILES), hit = await c.match(req);
  const net = fetch(req).then(async r => {
    if (r && r.ok && r.type !== 'opaque') { await c.put(req, r.clone()); trimTiles(c); }
    return r;
  }).catch(() => hit);
  return hit || net;
}
let trimming = false;
async function trimTiles(c) {
  if (trimming) return; trimming = true;
  try { const ks = await c.keys(); if (ks.length > MAX_TILES) for (const k of ks.slice(0, ks.length - MAX_TILES)) await c.delete(k); } finally { trimming = false; }
}
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const u = new URL(req.url);
  if (u.origin === location.origin) {
    if (/\/data\/meta\.json$/.test(u.pathname)) return e.respondWith(networkFirst(req, DATA));
    if (/\/data\/.+\.gz$/.test(u.pathname) && u.searchParams.has('v')) return e.respondWith(dataCacheFirst(req));
    if (/\/data\//.test(u.pathname)) return;
    return e.respondWith(networkFirst(req, SHELL, req.mode === 'navigate' ? 'index.html' : undefined));
  }
  if (/\/tile\/\d+\/\d+\/\d+$/.test(u.pathname) || /tile\.openstreetmap\.org$/.test(u.hostname)) return e.respondWith(tileSWR(req));
  if (/fonts\.(googleapis|gstatic)\.com$/.test(u.hostname)) return e.respondWith(networkFirst(req, SHELL));
});
