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

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || "/home";
  const url = link.startsWith("http") ? link : self.location.origin + link;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
