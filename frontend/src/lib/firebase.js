import { initializeApp, getApps } from "firebase/app";
import { getMessaging, getToken, onMessage, isSupported, deleteToken } from "firebase/messaging";
import { api } from "./api";

export const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID,
};
const VAPID = process.env.REACT_APP_FIREBASE_VAPID_KEY;
const TOKEN_KEY = "oryntix_push_token";

export const pushConfigured = () => !!(firebaseConfig.apiKey && firebaseConfig.messagingSenderId && firebaseConfig.appId && VAPID);

const app = () => getApps()[0] || initializeApp(firebaseConfig);

// The service worker cannot read process.env → the web config travels in its URL.
const swRegistration = () => navigator.serviceWorker.register(`/firebase-messaging-sw.js?config=${encodeURIComponent(btoa(JSON.stringify(firebaseConfig)))}`);

export async function pushSupported() {
  return pushConfigured() && "serviceWorker" in navigator && "Notification" in window && (await isSupported());
}

export async function enablePush() {
  if (!(await pushSupported())) throw new Error("Browser ini tidak mendukung notifikasi push");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Izin notifikasi ditolak");
  const reg = await swRegistration();
  const token = await getToken(getMessaging(app()), { vapidKey: VAPID, serviceWorkerRegistration: reg });
  if (!token) throw new Error("Token push tidak diperoleh");
  await api.post("/push/tokens", { token, platform: "web", ua: navigator.userAgent.slice(0, 200) });
  localStorage.setItem(TOKEN_KEY, token);
  return token;
}

export async function disablePush() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) { await api.delete("/push/tokens", { data: { token } }).catch(() => {}); localStorage.removeItem(TOKEN_KEY); }
  try { await deleteToken(getMessaging(app())); } catch (e) {}
}

export const pushEnabledHere = () => !!localStorage.getItem(TOKEN_KEY) && typeof Notification !== "undefined" && Notification.permission === "granted";

// Foreground messages (tab open): surface as an in-app event instead of a system notification.
export async function listenForegroundPush(cb) {
  if (!pushEnabledHere() || !(await pushSupported())) return () => {};
  return onMessage(getMessaging(app()), (payload) => cb(payload?.data || {}));
}
