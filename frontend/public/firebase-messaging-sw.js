// Oryntix web push (Firebase Cloud Messaging). Config arrives in the registration URL (?config=base64 JSON).
self.importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js");
self.importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js");

const params = new URL(self.location.href).searchParams;
let config = null;
try { config = JSON.parse(atob(params.get("config") || "")); } catch (e) { config = null; }

let messaging = null;
try {
  if (config && config.apiKey && config.messagingSenderId) { self.firebase.initializeApp(config); messaging = self.firebase.messaging(); }
} catch (e) { messaging = null; }
if (messaging) {
  // Data-only payloads (we send `data` + webpush.notification): show a notification when the tab is closed/background.
  messaging.onBackgroundMessage((payload) => {
    const d = payload.data || {};
    const n = payload.notification || {};
    const title = n.title || d.title || "Oryntix";
    return self.registration.showNotification(title, {
      body: n.body || d.body || "",
      icon: "/brand/mark-512.png",
      badge: "/brand/mark-512.png",
      tag: d.tag || undefined,
      renotify: !!d.tag,
      data: { link: d.link || (payload.fcmOptions && payload.fcmOptions.link) || "/home", kind: d.kind || "system" },
    });
  });
}

// Assistant portraits are content-addressed (/api/portraits/{id}/{hash}.jpg) → cache-first forever, independent of proxy Cache-Control.
const PORTRAIT_CACHE = "oryntix-portraits-v1";
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith("/api/portraits/")) return;
  event.respondWith((async () => {
    const cache = await caches.open(PORTRAIT_CACHE);
    const hit = await cache.match(event.request, { ignoreSearch: true });
    if (hit) return hit;
    const res = await fetch(event.request);
    if (res && res.ok) {
      const headers = new Headers(res.headers); headers.set("Cache-Control", "public, max-age=31536000, immutable");
      const body = await res.clone().arrayBuffer();
      cache.put(event.request, new Response(body, { status: 200, headers })).catch(() => {});
    }
    return res;
  })());
});
self.addEventListener("activate", (event) => { event.waitUntil(self.clients.claim()); });
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || "/home";
  const url = link.startsWith("http") ? link : self.location.origin + link;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
