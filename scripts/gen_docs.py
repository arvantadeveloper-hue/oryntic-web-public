"""Generates the three Oryntix Word documents (FSD, TSD, User Manual) into frontend/public/docs."""
import os
from datetime import date
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

OUT = "/app/frontend/public/docs"
os.makedirs(OUT, exist_ok=True)
TODAY = date.today().strftime("%d %B %Y")
BLUE = RGBColor(0x2F, 0x6B, 0xFF)


def new_doc(title, subtitle):
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    for s in d.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2)
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(140)
    r = p.add_run("ORYNTIX")
    r.bold = True; r.font.size = Pt(36); r.font.color.rgb = BLUE
    p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title); r.bold = True; r.font.size = Pt(22)
    p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(subtitle); r.font.size = Pt(13); r.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(60)
    p.add_run(f"Versi 1.0 — {TODAY}\nPlatform Asisten AI Personal & Tim\nDokumen internal — rahasia").font.size = Pt(11)
    d.add_page_break()
    return d


def h(d, text, lvl=1):
    return d.add_heading(text, level=lvl)


def para(d, text, bold=False, italic=False):
    p = d.add_paragraph()
    r = p.add_run(text); r.bold = bold; r.italic = italic
    return p


def bullets(d, items, style="List Bullet"):
    for it in items:
        p = d.add_paragraph(style=style)
        if isinstance(it, tuple):
            r = p.add_run(it[0]); r.bold = True
            p.add_run(" — " + it[1])
        else:
            p.add_run(it)


def table(d, headers, rows, widths=None):
    t = d.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, hd in enumerate(headers):
        c = t.rows[0].cells[i]; c.text = ""
        r = c.paragraphs[0].add_run(hd); r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    d.add_paragraph()
    return t


def toc_note(d):
    p = para(d, "Daftar isi: klik kanan → Perbarui bidang (Update Field) di Microsoft Word untuk menampilkan daftar isi otomatis dari judul bab.", italic=True)
    # real TOC field
    run = d.add_paragraph().add_run()
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    fld = OxmlElement("w:fldSimple"); fld.set(qn("w:instr"), 'TOC \\o "1-3" \\h \\z \\u')
    run._r.append(fld)
    d.add_page_break()


MODULES = [
    ("Autentikasi & Akun", "Daftar/masuk email + kata sandi, Login Google, verifikasi email, lupa/ubah kata sandi, onboarding, Syarat & Privasi."),
    ("Workspace & Tim", "Pendaftar menjadi admin workspace; undang anggota via email; peran admin/user; multi-workspace."),
    ("Asisten (Persona)", "Buat asisten dengan nama, kepribadian, suara, model AI (OpenAI/Anthropic/Gemini), potret AI, pengetahuan (knowledge), karakter inti."),
    ("Chat", "Chat teks ala WhatsApp dengan asisten, grup multi-asisten, DM teman, grup manusia+asisten; lampiran; mention @; balas (kutip) & teruskan; arsip otomatis dengan ringkasan 2 tingkat."),
    ("Media di Chat", "Render gambar (fotorealistik/ilustrasi/logo), edit gambar terakhir, render video Seedance 2.0/2.5 (durasi, rasio 16:9/9:16/1:1/21:9, resolusi 480p/720p/1080p, mode real person, suara/ambience), kotak loading, lightbox, publikasi ke sosmed."),
    ("Dokumen", "Asisten menulis dokumen (DOCX/PDF/XLSX/PPTX) yang dapat diunduh, disimpan ke Google Drive, dan dibagikan via tautan."),
    ("Panggilan Suara & Realtime", "Panggilan suara speech-to-speech (OpenAI Realtime), panggilan grup/meeting ala Zoom dengan moderator & notulen, panggilan suara antar teman (WebRTC + TURN), barge-in, noise gate."),
    ("Ruang Kerja (Workspace Tasks)", "Penugasan tugas ke asisten dari chat/meeting, pipeline agen multi-langkah, delegasi antar asisten, hasil (dokumen/gambar/video/presentasi), jadwal & kalender."),
    ("Pengingat", "Agenda dengan pengingat yang berdering dan asisten menelepon bersuara; ringkasan harian."),
    ("Galeri", "Semua gambar, video, dan dokumen hasil chat/tugas; pencarian berdasarkan permintaan/prompt; unduh, buka chat asal, publikasikan."),
    ("Integrasi", "Google Drive/Docs/Sheets (drive.file + Picker), GitHub & GitLab (baca repo, review PR/MR otomatis), YouTube (publikasi), LinkedIn & Meta (siap, menunggu kredensial), Firebase Cloud Messaging."),
    ("Social Media", "Dasbor publikasi: caption otomatis (Gemini Vision), publikasi ke YouTube, pelacakan post."),
    ("Teman & Notifikasi", "Permintaan pertemanan, lencana unread, lonceng notifikasi (overlay), push FCM, indikator koneksi realtime."),
    ("Kredit & Paket", "Saldo kredit per workspace, paket percobaan 7 hari, top-up (simulasi), kuota harian, laporan pemakaian, tarif dinamis per model."),
    ("Admin Workspace", "Kelola anggota, undangan, pemakaian, pengaturan workspace."),
    ("Oryntix Platform (Back-office)", "Dasbor platform, pengguna, paket, tarif per fitur & per model (margin, pengali video), masa percobaan, staf & peran, laporan keuangan."),
]

API_GROUPS = [
    ("/api/auth/*", "register, login, me, google/start|exchange, verify-email, forgot/reset-password, onboard"),
    ("/api/personas/*", "CRUD asisten, portrait (generate), knowledge; /api/portraits/{pid}/{hash} (gambar potret, cacheable)"),
    ("/api/conversations/*", "list, messages, send (SSE), run-tool/cancel-tool, compact (arsip), voice-image, voice-video, social-publish, members, read"),
    ("/api/ws/user, /api/ws/{cid}", "WebSocket per pengguna & per percakapan (event + sinyal WebRTC)"),
    ("/api/realtime/*", "sesi Realtime (ephemeral token), calls tick/end, tools (delegate/assign/search/archive/drive/image/video)"),
    ("/api/tasks/*, /api/assignments/*", "Ruang Kerja: tugas, langkah, hasil, penjadwalan, presentasi"),
    ("/api/reminders/*, /api/rtc/*", "pengingat, panggilan masuk, TURN credentials, notifications/badges|feed|seen"),
    ("/api/gallery, /api/files/*, /api/shares/*", "galeri, berkas (auth/sig), tautan berbagi"),
    ("/api/integrations/*", "Google OAuth, Drive save/list/media/public, GitHub, GitLab"),
    ("/api/social/*", "akun sosmed, caption, publish, posts"),
    ("/api/wallet/*, /api/admin/*, /api/platform/*", "kredit & paket, admin workspace, back-office platform (pricing, users, staff, finance)"),
]

COLLECTIONS = [
    ("users", "akun, peran, workspace, kredit (pemilik), notifications_seen_at, google_sub"),
    ("workspaces, invites", "workspace & undangan anggota"),
    ("personas", "asisten: profil, kepribadian, suara, model, portrait (URL), knowledge"),
    ("conversations", "percakapan: type (private/group/dm), members, participants, titles, read_at, last_message, archived_at, memory_summary"),
    ("messages", "pesan: role, content, media[], attachments, tool, pending_tool, rendering, reply_to, forwarded, archived"),
    ("archives", "arsip percakapan + ringkasan"),
    ("tasks, assignments", "tugas Ruang Kerja, langkah, hasil, jadwal"),
    ("reminders, realtime_calls", "pengingat & sesi panggilan"),
    ("friends, notifications", "pertemanan & log notifikasi"),
    ("integrations, drive_credentials, social_accounts", "token OAuth terenkripsi (Fernet)"),
    ("usage, wallet_tx, config", "pemakaian kredit, transaksi, konfigurasi platform (platform_pricing, model_routing, trial_config)"),
]


def build_fsd():
    d = new_doc("Functional Specification Document", "Spesifikasi Fungsional Platform Oryntix")
    toc_note(d)
    h(d, "1. Pendahuluan")
    h(d, "1.1 Tujuan Dokumen", 2)
    para(d, "Dokumen ini menjelaskan kebutuhan fungsional platform Oryntix: apa yang dapat dilakukan pengguna, aturan bisnis, dan perilaku sistem yang diharapkan. Dokumen ditujukan untuk pemilik produk, tim pengembang, QA, dan pemangku kepentingan bisnis.")
    h(d, "1.2 Ruang Lingkup", 2)
    para(d, "Oryntix adalah platform asisten AI personal dan tim: pengguna membuat asisten AI yang dipersonalisasi, berinteraksi lewat chat teks dan suara (realtime), berkolaborasi dalam ruang kerja multi-agen, menghasilkan media (gambar, video, dokumen), serta mengelola pengingat, integrasi pihak ketiga, dan publikasi media sosial. Platform dioperasikan dengan model kredit berbayar per fitur.")
    h(d, "1.3 Definisi & Istilah", 2)
    table(d, ["Istilah", "Definisi"], [
        ("Asisten / Persona", "Agen AI yang dibuat pengguna dengan nama, kepribadian, suara, dan model AI tertentu."),
        ("Workspace", "Ruang kerja/tenant yang dimiliki satu admin dan beranggotakan beberapa pengguna; saldo kredit melekat pada pemilik workspace."),
        ("Kredit", "Satuan biaya platform (1.000 kredit = USD 1). Setiap fitur berbayar memotong kredit sesuai tarif platform."),
        ("Ruang Kerja (Tasks)", "Modul penugasan di mana asisten mengerjakan tugas multi-langkah dan menghasilkan artefak."),
        ("Realtime", "Mode percakapan suara dua arah berbasis OpenAI Realtime API."),
        ("Platform Admin", "Back-office operator Oryntix (tarif, paket, pengguna, keuangan)."),
    ], [4, 12])
    h(d, "2. Gambaran Umum Sistem")
    para(d, "Aplikasi web responsif (desktop & mobile) dengan backend API dan basis data dokumen. Pembaruan antarmuka bersifat realtime melalui WebSocket dan Firebase Cloud Messaging; permintaan GET berkala hanya dilakukan ketika koneksi realtime terputus.")
    h(d, "2.1 Pengguna & Peran", 2)
    table(d, ["Peran", "Hak Utama"], [
        ("Pemilik/Admin Workspace", "Semua fitur pengguna + kelola anggota, undangan, kredit, laporan pemakaian, pengaturan workspace."),
        ("Anggota Workspace (User)", "Membuat asisten, chat, panggilan, tugas, pengingat, galeri, integrasi pribadi."),
        ("Teman", "Pengguna lain yang terhubung lewat permintaan pertemanan; dapat DM dan panggilan suara."),
        ("Staf Platform (Owner/Admin/Finance/Support)", "Akses back-office sesuai peran: tarif, paket, pengguna, keuangan, percobaan."),
    ], [5, 11])
    h(d, "3. Modul Fungsional")
    for i, (name, desc) in enumerate(MODULES, 1):
        h(d, f"3.{i} {name}", 2)
        para(d, desc)
    h(d, "4. Spesifikasi Fitur Terperinci (Terpilih)")
    h(d, "4.1 Chat & Media", 2)
    bullets(d, [
        ("Kirim pesan", "Pengguna mengetik pesan; asisten membalas secara streaming. Pesan baru muncul via WebSocket tanpa memuat ulang."),
        ("Deteksi permintaan media", "Permintaan gambar/video (termasuk 'render', 'tunjukkan', 'animasikan') dikenali; asisten tidak boleh menyatakan tidak mampu merender. Jika model menolak, sistem tetap merender."),
        ("Konfirmasi biaya", "Jika estimasi kredit ≥ ambang konfirmasi platform, asisten menanyakan 'Lanjutkan?' dengan tombol."),
        ("Render gambar", "Gambar muncul dalam bubble; selama proses tampil kotak shimmer 4:3 'Merender gambar…'. Klik gambar membuka lightbox."),
        ("Edit gambar", "Perintah 'ubah jadi kartun / ganti latar' mengedit gambar terakhir sebagai referensi visual."),
        ("Render video", "Syarat: Google Drive terhubung dan saldo mencukupi. Kartu pilihan: model Seedance 2.0/2.5, resolusi, mode real person (hanya image-to-video + izin), suara. Harga kredit/detik ditampilkan dari tarif platform; render berjalan di latar; hasil disimpan ke Google Drive pengguna dan tampil di chat."),
        ("Balas & teruskan", "Pengguna dapat mengutip pesan asisten dan meneruskan pesan ke percakapan lain."),
        ("Arsip otomatis", "Percakapan panjang diringkas (2 tingkat) dan diarsipkan; chat memuat ulang dari server saat arsip selesai."),
    ])
    h(d, "4.2 Panggilan Suara Realtime", 2)
    bullets(d, [
        "Pengguna memulai panggilan suara dengan asisten; percakapan berlangsung dua arah dengan latensi rendah dan dapat disela (barge-in).",
        "Asisten memiliki alat: delegasi tugas, pencarian ruang kerja, arsip, Google Drive, pembuatan gambar, dan penawaran video; hasil muncul di panel chat samping.",
        "Panggilan grup (meeting) mendukung beberapa asisten dan manusia, moderator aktif, dan notulen otomatis.",
    ])
    h(d, "4.3 Ruang Kerja", 2)
    bullets(d, [
        "Tugas dapat dibuat dari chat/meeting ('tugaskan ke Rio'), memiliki langkah, status (queued/running/done), hasil berkas, dan jadwal.",
        "Progres tugas dipancarkan realtime; asisten dapat mendelegasikan sub-tugas ke asisten lain.",
    ])
    h(d, "4.4 Kredit & Tarif", 2)
    bullets(d, [
        "Setiap fitur berbayar memotong kredit pemilik workspace sesuai tarif platform (biaya USD × margin → kredit).",
        "Tarif per model AI (token input/output), gambar, video per detik (Seedance 2.0 & 2.5) dengan pengali resolusi, mode real person, dan suara.",
        "Kredit video dipotong hanya jika render berhasil; kegagalan provider tidak dibebankan.",
        "Paket percobaan 7 hari dengan kuota harian; dialog Upgrade Paket saat kuota habis.",
    ])
    h(d, "5. Aturan Bisnis")
    bullets(d, [
        "Pengguna yang mendaftar mandiri otomatis menjadi admin workspace-nya sendiri.",
        "Video hasil render tidak disimpan di penyimpanan platform; wajib ke Google Drive pengguna.",
        "Mode real person memerlukan konfirmasi hak/izin dari pengguna dan hanya tersedia untuk image-to-video pada Seedance 2.0.",
        "Pesan berdurasi burst dibatasi (rate limiting) untuk mencegah spam.",
        "Asisten tidak menyapa lebih dahulu; percakapan dimulai oleh pengguna.",
    ])
    h(d, "6. Kebutuhan Non-Fungsional")
    table(d, ["Aspek", "Kebutuhan"], [
        ("Kinerja", "Pesan realtime < 1 detik via WebSocket; gambar render ±10–20 detik; video 2–7 menit (asinkron)."),
        ("Ketersediaan", "Reconnect WebSocket otomatis dengan backoff; fallback polling saat terputus; indikator koneksi di header."),
        ("Keamanan", "JWT dengan masa berlaku; token OAuth terenkripsi; akses percakapan dibatasi pemilik/peserta; tautan berkas bertanda tangan; CORS & rate limit."),
        ("Skalabilitas", "Stateless API; penyimpanan objek untuk media; cache potret asisten immutable."),
        ("Lokalisasi", "Bahasa Indonesia sebagai bahasa utama antarmuka."),
        ("Kepatuhan", "Halaman Syarat & Kebijakan Privasi; kepatuhan penggunaan wajah nyata (consent)."),
    ], [4, 12])
    h(d, "7. Batasan & Asumsi")
    bullets(d, [
        "Render video memerlukan akun provider Seedance berbayar dan host gambar yang disetujui untuk image-to-video.",
        "Publikasi LinkedIn & Meta memerlukan kredensial aplikasi dari pengguna.",
        "Pembayaran kredit saat ini simulasi (belum terhubung payment gateway).",
    ])
    d.save(f"{OUT}/Oryntix_Functional_Specification.docx")


def build_tsd():
    d = new_doc("Technical Specification Document", "Spesifikasi Teknis & Arsitektur Platform Oryntix")
    toc_note(d)
    h(d, "1. Ringkasan Arsitektur")
    para(d, "Oryntix dibangun dengan arsitektur tiga lapis: frontend React (SPA), backend FastAPI (Python, asinkron), dan MongoDB sebagai basis data dokumen, ditambah penyimpanan objek untuk media. Komunikasi realtime menggunakan WebSocket (per pengguna dan per percakapan) serta Firebase Cloud Messaging untuk push saat tab tidak aktif.")
    table(d, ["Lapisan", "Teknologi"], [
        ("Frontend", "React 18, React Router, TailwindCSS, shadcn/ui, lucide-react, sonner, Service Worker (FCM + cache potret)"),
        ("Backend", "FastAPI, Uvicorn, Motor (MongoDB async), httpx, PyJWT, cryptography (Fernet), python-docx/pptx/openpyxl, LiteLLM/emergentintegrations"),
        ("Data", "MongoDB (dokumen), Object Storage (gambar, dokumen, potret), Google Drive pengguna (video)"),
        ("Realtime", "WebSocket FastAPI (/api/ws/user, /api/ws/{cid}), OpenAI Realtime API (WebRTC), WebRTC P2P + TURN (Metered)"),
        ("AI", "OpenAI (GPT, Realtime gpt-realtime-2.1, gpt-image), Anthropic Claude, Google Gemini (teks, vision, image), Seedance (seedance2video.io) untuk video, fal.ai (legacy video Ruang Kerja)"),
        ("Infrastruktur", "Kubernetes (preview/produksi), ingress /api → backend 8001, frontend 3000; variabel lingkungan via .env"),
    ], [4, 12])
    h(d, "2. Struktur Kode")
    h(d, "2.1 Backend (/app/backend)", 2)
    table(d, ["Modul", "Tanggung jawab"], [
        ("server.py", "Aplikasi FastAPI, router, WebSocket endpoints, scheduler loop, migrasi startup (potret)"),
        ("auth.py / google_auth.py", "JWT, registrasi/login, verifikasi email, reset password, Google OAuth, onboarding"),
        ("chat.py", "Percakapan, pesan (SSE streaming), routing tool (gambar/edit/video/dokumen/drive/github/social), run-tool, arsip, voice-image/voice-video"),
        ("tools.py", "Planner tool (LLM JSON), regex deteksi (MEDIA_RE, EDIT_RE), run_image_tool, dokumen"),
        ("seedance.py", "Klien API seedance2video.io: tier 2.0/2.5, quote & multipliers, generate (poll), download"),
        ("realtime.py / realtime_voice.py", "Manajer koneksi WS (ConnectionManager, UserManager), enrich event, sesi Realtime & definisi tool suara"),
        ("notif_state.py", "Snapshot badges, feed lonceng, baris percakapan, baris tugas (dipakai GET & event WS)"),
        ("agents.py / workspace.py / assignments.py", "Pipeline agen Ruang Kerja, langkah, delegasi, emit progres"),
        ("integrations.py / github.py / gitlab.py / social.py", "Google Drive (OAuth, save, media stream, signed public), GitHub/GitLab, publikasi sosmed"),
        ("pricing.py / wallet.py / admin.py / platform_*.py", "Mesin tarif (USD→kredit, margin, pengali video), kredit, admin workspace, back-office"),
        ("portraits.py / storage.py / files.py / gallery.py", "Potret asisten content-addressed, penyimpanan objek, berkas bertanda tangan, galeri"),
        ("push.py / rtc.py / reminders.py / archives.py", "FCM, TURN & notifikasi, pengingat berdering, arsip & ringkasan"),
    ], [5, 11])
    h(d, "2.2 Frontend (/app/frontend/src)", 2)
    table(d, ["Direktori / Berkas", "Isi"], [
        ("pages/", "Home, Chat, Personas, CreatePersona, Workspace, TaskDetail, Reminders, Calendar, Gallery, Integrations, SocialMedia, Archives, Friends, Wallet, Profile, Admin, platform/*"),
        ("components/", "AppLayout (nav, badge, ConnectionDot), MessageExtras (MediaList, Lightbox, RenderingBox, ToolRequestCard, VideoChoiceCard, PublishDialog), RealtimeCall, MeetingShell, TaskPanel, NotificationBell, Gallery"),
        ("lib/api.js", "Axios instance, token, SSE streamChatWithAtt, openConvSocket (keepalive + reconnect)"),
        ("lib/userEvents.js", "Kanal event pengguna: WS /api/ws/user, isWsConnected, useLiveSync (polling hanya saat offline), FCM foreground"),
        ("lib/firebase.js", "Konfigurasi FCM, registrasi Service Worker (push + cache potret)"),
        ("public/firebase-messaging-sw.js", "Service Worker: notifikasi background, cache-first /api/portraits/*"),
    ], [5, 11])
    h(d, "3. Model Data (MongoDB)")
    table(d, ["Koleksi", "Isi utama"], COLLECTIONS, [5, 11])
    para(d, "Konvensi: setiap dokumen memiliki `id` (UUID string) sebagai kunci publik; `_id` Mongo tidak pernah dikembalikan ke klien. Waktu disimpan ISO-8601 UTC.", italic=True)
    h(d, "4. Antarmuka API")
    para(d, "Semua endpoint diawali /api. Autentikasi: header Authorization: Bearer <JWT> (atau query ?auth= untuk tautan unduhan/stream). Streaming balasan chat menggunakan Server-Sent Events.")
    table(d, ["Kelompok", "Endpoint / Fungsi"], API_GROUPS, [5, 11])
    h(d, "4.1 Event WebSocket (/api/ws/user)", 2)
    table(d, ["type", "Payload tambahan", "Pemicu"], [
        ("message_new", "badges, conversation (baris percakapan), preview", "Pesan baru di percakapan yang diikuti"),
        ("notification / friend_request / reminder_due", "badges, feed (lonceng)", "Notifikasi, pertemanan, pengingat berdering"),
        ("incoming_call", "badges, detail panggilan", "Panggilan teman/asisten masuk"),
        ("task_update", "badges, task (ringkas), progress", "Perubahan status/langkah tugas"),
        ("archived", "conversation_id, archived_at, badges", "Arsip percakapan selesai"),
    ], [4, 6, 6])
    para(d, "Event percakapan (/api/ws/{cid}): {type:'message', message:{...}} untuk pesan lengkap (termasuk pembaruan media video), {type:'archived'}, dan relay sinyal WebRTC {type:'rtc'}. Klien mengirim ping tiap 25 detik; server mengabaikan teks masuk selain sinyal rtc.")
    h(d, "5. Alur Teknis Utama")
    h(d, "5.1 Pesan Chat & Tool", 2)
    bullets(d, [
        "POST /conversations/{cid}/send → simpan pesan user → intercept (task offer, revisi, tool) → jika wants_tool (regex MEDIA_RE/DRIVE/GITHUB/SOCIAL atau EDIT/ANIMATE dengan gambar terakhir) → plan_tool (LLM JSON) → _tool_turn.",
        "image: run_image_tool (Gemini image, opsional referensi) → simpan ke storage → pesan dengan media; event SSE status+rendering untuk kotak shimmer.",
        "video: video_offer → cek SEEDANCE_API_KEY, Drive terhubung, saldo → pending_tool berisi options/multipliers → klien memilih → POST run-tool?choice&resolution&real_person&with_audio → placeholder rendering → _run_video_bg: seedance.generate (poll) → download → drive_save → update pesan + notify WS.",
        "Safety net: jika balasan LLM berisi penolakan merender sementara user meminta media (is_media_refusal), sistem menjalankan tool.",
    ])
    h(d, "5.2 Realtime Voice", 2)
    bullets(d, [
        "Klien meminta ephemeral token; sesi WebRTC langsung ke OpenAI dengan instruksi persona (assistant_persona.py) dan daftar tool.",
        "Panggilan tool dari model dieksekusi klien via lib/realtimeSession.js → REST backend (voice-image, voice-video, assign, search, drive…) → hasil diposting ke panel chat via WS.",
    ])
    h(d, "5.3 Realtime Sync & Fallback", 2)
    bullets(d, [
        "notify_user hanya mengirim ke pengguna online; payload diperkaya (_enrich) agar klien tidak perlu GET lanjutan.",
        "useLiveSync: jalankan fn saat mount, saat event push, saat reconnect, saat tab kembali visible; interval GET hanya ketika isWsConnected() false.",
        "Deteksi putus: onclose socket, window offline/online; indikator ConnectionDot.",
    ])
    h(d, "6. Mesin Tarif")
    para(d, "Konfigurasi platform_pricing (DEFAULT_PRICING + override admin) → compute_rates → RATES. Kredit = ceil(USD biaya × (1+margin) × 1000 / kurs). Video: kredit/detik tier × durasi × pengali resolusi (480p 0.6, 1080p 1.6) × pengali real person (1.45) × pengali suara (1.0). Harga model AI dipetakan dari harga per 1M token.")
    h(d, "7. Keamanan")
    bullets(d, [
        "JWT HS256 dengan freshness check (invalid setelah ganti password); WS menolak token tidak valid (4401) dan akses percakapan tanpa hak (4403).",
        "Token OAuth (Google, GitHub, sosmed) dienkripsi Fernet; kunci di .env.",
        "Tautan berkas publik bertanda tangan (sig JWT, purpose, exp); Drive public link berumur 1 jam.",
        "Rate limiting sliding window per pengguna/fitur; validasi Pydantic di semua input.",
        "CORS terbatas; tidak ada kredensial di frontend; kunci API hanya di backend/.env.",
    ])
    h(d, "8. Konfigurasi Lingkungan (.env backend)")
    table(d, ["Variabel", "Fungsi"], [
        ("MONGO_URL, DB_NAME", "Koneksi MongoDB"),
        ("JWT_SECRET, FERNET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD", "Autentikasi & enkripsi"),
        ("EMERGENT_LLM_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY", "Penyedia AI"),
        ("SEEDANCE_API_KEY", "Render video seedance2video.io"),
        ("GOOGLE_CLIENT_ID/SECRET, GOOGLE_MOBILE_CLIENT_IDS", "OAuth Google (login & Drive)"),
        ("FCM_SERVICE_ACCOUNT_B64, REACT_APP_FIREBASE_*", "Push notification"),
        ("STORAGE_URL / kredensial storage, METERED_*", "Penyimpanan objek, TURN"),
        ("SMTP_* / RESEND_API_KEY", "Email verifikasi & undangan"),
    ], [6, 10])
    h(d, "9. Deployment & Operasional")
    bullets(d, [
        "Supervisor menjalankan backend (0.0.0.0:8001) dan frontend (3000); ingress meneruskan /api ke backend.",
        "Hot reload untuk pengembangan; produksi dipublikasikan hanya atas permintaan pemilik produk.",
        "Migrasi startup idempoten (mis. potret base64 → storage) berjalan sebagai task latar saat aplikasi mulai.",
        "Pemantauan: log supervisor; event penting dicatat dengan logger 'chat', 'portraits', 'aivora'.",
    ])
    h(d, "10. Pengujian")
    bullets(d, [
        "Laporan iterasi pengujian otomatis tersimpan di /app/test_reports/iteration_N.json (backend via curl/pytest, frontend via Playwright).",
        "Kredensial uji: /app/memory/test_credentials.md (akun demo, budi, admin).",
    ])
    d.save(f"{OUT}/Oryntix_Technical_Specification.docx")


def build_manual():
    d = new_doc("User Manual", "Panduan Pengguna Oryntix")
    toc_note(d)
    h(d, "1. Memulai")
    h(d, "1.1 Membuat Akun & Masuk", 2)
    bullets(d, [
        "Buka halaman Masuk. Pilih Daftar, isi nama, email, kata sandi (ulangi kata sandi), setujui Syarat & Privasi, lalu verifikasi email dari tautan yang dikirim.",
        "Atau klik Masuk dengan Google. Akun Google yang sama akan selalu kembali ke workspace yang sama.",
        "Lupa kata sandi? Klik Lupa kata sandi dan ikuti tautan reset di email.",
    ], "List Number")
    h(d, "1.2 Onboarding", 2)
    para(d, "Setelah masuk pertama kali Anda diminta mengisi profil singkat dan membuat asisten pertama (nama, kepribadian, suara). Anda dapat melewati dan membuatnya nanti dari menu AI Agents.")
    h(d, "1.3 Mengenal Antarmuka", 2)
    table(d, ["Menu", "Fungsi"], [
        ("Dashboard", "Ringkasan aktivitas, kredit, tugas terbaru"),
        ("Chat & Panggilan", "Semua percakapan: asisten, teman, grup; mulai panggilan suara"),
        ("AI Agents", "Buat & kelola asisten"),
        ("Ruang Kerja", "Tugas yang dikerjakan asisten, jadwal, hasil"),
        ("Pengingat / Kalender", "Agenda dan pengingat berdering"),
        ("Galeri", "Semua gambar, video, dokumen hasil AI"),
        ("Integrasi", "Google Drive, GitHub, GitLab, YouTube, dll."),
        ("Social Media", "Publikasi konten dan riwayat post"),
        ("Arsip, Teman, Kredit, Settings", "Arsip percakapan, pertemanan, saldo & paket, profil"),
    ], [4, 12])
    para(d, "Di kanan atas terdapat saldo kredit, titik status koneksi (hijau = realtime terhubung; kuning = menyambung ulang), lonceng notifikasi, dan tombol New.")
    h(d, "2. Membuat Asisten")
    bullets(d, [
        "Buka AI Agents → + Asisten Baru.",
        "Isi nama, peran/kepribadian, gaya bicara, suara, dan pilih model AI (OpenAI, Claude, Gemini). Model memengaruhi biaya kredit per pesan.",
        "Klik Buat Potret untuk menghasilkan foto asisten (menggunakan kredit) atau unggah foto referensi.",
        "Tambahkan Pengetahuan (teks/berkas) agar asisten menjawab sesuai konteks bisnis Anda.",
    ], "List Number")
    h(d, "3. Chat dengan Asisten")
    h(d, "3.1 Mengirim Pesan & Lampiran", 2)
    para(d, "Pilih asisten di panel kiri, ketik pesan, tekan Enter. Klik ikon klip untuk melampirkan gambar/dokumen. Dalam grup, sebut @NamaAsisten untuk menuju asisten tertentu.")
    h(d, "3.2 Meminta Gambar", 2)
    bullets(d, [
        "Ketik permintaan apa adanya, misal: 'buatkan logo kedai kopi minimalis' atau 'render foto realistis kucing oranye di jendela'.",
        "Jika biaya di atas ambang, asisten menanyakan 'Lanjutkan?' — klik Lanjutkan. Kotak 'Merender gambar…' muncul hingga gambar jadi.",
        "Klik gambar untuk melihat ukuran besar (lightbox); di sana ada tombol Unduh dan Publikasikan.",
        "Untuk mengubah: 'ubah jadi gaya kartun', 'ganti latarnya jadi malam' — asisten mengedit gambar terakhir.",
    ])
    h(d, "3.3 Meminta Video", 2)
    bullets(d, [
        "Hubungkan Google Drive terlebih dahulu (Integrasi → Google Drive); video disimpan ke Drive Anda, bukan di server.",
        "Ketik misal: 'buatkan video 8 detik ombak di pantai, versi portrait untuk Reels, 1080p, dengan suara ambience'.",
        "Kartu pilihan muncul: pilih Resolusi (480p Hemat / 720p / 1080p Tajam), Suara, Mode (Normal / Real person — hanya saat menganimasikan gambar dan setelah mencentang izin), lalu klik Seedance 2.0 atau 2.5. Harga kredit per detik dan total tampil di tombol.",
        "Render berjalan 2–5 menit di latar; Anda bisa melanjutkan chat. Video muncul otomatis di pesan yang sama dengan tombol Buka di Google Drive.",
        "Untuk menganimasikan gambar terakhir: 'animasikan gambar ini jadi video 5 detik'.",
        "Tanya 'berapa harga video per detik?' — asisten menjawab dari tarif platform.",
    ])
    h(d, "3.4 Dokumen", 2)
    para(d, "Minta 'buatkan proposal dalam Word' atau 'buat tabel anggaran Excel'. Berkas dapat diunduh, disimpan ke Google Drive, atau dibagikan lewat tautan.")
    h(d, "3.5 Balas, Teruskan, Arsip", 2)
    bullets(d, [
        "Arahkan kursor ke pesan asisten → ikon Balas (mengutip pesan) atau Teruskan (kirim ke percakapan lain).",
        "Percakapan panjang diringkas dan diarsipkan otomatis; cari & pulihkan lewat menu Arsip atau minta asisten mencarinya.",
    ])
    h(d, "4. Panggilan Suara")
    bullets(d, [
        "Di chat asisten klik ikon telepon untuk panggilan suara realtime. Bicara natural; Anda dapat menyela asisten.",
        "Minta gambar atau video lewat suara — hasil/kartu pilihan muncul di panel chat samping.",
        "Panggilan grup: buat grup dengan beberapa asisten/teman → Mulai Panggilan. Moderator mencatat notulen otomatis.",
        "Panggilan dengan teman menggunakan koneksi langsung (WebRTC); izinkan mikrofon saat diminta.",
    ])
    h(d, "5. Ruang Kerja")
    bullets(d, [
        "Dari chat: 'tugaskan ke Rio: susun laporan penjualan Q3' → tugas dibuat dan dikerjakan bertahap.",
        "Pantau progres di Ruang Kerja; hasil (dokumen/gambar/presentasi) tersedia di detail tugas dan Galeri.",
        "Jadwalkan tugas berulang dan lihat di Kalender.",
    ])
    h(d, "6. Pengingat")
    para(d, "Buat pengingat dengan waktu; saat jatuh tempo pengingat berdering dan asisten dapat menelepon Anda. Ringkasan harian dikirim sesuai pengaturan.")
    h(d, "7. Galeri & Publikasi")
    bullets(d, [
        "Galeri memuat semua media hasil chat/tugas. Cari dengan kata dari permintaan Anda (mis. 'kucing', 'malam').",
        "Tombol Chat membuka percakapan asal; Publikasikan membuka dialog caption otomatis dan pilihan jaringan (YouTube aktif; LinkedIn & Meta setelah kredensial tersedia).",
    ])
    h(d, "8. Integrasi")
    table(d, ["Integrasi", "Cara menghubungkan", "Manfaat"], [
        ("Google Drive", "Integrasi → Hubungkan Google → izinkan akses berkas aplikasi", "Simpan dokumen & video hasil AI; asisten dapat membaca berkas yang Anda pilih"),
        ("GitHub / GitLab", "Masukkan Personal Access Token", "Asisten membaca repo dan mereview PR/MR"),
        ("YouTube", "Hubungkan akun Google dengan izin YouTube", "Publikasi video langsung dari chat/Galeri"),
        ("Notifikasi Push", "Izinkan notifikasi di browser", "Pemberitahuan pesan, pengingat, panggilan saat tab tidak aktif"),
    ], [3.5, 6.5, 6])
    h(d, "9. Kredit & Paket")
    bullets(d, [
        "Saldo kredit ada di kanan atas dan halaman Kredit. Setiap pesan, gambar, video, dan panggilan memotong kredit sesuai tarif.",
        "Masa percobaan 7 hari memiliki kuota harian; klik Tambah Kredit / Upgrade Paket saat habis.",
        "Video hanya memotong kredit jika render berhasil.",
    ])
    h(d, "10. Teman & Notifikasi")
    para(d, "Kirim permintaan pertemanan lewat menu Teman; setelah diterima Anda dapat DM dan menelepon. Lonceng menampilkan notifikasi; lencana merah di menu Chat menunjukkan pesan belum dibaca.")
    h(d, "11. Admin Workspace")
    bullets(d, [
        "Undang anggota via email (menu Admin). Anggota memakai kredit workspace Anda.",
        "Lihat laporan pemakaian per anggota/asisten dan kelola peran.",
    ])
    h(d, "12. Pemecahan Masalah")
    table(d, ["Gejala", "Solusi"], [
        ("Titik status kuning 'Menyambung ulang…'", "Periksa koneksi internet; aplikasi otomatis tersambung kembali dan memuat ulang data."),
        ("Asisten tidak membuat gambar/video", "Pastikan saldo kredit cukup; untuk video, hubungkan Google Drive. Jika pesan menyebut provider/paket, hubungi admin platform."),
        ("Video gagal: host belum disetujui / paket berbayar", "Konfigurasi provider Seedance di sisi admin platform; kredit Anda tidak dipotong."),
        ("Notifikasi push tidak muncul", "Izinkan notifikasi di browser dan pastikan tidak dalam mode privat."),
        ("Login Google diarahkan ke onboarding", "Lengkapi onboarding sekali; akun dan data tetap tersimpan."),
    ], [6, 10])
    h(d, "13. Kontak Dukungan")
    para(d, "Gunakan menu bantuan (?) di kanan atas atau hubungi admin workspace Anda. Untuk masalah platform, hubungi tim Oryntix.")
    d.save(f"{OUT}/Oryntix_User_Manual.docx")


if __name__ == "__main__":
    build_fsd(); build_tsd(); build_manual()
    print("ok", os.listdir(OUT))
