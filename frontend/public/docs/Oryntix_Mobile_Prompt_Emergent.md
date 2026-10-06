# PROMPT EMERGENT — Aplikasi Mobile Oryntix (Android & iOS)

## 1. Konteks & Sasaran
Bangun aplikasi mobile **Oryntix** untuk Android & iOS dari nol di project ini. Oryntix adalah platform asisten AI pribadi: pengguna membuat asisten (persona) kustom, chat teks dengan 1 asisten atau grup (beberapa asisten + teman manusia), memberi tugas ke asisten di Ruang Kerja (hasil berupa dokumen berversi), pengingat & kalender, teman, galeri media, integrasi Google Drive/GitHub/GitLab, kredit, notifikasi push, dan panggilan suara Realtime.

Backend produksi SUDAH ADA dan TIDAK boleh dibangun ulang: https://oryntix.com (FastAPI + MongoDB, semua endpoint berawalan /api, dokumentasi Swagger di https://oryntix.com/docs). Project ini HANYA membangun klien mobile yang memakai API tersebut. Jangan membuat backend baru, database baru, atau mock data permanen — semua data dari API asli. Akun uji: demo@aivora.ai / demo123456 (teman uji: budi@aivora.ai / budi123456).

## 2. Aturan Wajib
1. Stack WAJIB: Expo (SDK terbaru) + React Native + TypeScript + Expo Router; EAS development build (bukan Expo Go) karena akan memakai modul native (Firebase Messaging, WebRTC). State: TanStack Query (+ persist MMKV) dan Zustand. Ikon: lucide-react-native. Markdown: react-native-markdown-display.
2. Bahasa UI: Indonesia (nada santai, 'kamu'), siapkan i18n (id default, en). Jangan pakai emoji sebagai ikon.
3. Desain: brand Oryntix — warna utama #2F6BFF, navy gelap #0B132B, latar terang #F5F7FB, kartu putih radius 24, font bersih (Inter/Plus Jakarta Sans), tombol pil. Mode gelap opsional di tahap akhir. Hindari layout generik; gunakan spacing lega, header besar, kartu dengan bayangan lembut.
4. Semua request memakai header Authorization: Bearer <jwt>; JWT disimpan di expo-secure-store; respons 401 → bersihkan sesi dan kembali ke login. Base URL dari env EXPO_PUBLIC_API_URL (default https://oryntix.com).
5. Ikuti kontrak API persis seperti di Swagger dan Bagian 'Kontrak API' di bawah. Bila ada endpoint yang tidak ada, LAPORKAN — jangan mengarang endpoint.
6. Kerjakan BERTAHAP sesuai Tahap 0 → 6. Setiap tahap: implementasi → uji (unit + E2E Maestro + uji manual di dev build) → laporan ringkas → tunggu persetujuan sebelum tahap berikutnya.
7. Setiap elemen interaktif & informasi penting wajib punya testID (kebab-case, mis. login-submit-btn, chat-send-btn, task-restore-btn).
8. Tulis kode rapi: komponen kecil (< 150 baris), hooks per fitur, tanpa komentar panjang, tanpa over-engineering. Simpan catatan arsitektur & progres di /app/memory/PRD.md.
9. Hal yang TIDAK dibangun di mobile: bagikan layar; back-office Oryntix Platform (admin); Google Picker (cukup daftar berkas Drive buatan Oryntix).
10. Kredensial yang perlu diminta ke pemilik SEBELUM tahap terkait: Google Client ID Android & iOS (Tahap 1), file Firebase google-services.json & GoogleService-Info.plist + APNs key (Tahap 3), sertifikat VoIP/PushKit (Tahap 4), RevenueCat API key + produk IAP (Tahap 5), akun Play Console & App Store Connect (Tahap 5). Gunakan EAS Secrets / app.config.ts, jangan hardcode.

## 3. Kontrak API Backend (https://oryntix.com, Swagger: https://oryntix.com/docs)
- **Auth**: POST /api/auth/login {email,password} → {access_token,user}; POST /api/auth/register {name,email,password}; POST /api/auth/forgot-password {email}; POST /api/auth/reset-password {token,password}; POST /api/auth/google/mobile {id_token} → {access_token,user,created}; GET /api/auth/me; PUT /api/auth/settings {app_language?,conversation_language?,timezone?,mute_sounds?}; POST /api/auth/change-password {old_password,new_password}
- **Percakapan**: GET /api/conversations; GET /api/conversations/{cid}/messages?limit=50&before=<iso> → {conversation,messages}; POST /api/conversations/direct {persona_id}; POST /api/conversations {type:'group',persona_ids[],title?}; POST /api/conversations/{cid}/read; POST /api/conversations/{cid}/members {friend_ids[],persona_ids[]} (host saja); POST /api/conversations/{cid}/personas {persona_id}; POST /api/conversations/{cid}/compact (arsip)
- **Kirim pesan (SSE)**: POST /api/conversations/{cid}/send {content, attachments?, channel?:'meeting_chat', reply_to?:{id,name,content}} → stream text/event-stream: baris 'data: {json}'. Event: {persona_id,persona_name,delta} | {persona_id,final:true,content,message_id,media?,files?,tool?} | {credits_used,credits} | {attachments_context} | [DONE]. HTTP 402 = kredit habis. Lampiran perangkat: {type:'image'|'pdf'|'docx'|'text', name, data:<base64>}; Galeri: {type:'gallery', path|task_id, name, kind}; Drive: {type:'drive', drive_id, name, mime, link}.
- **Asisten (persona)**: GET /api/personas; POST /api/personas; PUT /api/personas/{pid}; DELETE /api/personas/{pid}; POST /api/personas/generate-profile {name,brief}; GET/POST/DELETE /api/personas/{pid}/knowledge (+{drive_id}, POST .../refresh); potret: GET /api/portraits/{pid}/{etag} (URL ada di field portrait); GET /api/models (daftar model & harga)
- **Ruang Kerja**: GET /api/workspace/search?q=&status=; POST /api/tasks {goal,model?}; GET /api/tasks/{tid}; GET /api/tasks/{tid}/versions/{v}; POST /api/tasks/{tid}/versions/{v}/restore; POST /api/tasks/{tid}/revise {instruction}; POST /api/tasks/{tid}/discuss {mode:'chat'|'call'|'meeting'} → {conversation_id,open_call}; GET /api/tasks/{tid}/export/{docx|pdf|xlsx|md}; POST /api/tasks/{tid}/cancel; GET /api/task-notifications; POST /api/task-notifications/ack {ids[]}
- **Pengingat**: GET/POST/PUT/DELETE /api/reminders; GET /api/reminders/calendar?month=YYYY-MM; POST /api/reminders/{rid}/respond {action:'done'|'snooze',minutes?}
- **Teman**: GET /api/friends → {friends[],incoming[],outgoing[]}; POST /api/friends/invite {email}; POST /api/friends/{rid}/accept|reject; POST /api/friends/{uid}/chat → {conversation_id}
- **Galeri & berkas**: GET /api/gallery?type=image|video|doc&q=; GET /api/files/{path}?auth=<jwt>; POST /api/conversations/{cid}/social-publish {message_id,providers[],caption}; GET /api/social/accounts
- **Integrasi**: GET /api/integrations; GET /api/integrations/google/status|connect (→ authorization_url, buka di browser sistem, callback kembali via deep link oryntix://integrations?connected=google)|files?q=|content; POST /api/integrations/google/save; DELETE /api/integrations/google; GitHub/GitLab: POST /api/integrations/github {token}, GET /api/integrations/github/repos (idem gitlab)
- **Kredit**: GET /api/wallet/balance; GET /api/wallet/history; (Tahap 5, baru) POST /api/wallet/iap/verify {platform,receipt|purchase_token,product_id}
- **Realtime (event)**: WS wss://oryntix.com/api/ws/user?token=<jwt> → {type:'message_new'|'badges'|'task_update'|'reminder_due'|'incoming_call'|'participants'|...}; WS wss://oryntix.com/api/ws/{cid}?token= (pesan & sinyal WebRTC per percakapan: {type:'rtc', kind:'join'|'offer'|'answer'|'ice', to?, from, ...})
- **Push**: POST /api/push/tokens {token, platform:'android'|'ios', ua}; DELETE /api/push/tokens/{token}; payload data: {title,body,kind,link,tag,silent:'0'|'1'}
- **Panggilan suara**: GET /api/realtime/status → {enabled,model,credits_per_min}; POST /api/realtime/calls {conversation_id} → {id,instructions,voice,tools,...}; POST /api/realtime/calls/{id}/negotiate (Content-Type: application/sdp, body SDP offer → SDP answer); data channel 'oai-events' (event OpenAI Realtime: session.update, response.create, response.done, conversation.item.input_audio_transcription.completed, ...); POST /api/realtime/calls/{id}/tick|usage|transcript|snapshot|end; GET /api/rtc/ice-servers; POST /api/conversations/{cid}/call/presence|leave; GET /api/rtc/incoming; POST /api/realtime/tools/run {call_id,name,arguments}

## 4. Tahapan Pengerjaan (berurutan, uji tiap tahap)
### Tahap 0 — Fondasi (minggu 1)
- Inisialisasi project Expo + TypeScript + Expo Router; konfigurasi EAS (profil development, preview, production); app.config.ts dengan scheme oryntix:// dan associated domain oryntix.com; bundle id com.oryntix.app.
- Design system: theme.ts (warna, radius, spasi, tipografi), komponen Button, Card, Input, Sheet, Toast, Avatar, Badge, EmptyState, Skeleton.
- src/api/client.ts (fetch + Bearer + 401), src/api/sse.ts (parser 'data:' streaming dengan AbortController), src/api/ws.ts (reconnect eksponensial, heartbeat), tipe TS dari Lampiran B.
- Layar Splash + Login kosong tampil di Android & iOS dev build. CI: lint + typecheck + jest.
- UJI: jest untuk parser SSE & client 401; build EAS development berhasil.

### Tahap 1 — Auth, Navigasi, Chat Inti (minggu 2–4)
- Auth: login, daftar, lupa/reset kata sandi, Masuk dengan Google (expo-auth-session → id_token → POST /api/auth/google/mobile). Sesi di SecureStore; auto-login; logout.
- Onboarding 5 langkah (sekali tampil) + pengaturan bahasa & zona waktu.
- Tab: Beranda (sapaan, kredit, aktivitas terbaru, tugas aktif, pengingat hari ini), Chat, Ruang Kerja, Pengingat, Profil.
- Daftar percakapan: unread badge, pencarian, swipe arsip; buka chat; buat chat baru (pilih 1 asisten → direct; beberapa → grup).
- Layar chat ala WhatsApp: bubble, potret asisten, streaming SSE (bubble sementara bertambah per delta → final), markdown (tabel/kode/tautan), kutip-balas & teruskan, mention @asisten di grup (chip saran), tandai dibaca, infinite scroll ke atas (before=).
- Media hasil asisten: gambar (lightbox pinch-zoom, simpan ke galeri perangkat), video (expo-video inline), dokumen (unduh & buka via expo-sharing). Kotak loading skeleton saat media sedang dirender (event tool/pending).
- Lampiran: kamera/galeri perangkat (expo-image-picker, kompres ≤ 1600px → base64), dokumen (expo-document-picker PDF/DOCX/TXT), Galeri Oryntix (sheet), berkas Drive Oryntix (sheet).
- Asisten: daftar, detail, buat/ubah (nama, ringkasan, kepribadian via generate-profile, suara, model dari /api/models, potret), pengetahuan (upload berkas/Drive, hapus, refresh).
- WS /api/ws/user: badge & daftar percakapan diperbarui realtime; indikator koneksi (terhubung/menyambung ulang) di header. DILARANG polling interval ke API.
- UJI: Maestro E2E login → chat direct → kirim pesan streaming → lampiran gambar → buka lightbox → logout; jest untuk reducer streaming.

### Tahap 2 — Ruang Kerja, Pengingat, Teman, Galeri, Integrasi (minggu 5–7)
- Ruang Kerja: daftar tugas (filter status, pencarian), buat tugas (goal + model), detail (langkah agen dengan status, hasil markdown, pemilih versi, Bandingkan versi (diff kata: hijau tambah/merah hapus), Kembalikan ke versi ini, revisi langsung, ekspor DOCX/PDF/XLSX via share sheet, tombol Chat/Panggilan tentang tugas (POST /discuss → buka percakapan; tampilkan kartu kutipan dokumen).
- Notifikasi tugas: badge di tab, daftar, ack.
- Pengingat & kalender: tampilan bulan + agenda, CRUD, pengingat berdering saat app aktif (layar penuh + suara kecuali mute_sounds) dan notifikasi lokal terjadwal (expo-notifications) sebagai cadangan; aksi selesai/tunda.
- Teman: daftar, undang via email, terima/tolak, DM teman, grup manusia+asisten; undang teman/asisten ke percakapan berjalan (host).
- Galeri: grid gambar/video/dokumen dengan filter & pencarian prompt; unduh ke perangkat; buka chat asal; publikasi ke YouTube (jika akun tersambung).
- Integrasi: Google Drive connect (expo-web-browser openAuthSessionAsync → deep link kembali), status, daftar berkas, putuskan; GitHub/GitLab (token PAT, daftar repo).
- Kredit: saldo, riwayat, paket; tombol top-up membuka web (Tahap 5 diganti IAP).
- Profil & Pengaturan: bahasa UI & percakapan, zona waktu, Senyapkan semua bunyi (mute_sounds), ganti kata sandi, tentang, keluar.
- UJI: Maestro untuk buat tugas → lihat hasil → bandingkan → kembalikan; buat pengingat → berdering; undang teman → DM.

### Tahap 3 — Push, Deep Link, Offline (minggu 8–9)
- Firebase Messaging (FCM Android, APNs via FCM iOS): minta izin, daftar token (platform android|ios), hapus saat logout; handler foreground (toast/in-app banner), background & terminated (tap → deep link ke link di payload). Hormati payload silent='1' (tanpa suara/getar) dan setelan pengguna.
- Deep link & universal link: /chat/{cid}, /workspace/{tid}, /reminders, /integrations; cold start & warm start.
- Offline: persist cache TanStack Query (MMKV) untuk daftar percakapan, 50 pesan terakhir per chat, tugas, pengingat; antrean pesan tertunda (kirim ulang saat online, status jam pasir → centang); banner 'Offline'.
- Siklus hidup: putus WS saat background > 30 dtk, sambung ulang saat foreground + refetch ringan.
- UJI: push diterima di 3 kondisi (foreground/background/terminated) di Android & iOS; mode pesawat → kirim pesan → online → terkirim.

### Tahap 4 — Panggilan Suara Realtime & Teman (minggu 10–13)
- Instal react-native-webrtc, react-native-incall-manager, react-native-callkeep; izin mikrofon; mode audio latar belakang (iOS UIBackgroundModes audio/voip; Android foreground service).
- Panggilan privat dengan asisten: POST /api/realtime/calls → RTCPeerConnection (audio track mic) → SDP offer ke /negotiate → answer → data channel 'oai-events': kirim session.update (instructions, voice, tools, turn_detection semantic_vad, interrupt_response:false), tangani response.created/done, transcript user/asisten (simpan via /transcript), tick per 15 dtk, usage, end. Satu respons aktif: antrekan response.create sampai response.done. Barge-in: hanya bila suara pengguna > 1,3 dtk; transkrip pendek 'hmm/iya/oke' setelah interupsi → kirim response.create 'lanjutkan dari titik berhenti'. UI: avatar besar beranimasi level suara, timer, kredit/menit, mute, speaker/earpiece, caption, panel chat meeting (channel meeting_chat), tombol Undang (host).
- Ruang grup (meeting): beberapa asisten (satu sesi Realtime per asisten, moderator mengatur giliran seperti web: delegasi via tool, status 'berbicara/menunggu'), peserta manusia via mesh P2P (sinyal WS percakapan, ICE dari /api/rtc/ice-servers, presence tiap 10 dtk), tile peserta, caption, notulen (jika endpoint tersedia).
- Panggilan teman masuk: PushKit (iOS) + FCM prioritas tinggi (Android) → CallKeep menampilkan layar dering sistem (nama & judul); terima → buka ruang; tolak → /call/leave. Dering mengikuti mute_sounds.
- Tool suara (buat gambar/video/dokumen, delegasi tugas, cari arsip) via POST /api/realtime/tools/run; hasil tampil di panel chat meeting.
- UJI MANUAL WAJIB (perangkat fisik): latensi, mute, barge-in vs backchannel, panggilan 10 menit layar terkunci, panggilan masuk di layar kunci, biaya kredit tercatat.

### Tahap 5 — IAP, Keamanan, Kepatuhan, Beta (minggu 14–15)
- RevenueCat: produk konsumsi paket kredit (mis. 1.000/5.000/20.000 kredit), layar beli, restore; verifikasi di backend POST /api/wallet/iap/verify (koordinasikan dengan pemilik backend bila endpoint belum ada).
- Keamanan: biometrik untuk membuka app (opsional di pengaturan), sembunyikan konten di app switcher, hapus akun (wajib App Store) → endpoint DELETE /api/auth/account (minta ke backend bila belum ada), kebijakan privasi & syarat (WebView).
- Aksesibilitas: label VoiceOver/TalkBack, font dinamis, kontras; mode gelap; tablet dasar.
- Observabilitas: Sentry (crash + performa), analitik funnel (login → pesan pertama → tugas pertama → panggilan pertama).
- Kepatuhan toko: App Privacy & Data Safety, alasan izin mikrofon/kamera/notifikasi, ikon, screenshot (ID/EN), deskripsi; TestFlight & Play Internal Testing.
- UJI: pembelian sandbox menambah kredit; checklist aksesibilitas; crash-free ≥ 99,7% selama beta.

### Tahap 6 — Rilis & Pasca-Rilis
- Rilis bertahap 10% → 50% → 100%; monitoring Sentry; hotfix OTA via EAS Update untuk perubahan JS; runbook rilis.
- Backlog: widget pengingat, share-sheet 'kirim ke Oryntix', Siri/Assistant shortcuts, iPad/tablet penuh, avatar video interaktif.

## 5. Tipe Data Inti (TypeScript)
```ts
type User = { id: string; email: string; name: string; avatar?: string; role: 'admin'|'user'; credits: number; plan?: string; settings: { app_language?: string; conversation_language?: string; timezone?: string; mute_sounds?: boolean } };
type Conversation = { id: string; title: string; type: 'private'|'group'|'dm'; user_id: string; persona_ids: string[]; participants: string[]; members: { id: string; name: string; portrait?: string; voice?: string }[]; humans?: { id: string; name: string; avatar?: string }[]; task_id?: string; unread?: number; last_message_at?: string; archived?: boolean };
type Message = { id: string; conversation_id: string; role: 'user'|'assistant'; content: string; persona_id?: string; persona_name?: string; portrait?: string; sender_user_id?: string; sender_name?: string; attachments?: { type: string; name: string; path?: string; link?: string; drive_id?: string; task_id?: string }[]; media?: { type: 'image'|'video'; url: string; prompt?: string }[]; files?: { name: string; path: string; mime?: string }[]; reply_to?: { id: string; name: string; content: string; link?: string }; forwarded?: boolean; tool?: string; via?: 'text'|'realtime'|'meeting_chat'; created_at: string };
type Persona = { id: string; name: string; summary?: string; portrait?: string; model?: string; voice?: string; profile: { identity?: Record<string, unknown>; personality?: { communication_style?: string; formality?: string; attitude?: string }; system_instructions?: string } };
type Task = { id: string; goal: string; status: 'queued'|'running'|'completed'|'failed'|'cancelled'; model?: string; persona_id?: string; version: number; versions?: { version: number; created_at: string; note?: string }[]; final_output?: string; revision_note?: string; steps?: { role: string; title: string; status: string; output?: string }[]; conversation_ids?: string[]; scheduled_at?: string; created_at: string };
type Reminder = { id: string; title: string; description?: string; start_at: string; remind_minutes?: number; status: 'scheduled'|'ringing'|'done'; persona_id?: string };
type Friend = { id: string; name: string; email: string; avatar?: string };
```

## 6. Kredensial dari Pemilik
- Tahap 1: Google OAuth Client ID Android & iOS (Google Cloud Console; kirim juga untuk GOOGLE_MOBILE_CLIENT_IDS backend)
- Tahap 3: google-services.json, GoogleService-Info.plist, APNs Auth Key (Firebase project oryntix-f927c, Apple Developer)
- Tahap 4: sertifikat VoIP Services (PushKit)
- Tahap 5: RevenueCat API key + produk IAP; akun Play Console & App Store Connect
- Env: EXPO_PUBLIC_API_URL (default https://oryntix.com), SENTRY_DSN via EAS Secrets

## 7. Kriteria Penerimaan Akhir
1. Login (email & Google) berhasil; sesi bertahan setelah app ditutup; 401 mengeluarkan pengguna.
2. Chat streaming: token pertama < 1 dtk di Wi-Fi; markdown & media tampil benar; lampiran terkirim.
3. Tidak ada polling interval; semua pembaruan lewat WS + refetch berbasis event.
4. Semua layar punya testID; Maestro E2E hijau di Android & iOS untuk alur utama tiap tahap.
5. Pengingat berdering tepat waktu; push diterima < 5 dtk; mute_sounds mematikan semua bunyi/getar.
6. Panggilan suara stabil 10 menit dengan layar terkunci; backchannel tidak memotong asisten; biaya kredit sama dengan web.
7. Crash-free ≥ 99,7% selama beta; startup dingin < 2 dtk; lolos review App Store & Play.

**Mulai dari Tahap 0. Sebelum menulis kode, ringkas rencana Tahap 0–1 dan ajukan pertanyaan klarifikasi yang benar-benar perlu (maksimal 5).**