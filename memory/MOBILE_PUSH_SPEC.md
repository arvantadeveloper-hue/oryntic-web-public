# Oryntix — Kontrak Push Notification (FCM + APNs VoIP)

Berlaku untuk backend `oryntix.com` per 2026-10-09. Semua endpoint butuh `Authorization: Bearer <JWT>`.

## 1. Endpoint

| Method | Path | Keterangan |
|---|---|---|
| `POST` | `/api/push/tokens` | `{token, platform: "web"\|"android"\|"ios", ua?}` — token FCM. `platform != "web"` mengaktifkan blok `android`+`apns`. |
| `DELETE` | `/api/push/tokens` | `{token}` |
| `PUT` | `/api/push/prefs` | `{reminders, calls, messages, tasks}` (boolean) |
| `GET` | `/api/push/status` | `{configured, devices, prefs, voip_configured, voip_devices, voip_env}` |
| `POST` | `/api/push/test` | Kirim push uji ke semua device user (abaikan status online) |
| `POST` | `/api/push/voip-tokens` | **Baru** `{token: <hex PushKit>, environment: "sandbox"\|"production", bundle_id?}` |
| `DELETE` | `/api/push/voip-tokens` | **Baru** `{token}` |
| `POST` | `/api/push/voip-test` | **Baru** Kirim VoIP push ke iPhone user sendiri (uji PushKit + CallKit) |

Catatan: push alert **tidak dikirim** jika user sedang online di WebSocket per-user (`/api/ws/user`), kecuali `force` (endpoint test). VoIP push **selalu** dikirim saat ada panggilan masuk.

## 2. Payload FCM (semua notifikasi)

`data` (semua nilai string):

| key | isi |
|---|---|
| `title`, `body` | teks notifikasi |
| `kind` | `calls` \| `reminders` \| `messages` \| `tasks` \| `friends` \| `system` |
| `link` | rute dalam app, mis. `/chat/<conversation_id>` |
| `tag` | kunci dedupe/collapse, mis. `call-<cid>`, `reminder-<id>` |
| `silent` | `"1"` bila user mematikan suara di setelan |
| `call_id`, `conversation_id`, `caller`, `handle`, `persona_id` | khusus `kind=calls` |

Blok platform:

```json
"android": {
  "priority": "high",
  "ttl": "45s",                     // panggilan; lainnya 6 jam
  "collapse_key": "call-<cid>",
  "direct_boot_ok": true,
  "notification": {
    "channel_id": "oryntix_calls",  // lihat tabel channel
    "notification_priority": "PRIORITY_MAX",   // panggilan; lainnya PRIORITY_HIGH
    "visibility": "PUBLIC",
    "tag": "call-<cid>",
    "icon": "ic_notification",
    "color": "#2F6BFF",
    "default_sound": true,
    "default_vibrate_timings": true
  }
},
"apns": {
  "headers": {
    "apns-priority": "10",
    "apns-push-type": "alert",
    "apns-topic": "<APNS_BUNDLE_ID>",      // dikirim bila env APNS_BUNDLE_ID diisi
    "apns-collapse-id": "call-<cid>",
    "apns-expiration": "<epoch+45>"        // hanya untuk panggilan
  },
  "payload": { "aps": {
    "alert": {"title": "...", "body": "..."},
    "sound": "default",                    // null bila silent
    "content-available": 1,
    "mutable-content": 1,
    "category": "ORYNTIX_CALL",
    "thread-id": "call-<cid>"
  }}
}
```

Android channel yang harus dibuat app (id harus sama persis):

| `kind` | channel_id | importance |
|---|---|---|
| calls | `oryntix_calls` | HIGH + full-screen intent + ringtone |
| reminders | `oryntix_reminders` | HIGH |
| messages | `oryntix_messages` | DEFAULT |
| tasks | `oryntix_tasks` | DEFAULT |
| friends | `oryntix_social` | DEFAULT |
| lainnya | `oryntix_default` | DEFAULT |

Kategori iOS (untuk `UNNotificationCategory` / action): `ORYNTIX_CALL`, `ORYNTIX_REMINDER`, `ORYNTIX_MESSAGE`, `ORYNTIX_TASK`, `ORYNTIX_SOCIAL`, `ORYNTIX`.

## 3. VoIP push (PushKit) — iOS

Dikirim langsung ke APNs (HTTP/2, JWT ES256), bukan via FCM:
`apns-push-type: voip`, `apns-priority: 10`, `apns-topic: <bundle>.voip`, `apns-expiration: now+45s`.

Body (≤5 KB):

```json
{
  "aps": {"content-available": 1},
  "call_id": "<call_session_id>",
  "conversation_id": "<cid>",
  "caller": "Andi",
  "handle": "Andi",
  "persona_id": "<opsional>",
  "tag": "call-<cid>",
  "link": "/chat/<cid>",
  "kind": "calls"
}
```

Sisi app: laporkan ke CallKit segera di `pushRegistry(_:didReceiveIncomingPushWith:)`, lalu panggil completion handler. Padanan Android: FCM data `kind=calls` priority high → `ConnectionService`/full-screen intent.

Token mati otomatis dibersihkan: APNs `410` atau reason `BadDeviceToken` / `Unregistered` / `DeviceTokenNotForTopic` / `TopicDisallowed` → dokumen `voip_tokens` dihapus. `ExpiredProviderToken`/`InvalidProviderToken` → JWT dibuat ulang lalu retry 1×.

## 4. Pemicu panggilan di backend

`POST /api/conversations/{cid}/call/presence` (heartbeat pertama = panggilan dimulai) → `send_call_push()`:
1. `apns_voip.send_voip()` ke semua device iOS penerima,
2. `send_push()` FCM high-priority ke Android/web.

## 5. Env yang dibutuhkan (produksi)

| key | isi |
|---|---|
| `FCM_SERVICE_ACCOUNT_B64` | sudah terpasang |
| `APNS_P8` | isi file AuthKey_XXXX.p8 (PEM, `\n` boleh di-escape) |
| `APNS_KEY_ID` | 10 karakter |
| `APNS_TEAM_ID` | 10 karakter |
| `APNS_BUNDLE_ID` | mis. `com.oryntix.app` → topic VoIP `com.oryntix.app.voip` |
| `APNS_ENV` | `sandbox` (debug/TestFlight) atau `production` |

Tanpa `APNS_*`, VoIP push no-op: `/api/push/voip-test` → `{"sent":0,"skipped":"APNS_* belum dikonfigurasi"}` dan `status.voip_configured=false`.

## 6. Status uji (2026-10-09)

- Bentuk payload FCM diverifikasi lewat encoder firebase-admin (hasil JSON sama dengan §2).
- Jalur APNs diverifikasi end-to-end dengan kunci ES256 dummy: koneksi HTTP/2 ke `api.sandbox.push.apple.com`, JWT tertandatangani, Apple membalas `403 InvalidProviderToken` (= jalur benar, kunci saja yang palsu). Perlu uji ulang dengan kunci asli + iPhone fisik.
