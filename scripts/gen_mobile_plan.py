"""Generates 'Oryntix Mobile Development Plan' (Android & iOS) — siap tempel ke project/job baru."""
import sys
sys.path.insert(0, "/app/scripts")
from gen_docs import new_doc, h, para, bullets, table, toc_note, OUT  # noqa: E402

BACKEND = "https://oryntix.com"

PHASES = [
    # (kode, nama, durasi, tujuan, fitur, endpoint, DoD)
    ("Tahap 0", "Persiapan & Fondasi Proyek", "1 minggu",
     "Repositori, tooling, desain sistem, dan kredensial siap sehingga tim bisa langsung membangun fitur tanpa hambatan.",
     ["Inisialisasi Expo (SDK terbaru, TypeScript, Expo Router) + EAS (development build, preview, production).",
      "Design system mobile: token warna (#2F6BFF, #0B132B), tipografi, komponen dasar (Button, Card radius 24, Input, Sheet, Toast), ikon lucide-react-native.",
      "Lapisan API: klien HTTP (axios/fetch) dengan interceptor Bearer JWT, penanganan 401 → logout, retry ringan; SecureStore untuk token.",
      "Tipe TypeScript dari model data inti (User, Conversation, Message, Persona, Task, Reminder).",
      "State: TanStack Query (cache server) + Zustand (sesi, UI). Lint/format, Husky, CI (GitHub Actions: lint + typecheck + EAS build preview).",
      "Kredensial: Google Client ID Android & iOS, Firebase app Android/iOS (google-services.json, GoogleService-Info.plist), APNs key, akun Play Console & App Store Connect."],
     ["GET /api/auth/me (smoke test autentikasi)", "GET /api/models (daftar model)"],
     ["Aplikasi dev-build jalan di Android & iOS dengan layar splash + login kosong.", "CI hijau; EAS preview build terbit ke internal tester.", "Semua kredensial §9 tersedia di EAS Secrets."]),
    ("Tahap 1", "Autentikasi, Navigasi & Chat Inti", "3 minggu",
     "Pengguna bisa masuk, melihat percakapan, dan mengobrol teks dengan asisten (termasuk streaming jawaban) — nilai inti produk tersedia di ponsel.",
     ["Login email/kata sandi, daftar, lupa/reset kata sandi, Masuk dengan Google (ID token → POST /api/auth/google/mobile).",
      "Onboarding singkat (tur 5 langkah versi mobile) & pengaturan bahasa/zona waktu.",
      "Tab utama: Beranda, Chat, Ruang Kerja, Pengingat, Profil. Deep link oryntix:// + universal link https://oryntix.com/*.",
      "Daftar percakapan (unread badge, pencarian, arsip), buka chat privat/grup/DM; buat chat baru dengan 1 asisten (direct) atau pilih beberapa asisten (grup).",
      "Chat teks dengan streaming SSE (delta → final), markdown (tabel, kode, tautan), kutip-balas & teruskan, mention @asisten di grup, tandai dibaca.",
      "Render media hasil asisten: gambar (lightbox), video (player inline), dokumen (unduh/buka).",
      "Lampiran: kamera/galeri perangkat (kompres → base64), berkas (PDF/DOCX/TXT), Galeri Oryntix, berkas Google Drive buatan Oryntix.",
      "WebSocket /api/ws/user untuk badge, pesan baru, status tugas; reconnect eksponensial + indikator koneksi.",
      "Daftar & detail asisten (persona): buat/ubah nama, kepribadian, suara, model, potret; pengetahuan (upload/Drive)."],
     ["POST /api/auth/login|register|forgot-password|reset-password, POST /api/auth/google/mobile, GET /api/auth/me, PUT /api/auth/settings",
      "GET /api/conversations, GET /api/conversations/{cid}/messages, POST /api/conversations/{cid}/send (SSE), POST /api/conversations/direct, POST /api/conversations, POST /api/conversations/{cid}/read",
      "GET/POST/PUT /api/personas, POST /api/personas/generate-profile, /api/personas/{pid}/knowledge, GET /api/portraits/{pid}/{etag}",
      "GET /api/gallery, GET /api/files/{path}?auth=, GET /api/integrations/google/files", "WS /api/ws/user?token="],
     ["Pengguna demo bisa login, chat 1:1 & grup dengan streaming < 1 dtk ke token pertama.", "Lampiran gambar/PDF berhasil dikirim dan dibaca asisten.", "Crash-free sessions ≥ 99,5% di internal test (Sentry).", "Uji E2E (Maestro) untuk login, kirim pesan, buka media."]),
    ("Tahap 2", "Ruang Kerja, Pengingat, Teman, Galeri & Integrasi", "3 minggu",
     "Semua fitur produktivitas web tersedia di mobile sehingga pengguna tidak perlu berpindah perangkat.",
     ["Ruang Kerja: daftar tugas (filter status, pencarian), detail tugas (langkah agen, hasil markdown, versi, bandingkan versi, kembalikan versi), revisi via chat atau langsung, ekspor DOCX/PDF/XLSX, bagikan tautan, 'Chat tentang tugas ini' (kutipan dokumen).",
      "Penugasan dari chat: lihat kartu tugas aktif, notifikasi tugas selesai (ack).",
      "Pengingat & kalender: CRUD, tampilan bulan/agenda, pengingat berdering (notifikasi lokal + layar penuh saat app aktif), respon tunda/selesai.",
      "Teman: daftar, undang via email, terima/tolak, DM teman, grup manusia + asisten; undang teman/asisten ke percakapan (POST /members).",
      "Galeri: grid gambar/video/dokumen, pencarian prompt, unduh/simpan ke perangkat, buka chat asal, publikasi ke sosmed (YouTube).",
      "Integrasi: Google Drive (connect via browser sistem + deep link kembali, daftar/simpan berkas), GitHub/GitLab (PAT, daftar repo), status koneksi.",
      "Kredit: saldo, riwayat pemakaian, paket; top-up mengarah ke web (atau IAP di Tahap 5).",
      "Pengaturan: bahasa UI & percakapan, zona waktu, senyapkan bunyi, ganti kata sandi, hapus akun."],
     ["GET /api/workspace/search, GET /api/tasks/{tid}, /versions/{v}, /versions/{v}/restore, /revise, /discuss, /export/{fmt}, GET /api/task-notifications, POST /api/task-notifications/ack",
      "GET/POST/PUT/DELETE /api/reminders, GET /api/reminders/calendar, POST /api/reminders/{rid}/respond",
      "GET /api/friends, POST /api/friends/invite, /{rid}/accept|reject, POST /api/friends/{uid}/chat, POST /api/conversations/{cid}/members",
      "GET /api/gallery, POST /api/conversations/{cid}/social-publish, GET /api/social/accounts",
      "GET /api/integrations, /google/status|connect|files|content, POST /google/save, DELETE /google, /github/*, /gitlab/*",
      "GET /api/wallet/*, PUT /api/auth/settings (mute_sounds, conversation_language, timezone)"],
     ["Paritas fitur produktivitas dengan web ≥ 90% (checklist FSD).", "Pengingat berdering tepat waktu saat app di latar depan & lewat notifikasi saat di latar belakang.", "Google Drive connect-disconnect berjalan di Android & iOS."]),
    ("Tahap 3", "Notifikasi Push, Latar Belakang & Offline", "2 minggu",
     "Aplikasi terasa 'hidup': pengguna mendapat notifikasi pesan, tugas, pengingat, dan panggilan masuk walau app tertutup; data terakhir tetap bisa dibaca tanpa jaringan.",
     ["FCM (Android) & APNs via FCM (iOS) dengan @react-native-firebase/messaging; daftar token POST /api/push/tokens {platform: android|ios}.",
      "Kategori notifikasi: pesan, tugas, pengingat, panggilan, sistem — hormati setelan 'senyapkan bunyi' (payload silent) & preferensi per kategori.",
      "Tap notifikasi → deep link ke chat/tugas/pengingat; badge ikon aplikasi.",
      "Cache offline: percakapan & 50 pesan terakhir, tugas & pengingat (TanStack Query persist ke MMKV); antrean kirim pesan saat offline → kirim ulang otomatis.",
      "Background fetch ringan untuk sinkron badge; penanganan token kedaluwarsa & multi-perangkat (hapus token saat logout)."],
     ["POST /api/push/tokens, DELETE /api/push/tokens/{token}", "WS /api/ws/user (reconnect saat kembali ke foreground)"],
     ["Push diterima < 5 dtk di Android & iOS (foreground, background, terminated).", "Membuka app tanpa jaringan tetap menampilkan chat terakhir; pesan tertunda terkirim saat online.", "Tidak ada bunyi/getar saat 'senyapkan bunyi' aktif."]),
    ("Tahap 4", "Panggilan Suara Realtime & Panggilan Teman (WebRTC)", "4 minggu",
     "Pengalaman suara Oryntix (asisten Realtime, ruang grup dengan moderator, panggilan antar teman) hadir di mobile dengan kualitas setara web.",
     ["react-native-webrtc (development build) + InCallManager (speaker/earpiece, Bluetooth, mode audio) + izin mikrofon.",
      "Panggilan privat dengan asisten: POST /api/realtime/calls → negotiate SDP → data channel oai-events; VAD server; mute; timer & biaya/menit; caption transkrip; antrean response.create (satu respons aktif) dan toleransi backchannel (1,3 dtk) seperti web.",
      "Ruang grup/meeting: beberapa asisten + moderator, delegasi, caption, panel chat meeting (channel meeting_chat), notulen; peserta manusia via mesh P2P (sinyal lewat WS percakapan, ICE dari GET /api/rtc/ice-servers).",
      "Panggilan masuk dari teman: CallKeep/CallKit (iOS) & ConnectionService (Android) dengan push prioritas tinggi/VoIP (PushKit) → layar dering sistem; terima/tolak; dering mengikuti 'senyapkan bunyi'.",
      "Undang teman/asisten di tengah panggilan (POST /members) dan perpindahan otomatis privat → ruang grup.",
      "Tool suara: buat gambar/video/dokumen, delegasi tugas, cari arsip — hasil tampil di panel chat meeting.",
      "Tidak dibangun di mobile: bagikan layar (di-skip); 'Tunjukkan ke asisten' diganti kirim foto kamera ke snapshot endpoint (opsional)."],
     ["POST /api/realtime/calls, POST /api/realtime/calls/{id}/negotiate (application/sdp), /tick, /usage, /transcript, /snapshot, /end, GET /api/realtime/status|vision-rate",
      "GET /api/rtc/ice-servers, POST /api/conversations/{cid}/call/presence|leave, GET /api/rtc/incoming", "WS /api/ws/{cid}?token= (sinyal WebRTC)"],
     ["Latensi suara ke-suara < 1,2 dtk di 4G.", "Panggilan 10 menit stabil tanpa putus saat layar terkunci (audio background mode iOS, foreground service Android).", "Panggilan masuk berdering di layar kunci kedua platform; biaya kredit tercatat sama dengan web."]),
    ("Tahap 5", "Monetisasi, Keamanan & Kesiapan Rilis", "2 minggu",
     "Aplikasi memenuhi kebijakan toko, aman, dan siap menerima pembayaran kredit dari dalam aplikasi.",
     ["Pembelian kredit: RevenueCat/StoreKit 2 & Google Play Billing (produk konsumsi paket kredit) → verifikasi server (endpoint baru POST /api/wallet/iap/verify) → tambah kredit.",
      "Keamanan: SecureStore/Keychain, pinning sertifikat (opsional), biometrik untuk membuka app, logout semua perangkat, kebijakan privasi & hapus akun (wajib App Store).",
      "Aksesibilitas (font dinamis, kontras, label VoiceOver/TalkBack), dukungan tablet dasar, mode gelap.",
      "Analitik & observabilitas: Sentry (crash), PostHog/Firebase Analytics (funnel), log performa startup < 2 dtk.",
      "Kepatuhan toko: App Privacy labels, Data Safety form, izin mikrofon/kamera dengan alasan jelas, screenshot & deskripsi (ID/EN), usia 13+.",
      "Beta: TestFlight & Play Internal/Closed Testing dengan 20–50 pengguna, perbaikan bug prioritas."],
     ["POST /api/wallet/iap/verify (baru), GET /api/wallet/balance|history, POST /api/auth/change-password, DELETE /api/auth/account (baru bila belum ada)"],
     ["Pembelian uji (sandbox) menambah kredit di kedua platform.", "Review App Store & Play lolos tanpa penolakan kebijakan.", "Skor crash-free ≥ 99,7%, startup dingin < 2 dtk pada perangkat kelas menengah."]),
    ("Tahap 6", "Peluncuran & Pasca-Rilis", "berkelanjutan (sprint 2 minggu)",
     "Rilis publik, pemantauan, dan iterasi berdasarkan data pemakaian.",
     ["Rilis bertahap (staged rollout 10% → 50% → 100%), monitoring crash & latensi, hotfix via EAS Update (OTA untuk JS).",
      "Backlog pasca-rilis: widget pengingat, Siri/Assistant shortcuts, share-sheet 'kirim ke Oryntix', avatar video interaktif (P2 web), Apple Watch/Wear OS ringkas, iPad/tablet layout penuh.",
      "Review bulanan metrik: DAU/MAU, retensi D7/D30, menit panggilan, konversi top-up, NPS in-app."],
     ["—"],
     ["Aplikasi tersedia publik di Play Store & App Store.", "Proses rilis terdokumentasi (runbook) dan OTA update teruji."]),
]

RISKS = [
    ("WebRTC di Expo butuh development build (bukan Expo Go)", "Tinggi", "Gunakan EAS dev client sejak Tahap 0; simulasikan panggilan di Tahap 1–3 dengan mock agar tim UI tidak terblokir."),
    ("Panggilan masuk saat app tertutup (iOS)", "Tinggi", "PushKit + CallKit wajib; siapkan sertifikat VoIP; uji di perangkat fisik sejak awal Tahap 4."),
    ("Kebijakan App Store untuk pembelian kredit", "Sedang", "Gunakan IAP untuk kredit (barang digital); top-up web tetap ada tetapi tidak dipromosikan dalam app iOS."),
    ("Konsumsi baterai/kuota saat WebSocket & panggilan", "Sedang", "Putuskan WS saat background (andalkan push), batasi bitrate audio Opus 24–32 kbps, foreground service hanya saat panggilan."),
    ("Perbedaan perilaku Android vs iOS (izin, audio routing)", "Sedang", "Matriks perangkat uji (3 Android, 2 iPhone) dan checklist izin per layar."),
    ("Perubahan kontrak API backend", "Rendah", "Backend sudah stabil & terdokumentasi (Swagger /docs); versi API di header, tes kontrak otomatis di CI."),
]

TEAM = [
    ("Tech Lead Mobile (1)", "Arsitektur, review, EAS, integrasi WebRTC."),
    ("Mobile Engineer RN (2)", "Fitur per tahap, komponen UI, pengujian."),
    ("Backend Engineer (0,5)", "Endpoint baru (IAP verify, hapus akun, push mobile), dukungan debugging."),
    ("UI/UX Designer (0,5)", "Adaptasi design system web ke mobile, ikon, screenshot toko."),
    ("QA (1)", "Rencana uji, Maestro E2E, uji perangkat fisik, regresi per rilis."),
]

STRUCTURE = [
    ("app/", "Expo Router: (auth)/login, register, forgot; (tabs)/home, chat, workspace, reminders, profile; chat/[cid]; workspace/[tid]; call/[cid]"),
    ("src/api/", "client.ts (JWT, 401), sse.ts (stream /send), ws.ts (user & conversation sockets), endpoints/* per modul"),
    ("src/store/", "session.ts (Zustand), query/ (TanStack Query + persist MMKV)"),
    ("src/features/", "chat/, personas/, workspace/, reminders/, friends/, gallery/, integrations/, calls/ (Tahap 4), billing/ (Tahap 5)"),
    ("src/components/ui/", "Button, Card, Input, Sheet, Toast, Avatar, Markdown (react-native-markdown-display), MediaViewer"),
    ("src/lib/", "theme.ts, i18n (id default), permissions.ts, notifications.ts, deeplinks.ts, audio.ts"),
    ("eas.json / app.config.ts", "Profil build dev/preview/production, skema oryntix://, associated domains oryntix.com, izin & plist strings"),
]

QA_MATRIX = [
    ("Unit", "Jest + RN Testing Library", "util, store, parser SSE, formatter kredit"),
    ("Integrasi API", "MSW/mock server + tes kontrak", "semua endpoint per tahap terhadap Swagger"),
    ("E2E", "Maestro (Android & iOS)", "login, chat streaming, lampiran, tugas, pengingat, panggilan (Tahap 4)"),
    ("Perangkat", "Pixel 6/7, Samsung A-series, iPhone 12/14/15", "izin, audio routing, notifikasi, layar kunci"),
    ("Kinerja", "Flashlight / Xcode Instruments", "startup < 2 dtk, FPS daftar chat ≥ 55, memori panggilan < 250 MB"),
    ("Keamanan", "MobSF, review manual", "penyimpanan token, log sensitif, pinning (opsional)"),
]

CREDS = [
    ("Google Cloud Console", "OAuth Client ID Android (SHA-1 debug & release) dan iOS (bundle id) → isi GOOGLE_MOBILE_CLIENT_IDS di backend"),
    ("Firebase (project oryntix-f927c)", "App Android & iOS, google-services.json, GoogleService-Info.plist, APNs Auth Key (.p8), sertifikat VoIP (Tahap 4)"),
    ("Apple Developer", "Team ID, bundle id com.oryntix.app, App Store Connect, TestFlight, Associated Domains, Push & VoIP capability"),
    ("Google Play Console", "Paket com.oryntix.app, App signing, Internal testing track, Data Safety"),
    ("Expo / EAS", "Akun organisasi, EAS Secrets (API_URL, Sentry DSN, RevenueCat key)"),
    ("Backend", "Tidak ada perubahan untuk Tahap 1–3 (semua endpoint tersedia); Tahap 5 butuh endpoint IAP verify"),
]


def build():
    d = new_doc("Rencana Pengembangan Aplikasi Mobile", "Android & iOS — Tahap 0 sampai Peluncuran (Expo / React Native)")
    toc_note(d)

    h(d, "1. Ringkasan Eksekutif")
    para(d, "Dokumen ini adalah rencana pengembangan aplikasi mobile Oryntix untuk Android dan iOS, disusun agar dapat langsung dipakai sebagai acuan pada project/job baru. "
            "Backend produksi Oryntix (FastAPI + MongoDB, semua endpoint berawalan /api) sudah lengkap dan dipakai oleh web; aplikasi mobile dibangun sebagai klien baru tanpa perubahan server pada Tahap 1–3.")
    bullets(d, [("Pendekatan", "Satu basis kode React Native (Expo + EAS) untuk Android & iOS; development build sejak awal agar WebRTC & push native dapat dipakai."),
                ("Urutan nilai", "Chat & asisten dulu (Tahap 1), produktivitas (Tahap 2), notifikasi/offline (Tahap 3), suara/WebRTC (Tahap 4), monetisasi & rilis (Tahap 5), pasca-rilis (Tahap 6)."),
                ("Total estimasi", "±15 minggu sampai rilis publik dengan tim 4–5 orang; setiap tahap punya kriteria selesai (Definition of Done) yang dapat diuji."),
                ("Backend", f"{BACKEND} — dokumentasi Swagger di {BACKEND}/docs; akun uji demo@aivora.ai / demo123456.")])

    h(d, "2. Tujuan & Sasaran Produk")
    bullets(d, ["Paritas fitur inti dengan web: chat teks/grup, asisten kustom, Ruang Kerja, pengingat, teman, galeri, integrasi Google Drive.",
                "Pengalaman mobile-native: notifikasi push, deep link, offline-first ringan, panggilan masuk di layar kunci, dering & getar yang menghormati setelan senyap.",
                "Panggilan suara Realtime dan panggilan teman dengan kualitas setara web (Tahap 4).",
                "Monetisasi kredit via pembelian dalam aplikasi sesuai kebijakan toko (Tahap 5).",
                "Bahasa UI Indonesia (default) dengan i18n siap untuk bahasa lain; nada santai, tanpa emoji sebagai ikon."])

    h(d, "3. Keputusan Teknologi")
    table(d, ["Area", "Pilihan", "Alasan"], [
        ("Framework", "Expo SDK terbaru + React Native + TypeScript + Expo Router", "Satu kode untuk 2 platform, OTA update, tim web React cepat beradaptasi."),
        ("Build & rilis", "EAS Build / Submit / Update", "Development build untuk modul native (WebRTC, Firebase), pipeline rilis otomatis."),
        ("State & data", "TanStack Query (+ persist MMKV) & Zustand", "Cache server, offline ringan, state sesi sederhana."),
        ("Streaming", "fetch streaming / react-native-sse untuk SSE /send; WebSocket bawaan RN", "Mengikuti kontrak backend yang ada."),
        ("Suara", "react-native-webrtc, react-native-incall-manager, CallKeep (CallKit/ConnectionService), PushKit", "Panggilan Realtime & teman, dering layar kunci."),
        ("Push", "@react-native-firebase/messaging (FCM, APNs via FCM)", "Backend sudah mengirim MulticastMessage dengan konfigurasi android/apns."),
        ("Auth Google", "expo-auth-session (ID token) → POST /api/auth/google/mobile", "Endpoint native sudah tersedia di backend."),
        ("Pembayaran", "RevenueCat (StoreKit 2 + Play Billing)", "Kepatuhan toko untuk kredit digital, verifikasi server."),
        ("Observabilitas", "Sentry + PostHog/Firebase Analytics", "Crash & funnel sejak beta."),
        ("Pengujian", "Jest, RN Testing Library, Maestro", "Unit, integrasi, E2E lintas platform."),
    ], widths=[3.2, 6.5, 6.8])

    h(d, "4. Arsitektur Aplikasi")
    para(d, "Aplikasi adalah klien tipis: seluruh logika AI, kredit, dan penyimpanan ada di backend. Mobile bertanggung jawab atas UI, sesi, cache, media perangkat, audio/WebRTC, dan notifikasi.")
    table(d, ["Direktori", "Isi"], STRUCTURE, widths=[4.5, 12])
    para(d, "Alur data utama:", bold=True)
    bullets(d, ["Login → JWT di SecureStore → semua request Authorization: Bearer; 401 → bersihkan sesi.",
                "Chat: GET messages (cache) → POST /send (SSE) → delta ditambahkan ke bubble sementara → final menggantikan → refetch ringan; WS /ws/user memicu invalidasi badge/daftar.",
                "Panggilan: POST /realtime/calls → RTCPeerConnection → SDP ke /negotiate → data channel event → tick/usage → /end saat tutup; sinyal teman via WS percakapan.",
                "Push: token FCM → POST /push/tokens {platform} → payload data {link, kind, silent} → deep link."])

    h(d, "5. Peta Jalan per Tahap")
    table(d, ["Tahap", "Nama", "Durasi", "Hasil utama"], [(p[0], p[1], p[2], p[3]) for p in PHASES], widths=[2, 5, 2.5, 7])
    for code, name, dur, goal, feats, eps, dod in PHASES:
        h(d, f"{code} — {name} ({dur})", 2)
        para(d, goal, italic=True)
        para(d, "Fitur & pekerjaan:", bold=True); bullets(d, feats)
        para(d, "Endpoint backend yang dipakai:", bold=True); bullets(d, eps)
        para(d, "Kriteria selesai (Definition of Done):", bold=True); bullets(d, dod, style="List Number")

    h(d, "6. Jadwal Ringkas")
    table(d, ["Minggu", "Tahap", "Milestone"], [
        ("1", "Tahap 0", "Dev build Android/iOS, CI, design system, kredensial lengkap"),
        ("2–4", "Tahap 1", "Login + chat streaming + asisten → Alpha internal"),
        ("5–7", "Tahap 2", "Ruang Kerja, pengingat, teman, galeri, integrasi → Alpha 2"),
        ("8–9", "Tahap 3", "Push, offline, deep link → Beta tertutup (TestFlight/Internal)"),
        ("10–13", "Tahap 4", "Panggilan Realtime & teman, CallKit/ConnectionService → Beta 2"),
        ("14–15", "Tahap 5", "IAP, keamanan, kepatuhan toko → Submit review"),
        ("16+", "Tahap 6", "Rilis bertahap, OTA, iterasi"),
    ], widths=[2.2, 2.5, 11.8])

    h(d, "7. Tim & Peran")
    table(d, ["Peran", "Tanggung jawab"], TEAM, widths=[5, 11.5])

    h(d, "8. Strategi Pengujian & Kualitas")
    table(d, ["Lapisan", "Alat", "Cakupan"], QA_MATRIX, widths=[3, 5.5, 8])
    bullets(d, ["Setiap tahap ditutup dengan regresi E2E Maestro + uji perangkat fisik; bug P0/P1 wajib nol sebelum lanjut.",
                "Kontrak API diverifikasi terhadap Swagger backend di CI; perubahan backend diumumkan lewat changelog.",
                "Kualitas suara (Tahap 4) diuji manual: barge-in, backchannel 'hmm/iya' tidak memotong, panggilan 10 menit layar terkunci."])

    h(d, "9. Kredensial & Prasyarat yang Harus Disiapkan Pemilik")
    table(d, ["Sumber", "Yang dibutuhkan"], CREDS, widths=[4.5, 12])

    h(d, "10. Risiko & Mitigasi")
    table(d, ["Risiko", "Dampak", "Mitigasi"], RISKS, widths=[5.5, 2, 9])

    h(d, "11. Metrik Keberhasilan")
    bullets(d, [("Teknis", "crash-free ≥ 99,7%, startup dingin < 2 dtk, token pertama chat < 1 dtk, latensi suara < 1,2 dtk, push < 5 dtk."),
                ("Produk", "aktivasi (login → pesan pertama) ≥ 70%, retensi D7 ≥ 35%, menit panggilan/pengguna, konversi top-up ≥ 5% pengguna aktif."),
                ("Operasional", "waktu rilis hotfix OTA < 1 jam, review toko lolos sekali jalan.")])

    h(d, "12. Lampiran A — Problem Statement Siap Tempel (Job/Project Baru)")
    para(d, "Salin teks berikut sebagai problem statement awal di project mobile:", italic=True)
    para(d, f"Bangun aplikasi mobile Oryntix (Android & iOS) dengan Expo (SDK terbaru) + React Native + TypeScript + Expo Router, menggunakan EAS development build. "
            f"Backend produksi: {BACKEND} (FastAPI, semua endpoint berawalan /api, Swagger di /docs). Bahasa UI Indonesia; brand Oryntix — warna utama #2F6BFF, gelap #0B132B, kartu putih radius 24, ikon lucide-react-native. "
            "Tahap 1: login email/kata sandi + Masuk dengan Google (POST /api/auth/google/mobile dengan ID token), tab Beranda/Chat/Ruang Kerja/Pengingat/Profil, daftar percakapan, chat teks dengan streaming SSE (POST /api/conversations/{cid}/send), "
            "grup multi-asisten, kutip/teruskan, lampiran (perangkat/Galeri/Drive), render gambar/video/dokumen, CRUD asisten + pengetahuan, WebSocket /api/ws/user untuk badge & pesan baru. "
            "Tahap 2: Ruang Kerja (tugas, versi, bandingkan, kembalikan, revisi, ekspor), pengingat & kalender, teman & undang ke percakapan, galeri, integrasi Google Drive/GitHub/GitLab, kredit, pengaturan (bahasa, zona waktu, senyapkan bunyi). "
            "Tahap 3: push FCM/APNs (POST /api/push/tokens platform android|ios, hormati flag silent), deep link oryntix:// & https://oryntix.com/*, cache offline + antrean kirim. "
            "Tahap 4: panggilan suara Realtime (POST /api/realtime/calls → /negotiate SDP → data channel oai-events), ruang grup dengan moderator, panggilan teman P2P (ICE dari GET /api/rtc/ice-servers, sinyal via WS /api/ws/{cid}), CallKit/ConnectionService + PushKit untuk panggilan masuk; lewati bagikan layar. "
            "Tahap 5: pembelian kredit via RevenueCat + verifikasi server, keamanan, aksesibilitas, kepatuhan toko, beta TestFlight/Play. Akun uji: demo@aivora.ai / demo123456.")

    h(d, "13. Lampiran B — Model Data Inti (TypeScript)")
    para(d, "type User = { id: string; email: string; name: string; avatar?: string; role: 'admin'|'user'; credits: number; plan?: string; settings: { app_language?: string; conversation_language?: string; timezone?: string; mute_sounds?: boolean } };\n"
            "type Conversation = { id: string; title: string; type: 'private'|'group'|'dm'; persona_ids: string[]; participants: string[]; members: { id: string; name: string; portrait?: string; voice?: string }[]; humans?: { id: string; name: string }[]; task_id?: string; unread?: number; last_message_at?: string; user_id: string };\n"
            "type Message = { id: string; conversation_id: string; role: 'user'|'assistant'; content: string; persona_id?: string; persona_name?: string; portrait?: string; sender_user_id?: string; sender_name?: string; attachments?: { type: string; name: string; path?: string; link?: string; drive_id?: string; task_id?: string }[]; media?: any[]; files?: any[]; reply_to?: { id: string; name: string; content: string; link?: string }; tool?: string; via?: 'text'|'realtime'|'meeting_chat'; created_at: string };\n"
            "type Persona = { id: string; name: string; summary?: string; portrait?: string; model?: string; voice?: string; profile: { identity?: any; personality?: any; system_instructions?: string } };\n"
            "type Task = { id: string; goal: string; status: 'queued'|'running'|'completed'|'failed'|'cancelled'; model?: string; persona_id?: string; version: number; versions?: { version: number; created_at: string; note?: string }[]; final_output?: string; steps?: { role: string; title: string; status: string; output?: string }[]; scheduled_at?: string };\n"
            "type Reminder = { id: string; title: string; description?: string; start_at: string; remind_minutes?: number; status: 'scheduled'|'ringing'|'done' };")

    h(d, "14. Lampiran C — Format Streaming SSE /send")
    bullets(d, ["Setiap baris: data: {json}. Event: {persona_id, persona_name, delta} (potongan teks), {persona_id, final: true, content, message_id, media?, files?, tool?}, {credits_used, credits}, {attachments_context} (hanya channel meeting_chat), [DONE].",
                "Body: {content, attachments?, channel?: 'meeting_chat', reply_to?}. Header Authorization: Bearer <jwt>. Batalkan dengan AbortController; tampilkan toast bila kredit habis (HTTP 402)."])

    d.save(f"{OUT}/Oryntix_Mobile_Development_Plan.docx")
    print("saved", f"{OUT}/Oryntix_Mobile_Development_Plan.docx")


if __name__ == "__main__":
    build()
