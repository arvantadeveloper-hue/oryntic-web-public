# Oryntix Mobile (Android & iOS) — Brief untuk job Emergent baru (Expo / React Native)

> Tempel brief ini sebagai problem statement di job mobile. Backend produksi: **https://oryntix.com** (FastAPI, semua endpoint berawalan `/api`). Tidak ada perubahan server yang diperlukan untuk Tahap 1, kecuali token push platform (lihat §6).

## 1. Produk
Oryntix = asisten AI pribadi yang dapat dikustomisasi (persona), chat teks dengan 1 asisten atau grup (multi-agen + teman manusia), lampiran (perangkat/Galeri/Google Drive), pengetahuan asisten, Ruang Kerja (tugas yang dikerjakan asisten → dokumen), pengingat & kalender, kredit, integrasi Google Drive, notifikasi push. Bahasa UI: **Indonesia**. Brand: "Oryntix — Intelligence, Orchestrated." Warna utama `#2F6BFF`, gelap `#0B132B`, kartu putih radius 24, font bersih.

## 2. Tahap 1 (bangun dulu) — tanpa WebRTC
- Auth: email+password (`POST /api/auth/login`, `/register`, `/forgot-password`, `/reset-password`), **Masuk dengan Google** (lihat §4), `GET /api/auth/me`, JWT Bearer disimpan di SecureStore.
- Daftar percakapan & chat: `GET /api/conversations`, `GET /api/conversations/{cid}/messages?limit=50&before=`, `POST /api/conversations/{cid}/send` (**SSE stream**; body `{content, attachments?, channel?}`), `POST /api/conversations/direct {persona_id}`, `POST /api/conversations {title, persona_ids…}`, `POST /api/conversations/{cid}/read`.
- Lampiran: perangkat (base64 `{type:"image"|"pdf"|"docx"|"text", name, data}`), Galeri (`GET /api/gallery` → `{type:"gallery", path|task_id, name, kind}`), Drive (`GET /api/integrations/google/files?q=` → `{type:"drive", drive_id, name, mime, link}`; file lain via Google Picker tidak tersedia di RN → cukup daftar file buatan Oryntix).
- Asisten/persona: `GET/POST/PUT /api/personas`, `POST /api/personas/generate-profile`, pengetahuan `GET/POST/DELETE /api/personas/{pid}/knowledge` (+ `{drive_id}` dan `/refresh`).
- Ruang Kerja: `GET /api/workspace/search`, `POST /api/conversations/{cid}/tasks`, `GET /api/tasks/{tid}` (+ revisi `POST /api/tasks/{tid}/revise`), notifikasi tugas `GET /api/task-notifications`, `POST /api/task-notifications/ack`.
- Pengingat & kalender: `GET/POST/PUT/DELETE /api/reminders`, `GET /api/reminders/calendar`, `POST /api/reminders/{rid}/respond`.
- Teman: `GET /api/friends`, `POST /api/friends/invite`, `/{rid}/accept|reject`, `POST /api/friends/{uid}/chat`.
- Galeri & berkas: `GET /api/gallery`, unduh `GET /api/files/{path}?auth=<jwt>`.
- Kredit: `GET /api/auth/me` (credits), riwayat `GET /api/credits/...` (lihat Swagger `/docs`).
- Integrasi Google Drive: `GET /api/integrations`, `GET /api/integrations/google/status|connect|files|content`, `POST /api/integrations/google/save|update|link`, `DELETE /api/integrations/google`. Connect: buka `authorization_url` di browser sistem (`expo-web-browser`), callback server mengarahkan ke `/integrations?connected=google` → tangkap via deep link `oryntix://integrations`.
- Realtime dalam-app: WebSocket `wss://oryntix.com/api/ws/user?token=<jwt>` → event `{type: "reminder_due"|"incoming_call"|"task_update"|"message_new"|…}`; per percakapan `wss://oryntix.com/api/ws/{cid}?token=`.
- Push: lihat §6.
- Pengaturan: `PUT /api/auth/settings` (bahasa, zona waktu), ganti password `POST /api/auth/change-password`.

## 3. Tahap 2 (setelah Tahap 1 stabil)
- Panggilan suara Realtime (OpenAI) & panggilan teman: `react-native-webrtc` (butuh **development build / EAS**, bukan Expo Go). Alur server sama dengan web: `POST /api/realtime/calls {conversation_id}` → `POST /api/realtime/calls/{id}/negotiate` (body SDP offer, `Content-Type: application/sdp`, balasan SDP answer) → data channel `oai-events` → `/tick`, `/usage`, `/transcript`, `/end`. ICE/TURN: `GET /api/rtc/ice-servers`. Panel chat dalam panggilan = percakapan yang sama (`channel:"meeting_chat"`).
- Bagikan layar: lewati di mobile.

## 4. Login Google di mobile
Web memakai authorization-code + cookie CSRF (`/api/auth/google/start|exchange`) yang **tidak cocok untuk aplikasi native**. **Sudah tersedia di backend**: `POST /api/auth/google/mobile {id_token}` → verifikasi ID token Google (audience harus salah satu dari `GOOGLE_CLIENT_ID` atau daftar `GOOGLE_MOBILE_CLIENT_IDS` (env, dipisah koma) → upsert user → `{access_token, user, created}`. Di mobile pakai `expo-auth-session/providers/google` dengan Client ID Android & iOS (buat di Google Cloud Console, project yang sama: `488445398588-…`).

## 5. Format SSE `/send`
`data: {...}` per baris; event penting: `{persona_id, persona_name, delta}` (potongan teks), `{persona_id, final:true, content, message_id, media?, files?, tool?}`, `{credits_used, credits}`, `{attachments_context}` (hanya channel meeting_chat), `[DONE]`. Gunakan `react-native-sse` atau fetch streaming (`expo/fetch`).

## 6. Push notification
Backend sudah punya `POST /api/push/tokens {token, platform:"web", ua}` + `send_push()` via firebase-admin (`MulticastMessage`). Untuk mobile: kirim `platform:"android"|"ios"` dengan FCM token dari `@react-native-firebase/messaging` (atau Expo Notifications + FCM/APNs). **Sudah tersedia**: bila ada token dengan platform `android`/`ios`, backend menambahkan `notification` + konfigurasi `android`/`apns` (sound default, tag/thread) pada pesan FCM. Project Firebase: **oryntix-f927c** (tambahkan app Android/iOS, unduh `google-services.json` / `GoogleService-Info.plist`, dan upload kunci APNs).

## 7. Deep links
Skema `oryntix://` + universal links `https://oryntix.com/*`: `/chat/{cid}`, `/workspace/{tid}`, `/reminders`, `/integrations`.

## 8. Data model inti (untuk tipe TS)
- User `{id, email, name, avatar, role: "admin"|"user", credits, plan, trial_ends_at, settings{app_language, conversation_language, timezone}, google_email?}`
- Conversation `{id, title, type: "private"|"group"|"friend", persona_ids[], participants[], task_id?, unread?, last_message_at}`
- Message `{id, conversation_id, role: "user"|"assistant", content (markdown), persona_id?, persona_name?, portrait?, sender_user_id?, sender_name?, attachments[{type,name,path?,link?,drive_id?}], media[], files[], tool?, via: "text"|"realtime"|"meeting_chat", created_at}`
- Persona `{id, name, summary, portrait, profile{identity, personality, system_instructions}, voice}`
- Task `{id, goal, status: "queued"|"running"|"completed"|"failed", persona_id, result_path?, version, scheduled_at}`
- Reminder `{id, title, description, start_at, remind_minutes, status: "scheduled"|"ringing"|"done"}`

## 9. Kredensial yang perlu disiapkan pemilik
Google Client ID Android & iOS; Firebase app Android/iOS (`google-services.json`, `GoogleService-Info.plist`, kunci APNs); akun Google Play Console & Apple Developer untuk rilis (EAS Build/Submit).

## 10. Catatan kualitas
- Semua request pakai header `Authorization: Bearer <jwt>`; 401 → logout. 
- Bahasa UI Indonesia, nada santai; hindari emoji sebagai ikon (pakai lucide-react-native).
- Uji dengan akun demo: `demo@aivora.ai / demo123456`.
