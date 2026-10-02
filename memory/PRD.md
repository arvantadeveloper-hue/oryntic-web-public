# Aivora (Persona AI) — PRD & Implementation Status

## Original problem statement
Build "Persona AI / Aivora": an AI personal assistant + companion + multi-agent workspace. The approved MVP is a **responsive web app** (not mobile native), using React + FastAPI + MongoDB, JWT email/password auth, GPT (text) and Gemini Nano Banana (image) via the Emergent Universal Key.

## Architecture
- **Backend**: FastAPI, modular routers — `auth.py`, `personas.py`, `chat.py`, `agents.py`, `reminders.py`, `wallet.py`, `admin.py`; shared `db.py` (Motor/MongoDB), `llm.py` (LLM + image + credit metering). All routes under `/api`. Background scheduler loop for reminders.
- **Frontend**: React (CRA/craco), react-router, context (Auth + i18n ID/EN), Tailwind + custom Aivora dark theme, sonner toasts, recharts, lucide icons.
- **Integrations**: Emergent Universal Key — GPT `gpt-5.4` (text/chat/structured), Gemini `gemini-3.1-flash-image-preview` (portraits). JWT auth (bcrypt), registration auto-verifies (no SMTP in MVP).

## User personas
Individuals & professionals who want one AI assistant to delegate work (research, writing, analysis, planning), chat with self-made AI characters, and get proactive reminders.

## Core requirements (static)
Account/onboarding; Create-Your-Persona studio (describe/photo/combine); streaming chat + per-persona memory; multi-agent coordinator (Aivora) + task workspace; proactive in-app reminder "calls"; transparent credit wallet; basic admin.

## Implemented (2026-06, MVP — COMPLETE, tested 40/40 backend + 10/10 FE)
- **Auth & onboarding**: register/login/me/onboard, JWT, admin seed, 500 welcome credits.
- **Personas**: GPT structured-profile generation (3 methods), Gemini portrait generation + regenerate, NL edit, form fields, duplicate, soft-delete, versions.
- **Chat**: SSE streaming responses, history, search, copy/regenerate/save-to-memory, per-persona context + memory CRUD.
- **Multi-agent**: coordinator plans 2–4 subtasks across role agents (Research/Planning/Writing/Analyst/Coding), runs in background, Reviewer merges final deliverable; live status polling.
- **Workspace**: task list, status filters, search, task detail with subtask progress, final output, export `.md`.
- **Reminders**: schedule + backend scheduler marks due → "ringing"; global in-app incoming-call overlay with Accept/Decline; honest AI reminder message.
- **Wallet**: balance, usage breakdown chart, 5 credit packages, SIMULATED top-up, transaction ledger, usage events per activity.
- **Admin**: overview metrics, users, tasks, pricing/providers (RBAC-protected).
- **i18n**: ID/EN toggle; dark premium Aivora theme with brand assets.

## Known limitations / MOCKED
- **Top-up is SIMULATED** (no real payment gateway) — web MVP constraint.
- Email verification auto-passes (no SMTP configured).
- Reminder "calls" are in-app only (no native VoIP/CallKit/push).

## Backlog (deferred phases)
- **P1**: Voice (STT/TTS), real payment gateway, full admin console + dynamic provider price catalog/margin engine, group chat/meeting multi-persona, full multilingual + RTL, RBAC for finance/ops/support/auditor.
- **P2**: Realtime digital human/avatar + lip-sync, video call, native mobile (React Native) + VoIP inbound, music-synced avatar dance, automated provider price monitoring + full reconciliation.
- **Tech debt (non-blocking)**: migrate FastAPI `on_event` → lifespan; per-user rate limit/cooldown on portrait+task endpoints; rotate JWT_SECRET and tighten CORS before production; aggregate wallet usage for scale.

## Update 2026-06 — Team concept, no default assistant, per-persona models
- Removed the built-in "Aivora" assistant entirely. Aivora is the brand/product only. First-time users are routed to create their own persona right after onboarding.
- Chat now supports **private** (1 persona) and **group** (multiple personas) conversations. In a group, each persona replies in turn with its own avatar/name, aware of the other members. New-chat picker on the Chat page; Home shows "Tim Asisten Anda".
- Each persona has a selectable **model ("brain")** from a catalog: GPT Astra (gpt-6-astra), GPT Luna (gpt-6-luna), GPT Terra (gpt-5.6-terra, default), Claude Sonnet (claude-sonnet-5-5), Gemini Pro (gemini-3.1-pro-preview). Selectable at creation and editable in persona detail. Backend GET /api/models serves the catalog; chat/orchestration resolve provider+model per persona. All 5 models verified working via Universal Key.

## Update 2026-06 (b) — Voice, meetings, attachments, mentions, task-model recommendation
- **Voice (STT/TTS)**: Whisper transcription (mic button in chat composer) + OpenAI TTS (per-message play + "speaker" auto-read toggle). Endpoints `/api/voice/transcribe`, `/api/voice/tts`, `/api/voice/voices`.
- **Meeting multi-persona**: new conversation type `meeting` — all personas respond, then a built-in **Moderator** posts a markdown summary (key points, agreements, action items). Chosen via Grup/Meeting toggle in the new-chat modal.
- **Group moderator / @mention**: in group/meeting, mentioning `@Name` routes the turn to just that persona; otherwise all respond in sequence. Per-persona **typing indicator** (bouncing dots via SSE `start` events).
- **Attachments**: upload image/PDF/text in chat; backend extracts PDF text (pypdf), vision-describes images (gemini), and injects as context. Shown as chips.
- **Task model recommendation**: `/api/tasks/recommend` classifies the goal and suggests the best model only when it differs from default (DB: video→Seedance 2.5 [not executable here], code/writing→Claude Sonnet, research/image→Gemini Pro, data→GPT Astra). Workspace surfaces a picker only when a better model is recommended; otherwise runs on default. Tasks run with the chosen model.

## Update 2026-06 (c) — Call mode, Seedance video, meeting notes, per-persona voice
- **Mode Panggilan Suara**: overlay panggilan di chat privat — loop dengar (mic) → tekan Kirim → transkrip (Whisper) → balas persona → TTS suara persona → otomatis dengar lagi. Hands-light.
- **Eksekusi Video (Seedance)**: tugas kategori video di Ruang Kerja memanggil Seedance via fal.ai Universal Key (queue submit→poll per playbook, `video_gen.py`, endpoint via env `SEEDANCE_ENDPOINT`); hasil video_url tampil sebagai player di TaskDetail. Jika gagal/tak didukung, tugas tetap selesai dengan rencana + catatan jujur.
- **Notulen Meeting Tersimpan**: ringkasan Moderator meeting otomatis dibuat jadi dokumen `meeting_notes` di Ruang Kerja.
- **Suara Persona**: tiap persona punya voice TTS sendiri (field `voice`, selektor di detail persona); dipakai di auto-read, tombol play, dan mode panggilan.

## Update 2026-06 (d) — VAD call mode, permanent video storage, onboarding voice picker, responsive polish
- **Deteksi Diam (VAD)**: Mode Panggilan kini hands-free. Memakai Web Audio AnalyserNode (RMS) — auto-kirim giliran setelah pengguna berhenti bicara ~1.4s, dan **auto-akhiri panggilan** bila tidak ada suara ~12s. Tombol Kirim/Tutup manual tetap ada; avatar berdenyut mengikuti level mic. (`Chat.jsx` CallMode)
- **Video Seedance Permanen**: hasil Seedance diunduh lalu disimpan ke Emergent Object Storage (`storage.py`, prefix `aivora/videos/{user_id}/{task_id}.mp4`). Task menyimpan `video_path`; disajikan via `GET /api/files/{path}` dengan auth query-param (`?auth=<jwt>`, cek segmen user-id). TaskDetail memutar dari URL permanen. init storage saat startup.
- **Suara di Onboarding/Pembuatan Persona**: langkah review CreatePersona punya pemilih "Suara Persona (TTS)" dengan 9 opsi + tombol **Dengar contoh** (preview TTS). Voice ikut tersimpan di POST /api/personas.
- **UI Responsif**: Chat punya drawer daftar percakapan di mobile (tombol `mobile-conv-btn` → `mobile-conv-drawer`), header chat truncate + tombol Panggil ikon-saja di layar kecil. Testid drawer dinamai terpisah (`new-chat-btn-mobile`, `conv-m-*`).
- Tested: testing agent iteration_2 — backend /api/files auth 4/4, frontend 3/3 (voice picker, mobile drawer, call overlay). VAD mic tidak diuji otomatis (tanpa mikrofon di headless).

## Update 2026-06 (e) — Ruang Video Call ala Zoom (grup/meeting) + moderator notulen
- **VideoRoom** (`frontend/src/components/VideoRoom.jsx`): overlay full-screen gaya Zoom (tema gelap imersif) untuk percakapan **grup/meeting**. Grid tile: **Anda** + tiap persona + **Moderator**. Tile "hidup": potret, cincin berdenyut + waveform saat bicara, status mendengar/berpikir/bicara. Tombol buka: `video-call-btn` di header chat (tampil bila type != private).
- **Hands-free suara**: pakai VAD (deteksi diam) — Anda bicara → auto-kirim saat berhenti → tiap persona menjawab bergiliran lewat TTS suara masing-masing (hanya satu bicara pada satu waktu via playback queue). Caption langsung di bawah. Kontrol: mute mic, kirim sekarang, toggle caption, keluar. (Alur mic tak bisa diuji otomatis — tanpa mikrofon di headless.)
- **Moderator & Notulen**: saat tekan **"Akhiri & Simpan Notulen"** (`vr-end-save`) → `POST /api/conversations/{cid}/summary` membuat ringkasan Moderator (poin, kesepakatan, action items), menyimpannya sebagai pesan + **task `meeting_notes` di Ruang Kerja**, lalu Moderator "membacakan" ringkasan (TTS suara onyx, dibatasi 25s agar tak menggantung) dan ruang ditutup. Endpoint ditolak (400) untuk percakapan privat.
- **Flag moderator per-giliran**: `POST /conversations/{cid}/send` menerima `moderator:false` (dipakai VideoRoom) agar moderator TIDAK merangkum tiap giliran; ringkasan hanya di akhir. Perilaku chat meeting teks lama tetap (default `moderator:true`).
- `streamChatWithAtt` dipindah ke `lib/api.js` (mendukung extra body) untuk dipakai Chat + VideoRoom tanpa circular import.
- Tested: testing agent iteration_3 — backend 4/4 (summary membuat meeting_notes, flag moderator true/false, 400 privat), frontend 100% (tombol, overlay, semua tile + kontrol, caption toggle, end+save → task notulen muncul di Ruang Kerja). Fix pasca-tes: timeout 25s pada pemutaran TTS akhir + guard privat + label tile fallback.

## Update 2026-06 (f) — Moderator Aktif + Reaksi Hidup di Video Room
- **Moderator Aktif** (`chat.py`): di alur Video Room (`send` dengan `moderator:false`) pada percakapan **meeting**, Moderator kini **menengahi di tengah rapat** setiap giliran genap (turn 2,4,...) dengan 1-2 kalimat singkat (mengakui poin, bertanya lanjutan, atau mengundang peserta). Di-stream sebagai event `is_moderator:true` + `moderator_kind:"interject"`, suara `onyx`. **Tidak** membuat task notulen (hanya ringkasan akhir yang menyimpan notulen). Perilaku meeting teks lama (`moderator:true`) tetap.
- **Reaksi Hidup** (`VideoRoom.jsx`): tile asisten/moderator memunculkan **emoji mengambang** saat mulai bicara (👍/💡/😂/🤔/🎉/🙏 berdasarkan kata kunci isi jawaban, fallback acak), animasi `vr-reaction` naik & memudar. VideoRoom kini juga memutar interjeksi Moderator di antrean suara (Moderator ikut "bicara" di tengah rapat). Label tile kosong → fallback "Asisten".
- Tested: testing agent iteration_4 — backend 5/5 (turn ganjil tanpa moderator, turn genap interject + tanpa task, summary tetap buat 1 notulen & guard privat 400, legacy moderator:true tetap), frontend 100% (Video Room render + semua kontrol). Reaksi & loop mikrofon tidak bisa diuji headless (markup terverifikasi).
- **Catatan**: "Coba Rapat Suara" (hands-free dengan mikrofon nyata) harus diuji langsung oleh user — tidak bisa dijalankan di browser otomatis tanpa mikrofon.

## Update 2026-06 (g) — Multi-user workspace, roles (admin/user), multi-human meetings, real-time WebSocket
- **Role & Workspace**: setiap user punya `role` (admin/user) + `owner_id` (pemilik workspace). `demo@aivora.ai` otomatis dipromosikan jadi **Administrator** saat startup (`migrate_workspace`). Admin = pemilik workspace; semua persona & dompet kredit dibagikan.
- **Admin buat user**: panel **Tim** (`/team`, admin-only) + endpoint `POST /api/admin/users`, `GET /api/admin/workspace-users`, `DELETE /api/admin/users/{id}`. User baru `role:user`, `owner_id=admin`, kredit 0 (pakai dompet admin).
- **Shared wallet**: `record_usage` kini memotong kredit dari **pemilik workspace (admin)**, apa pun yang dilakukan user biasa. `wallet` & `topup` scoped ke owner; `topup` admin-only.
- **Persona shared**: list/get persona pakai `workspace_id` (user biasa melihat & memakai persona admin). Create/edit/portrait/duplicate/delete persona = **admin-only** (403 untuk user biasa).
- **Multi-human meeting**: conversation punya `workspace_id` + `participants[]`. Admin membuat meeting dengan `participant_ids` atau mengundang via `POST /api/conversations/{cid}/participants`. Akses via `_can_access` (owner / participant / admin workspace). Pesan manusia ditandai `sender_user_id`+`sender_name`; AI melihat nama tiap manusia.
- **Real-time WebSocket**: `GET /api/ws/{cid}?token=` (server.py + `realtime.py` ConnectionManager). Broadcast `{type:'message'|'participants'}` ke semua peserta; frontend (`openConvSocket` di api.js) refetch pesan saat ada event. Tolak 4401 (token invalid) / 4403 (tanpa akses). Teruji end-to-end (Budi menerima pesan admin + jawaban AI live).
- **Frontend gating**: user biasa — nav tanpa Agen AI/Kredit/Tim/Admin, tanpa badge kredit & kartu Upgrade, Home tanpa kartu kredit; route /personas,/wallet,/team,/admin redirect ke /home. Admin melihat semua + halaman **Tim** (buat/hapus user) + tombol **Undang** di meeting.
- Tested: testing agent iteration_7 — backend 20/20, frontend 100% (gating, redirect, CRUD tim, shared wallet, WS auth + broadcast). Tanpa bug.

## Update 2026-06 (h) — Panggilan pengingat bersuara, kuota kredit harian, tautan undangan sekali klik
- **Bug fix — Panggilan Pengingat bersuara**: saat panggilan pengingat diterima, asisten kini **berbicara** mengingatkan (TTS suara persona, nada ramah, bahasa sesuai setelan) lalu **lanjut jadi panggilan suara normal** (membuka VideoRoom isPrivate hands-free). `reminders.respond(accept)` mengembalikan `message` + `persona{voice}` + `conversation`, dan menyimpan pesan pembuka di percakapan. (`IncomingCall.jsx`)
- **Kuota kredit harian per anggota**: admin set `daily_credit_limit` tiap user biasa di halaman **Tim** (PATCH `/api/admin/users/{id}`). Jika pemakaian hari ini (UTC) ≥ limit → kirim AI diblokir **402** sampai reset tengah malam. `workspace-users` menampilkan `today_usage` + limit. 0 = tanpa batas. Admin tak pernah diblokir. (`llm.user_today_usage/quota_exceeded`, `chat.send_message`)
- **Tautan undangan sekali klik**: admin buat tautan meeting (`POST /conversations/{cid}/invite-link` → `/join/{token}`). Halaman publik `/join/:token`: user lama (workspace sama) langsung **Gabung**; orang baru **daftar instan** (akun user biasa dibuat di workspace lalu masuk meeting). Endpoint: `GET /api/invites/{token}`, `/join`, `/register`. Tombol salin di modal Undang chat.
- **Kamera di meeting**: DITUNDA atas permintaan user (butuh WebRTC + TURN).
- Tested: testing agent iteration_8 — backend 12/12, frontend 100% core. Fix pasca-tes: daftar percakapan refetch saat auth berubah (sidebar langsung muncul setelah guest join).

## Update 2026-06 (i) — Rebranding Oryntix, tema dashboard baru, meeting langsung, barge-in, moderator hanya saat buntu, code review + security audit
- **Rebranding → Oryntix** ("Intelligence, Orchestrated."): aset di `frontend/public/brand/` (mark.png/mark-512.png, logo-dark.webp, logo-white.webp), favicon, title. `Logo.jsx` ekspor `Logo`, `Mark`, `LogoFull`, `BRAND_*`, `TAGLINE`. Semua teks "Aivora" → "Oryntix" (kunci localStorage `aivora_*`, class `aivora-card`, prefix storage `aivora/` sengaja TIDAK diubah).
- **Tema UI** mengikuti referensi ui-dashboard: sidebar navy gelap (`.sidebar-dark`, `.nav-item`), konten terang, base font 14px (desktop)/15px (mobile), `.btn-primary`/`.btn-soft`. `AppLayout.jsx` (sidebar Workspace Usage + user, header search + New). `Home.jsx` redesign: hero "Turn your ideas into real results with AI.", 4 stat card, Recent Activity, Your AI Agents, Quick Actions, kalender/Upcoming/promo/Popular Tools. Login page pakai mark ribbon.
- **Chat & Meeting**: tombol **Chat Baru** (1+ asisten → private/group teks) dan **Meeting Baru** (1+ asisten → type `meeting`, ruang meeting langsung terbuka via router state `openMeeting`). Toggle Grup/Meeting dihapus. Semua kata "Video Call" → "Meeting" ("Masuk Meeting"). Backend `create_conv` kini mengizinkan meeting dengan 1 persona. Tombol **Notulen** (`save-notes-btn`) di header grup/meeting → `/summary`.
- **Suara humanis & bahasa**: `send` menerima `voice_mode:true` → prompt `VOICE_STYLE` (kalimat lisan pendek, hangat, tanpa markdown) + `interrupted:true`; bahasa tetap dari `settings.conversation_language` (STT+LLM).
- **Barge-in (menyela) di VideoRoom**: mic persisten + analyser; saat asisten bicara/berpikir, suara user yang cukup keras ≥300ms → audio berhenti, antrean dibersihkan, SSE+TTS fetch di-abort (AbortController), giliran berpindah ke user (pill "Anda menyela"). Recorder di-restart tiap transisi agar rekaman hanya berisi ucapan user. Blob URL audio di-revoke; error 402/jaringan ditampilkan sebagai toast+caption.
- **Moderator hanya saat buntu**: per giliran meeting (teks maupun ruang meeting) Moderator cuma menyela bila `_is_stuck()` (cek LLM YES/NO) pada user_turns ≥ 2. Hening 20 dtk di ruang meeting → `POST /conversations/{cid}/nudge` (Moderator untuk meeting 2+ asisten, persona untuk privat/1 asisten). Notulen lengkap hanya via `/summary` (kini boleh pembuat/peserta/admin).
- **Security audit fixes**: tautan undangan kedaluwarsa 7 hari (`invite_expires_at`, token 32 char), user dari undangan default `daily_credit_limit=200`; `invite_token` tidak lagi dikembalikan di payload percakapan; persona_ids divalidasi milik workspace; `/api/files` tolak `..`/prefix salah; pesan error voice/portrait tidak bocorkan exception; batas lampiran 8MB; `Markdown.jsx` hanya izinkan link http/https + escape kutip.
- Tested: iteration_9 (backend 13/13, FE 100%) & iteration_10 regression (backend 11/11, FE 100%). Barge-in/VAD butuh uji manual dengan mikrofon.
- Catatan audit tersisa (P3, belum dikerjakan): rate limiting per-user pada endpoint pemakan kredit, pin CORS origins eksplisit untuk produksi.

## Update 2026-06 (j) — Mode Realtime (speech-to-speech ala ChatGPT Voice) + panggilan pengingat bersuara
- **Realtime voice call** (`backend/realtime_voice.py`, `frontend/src/components/RealtimeCall.jsx`): OpenAI Realtime API **gpt-realtime** via WebRTC, negosiasi SDP lewat backend (`POST /api/realtime/calls/{id}/negotiate` → `https://api.openai.com/v1/realtime/calls`, key tidak pernah ke browser). BYOK: `OPENAI_API_KEY` + `OPENAI_REALTIME_MODEL` di `backend/.env` (bukan Universal Key). Server VAD `interrupt_response:true` (menyela native), transkripsi `gpt-4o-mini-transcribe` bahasa = `settings.conversation_language`. Instruksi sesi = `_persona_system(voice_mode=True)` + riwayat 12 pesan. Asisten **bicara duluan** (sapaan singkat / pengingat). Transkrip user & asisten disimpan ke `messages` (`via:"realtime"`) via `/transcript`; flush saat hangup.
- **Metering**: `realtime_calls` collection; `tick` tiap 60 dtk + `end` → tagih per menit berjalan (ceil) dari dompet admin, hormati kuota harian; 402 → panggilan ditutup. Tarif dikonfigurasi admin (`GET/PUT /api/admin/realtime-pricing`, kartu di Admin → Pricing): kredit/menit = ceil(USD/menit × (1+margin 30%) × (1+PPN 11%) × kurs / IDR per kredit) → default 75 kredit/menit. `GET /api/realtime/status` → `{enabled, model, credits_per_min}`.
- **Pemakaian**: chat privat → tombol "Panggil · Realtime" membuka RealtimeCall (fallback VideoRoom bila key tidak ada). Meeting/grup multi-asisten tetap memakai VideoRoom (Realtime hanya satu suara).
- **Panggilan pengingat**: reminder tanpa persona kini **fallback ke persona pertama workspace** (`_reminder_persona`) sehingga selalu bersuara. `respond {accept, realtime:true}` melewati TTS dan mengembalikan `opening`; RealtimeCall dibuka dan asisten langsung **mengucapkan pengingat dengan ramah**, lalu lanjut sebagai panggilan biasa. Fallback non-realtime: TTS seperti sebelumnya.
- Fix: guard React StrictMode (runId) agar tidak membuat 2 panggilan; sweep panggilan basi (>2 mnt) saat panggilan baru.
- Tested: iteration_11 — backend 14/14, FE 100% (negosiasi WebRTC nyata berhasil di headless; sapaan Indonesia muncul <2 dtk; billing 75 kredit terpotong). Fix pasca-tes: transkrip di-flush saat hangup — diverifikasi ulang.
- **MOCK/LIMITASI**: biaya provider default 0.25 USD/menit adalah estimasi — admin wajib sesuaikan di Pricing.
- (P3) Rate limiting endpoint LLM/TTS/STT; CORS pin untuk produksi.
- (Backlog P1) Payment gateway nyata; (P2) kamera WebRTC antar-manusia (ditunda).

## Update 2026-06 (k) — Realtime Meeting multi-agen, rate limiting, uji panggilan
- **RealtimeMeeting** (`components/RealtimeMeeting.jsx`, `lib/realtimeSession.js`): meeting/grup dengan ≥2 agen kini memakai **satu sesi Realtime per agen** (suara berbeda tiap agen, `VOICE_MAP`). Backend `POST /api/realtime/calls` mengembalikan `sessions[]` (`multi`, `primary`, `credits_per_min_total` = N × tarif). Sesi non-primer: `create_response:false`, tanpa transkripsi (hemat); hanya sesi primer mentranskrip user. Orkestrasi di browser: setelah transkrip user selesai → urutan penjawab (agen yang disebut namanya duluan/satu-satunya; selain itu rotasi) → `response.create` bergiliran; ucapan agen disuntikkan ke sesi lain sebagai `[Nama]: ...`; giliran berikutnya dimulai saat `output_audio_buffer.stopped` (fallback 15 dtk). Menyela: `speech_started` di sesi primer → cancel agen aktif, kosongkan antrean. Akhiri & Simpan Notulen → `/summary`. Fallback VideoRoom bila Realtime nonaktif.
- **Rate limiting per pengguna** (`backend/ratelimit.py`, sliding window in-process, cache 30 dtk): chat send/nudge 20/mnt, STT/TTS 30/mnt, buat panggilan realtime 20/jam, generate profil/potret 30/jam, durasi maks panggilan 60 mnt (tick → 402). Admin `GET/PUT /api/admin/rate-limits` + kartu "Batas Pemakaian per Pengguna" di Admin → Pricing. 429 → toast (axios interceptor + streamSSE `err.detail`).
- Fix: transkrip agen di-flush saat keluar/hangup (RealtimeCall & RealtimeMeeting) + fallback `response.done`; fallback kembali ke "mendengarkan" bila VAD terpicu tanpa transkrip (7 dtk).
- Tested: iteration_12 — backend 6/6, FE 100% (meeting 2 agen tersambung nyata, Rio menyapa dalam Bahasa Indonesia; billing 2 sesi). **Belum bisa diuji otomatis**: kualitas sela & giliran multi-agen dengan ucapan nyata (butuh mikrofon user).

## Update 2026-06 (l) — Moderator bersuara di Realtime Meeting, Laporan Pemakaian
- **Moderator Realtime** (TTS, bukan sesi Realtime tambahan → hemat): `POST /api/conversations/{cid}/moderate {reason: silence|stuck}` → `_moderator_text()` (dipakai juga oleh `_moderator_interject`) → `{content|null, voice:"onyx"}`. `stuck` hanya bila user_turns ≥ 2 dan `_is_stuck()` YES; `silence` bila user_turns ≥ 1. Di `RealtimeMeeting.jsx`: tile Moderator; setelah semua agen selesai menjawab (giliran ≥ 2) → cek `stuck`; hening 20 dtk → `silence` (sekali per periode hening); teks Moderator disuntikkan ke semua sesi agen sebagai `[Moderator]: ...`; user bicara → audio Moderator dihentikan.
- **Laporan Pemakaian** (`GET /api/admin/usage-report?days=7|30|90`, `components/UsageReport.jsx` di halaman Team): total, rata-rata/hari, aktivitas, paling boros; grafik per anggota (bar, atribusi `meta.actor_id`), per fitur (donut + legenda label Indonesia `FEATURE_LABELS`), tren harian (area). Recharts.
- Tested: iteration_13 — backend 10/10, FE 100%. Uji suara nyata (sela, sebut nama, Moderator menyela) tetap perlu mikrofon user.

## Update 2026-06 (m) — Code quality fixes (laporan code review)
- Variabel dalam `try` diinisialisasi/`raise ... from exc` (voice.py, personas.py, files.py, chat.py `_is_stuck`).
- Kredensial uji di `backend/tests/*.py` dibaca dari env `TEST_ADMIN_PASSWORD` / `TEST_BUDI_PASSWORD` (default tetap untuk lokal).
- Refactor kompleksitas: `chat.py` → `_load_ai_conv`, `_mentioned`, `_persona_reply` (generator SSE dipakai send & nudge), `_finish_stream`, `_sse`, `_conv_title`, `_resolve_participants`; `realtime_voice.py` → `_call_personas`, `_ensure_affordable`, `_close_stale_calls`, `_session_instructions`; `admin.py` → `_aggregate_usage`. `agents._orchestrate` sengaja tidak disentuh (risiko regresi, tidak ada bug).
- Temuan `is None` adalah idiom Python yang benar (false positive) — tidak diubah.
- Regresi: pytest iter10 + iter13 (21 passed) + curl send/nudge/moderate/realtime/usage-report OK.

## Update 2026-06 (n) — Pendaftar mandiri = admin workspace-nya sendiri
- `POST /api/auth/register` kini membuat akun dengan `role:"admin"`, `owner_id = id` (pemilik workspace sendiri, 500 kredit awal). Anggota yang dibuat admin (Team) atau lewat tautan undangan tetap `role:"user"`.
- `migrate_workspace()` saat startup: semua akun dengan `owner_id == id` dipromosikan ke admin (idempoten; berlaku juga di produksi).
- Verified via curl: register → role admin, akses /api/admin/workspace-users 200; budi tetap user.

## Update 2026-06 (o) — Paket percobaan 7 hari, mesin tarif platform (margin 30%), pemisahan Platform Admin
- **Trial**: register → `plan:"trial"`, kredit 700, `daily_credit_limit` 100, `trial_ends_at` +7 hari (konfigurasi `config.trial_config` via `PUT /api/admin/trial`). `quota_exceeded` berlaku untuk owner trial (kuota harian; lewat `trial_ends_at` → 402 "Masa percobaan ... berakhir"). Topup (simulasi) → `plan:"paid"`, limit 0. `TrialBanner` di Home & Kredit.
- **Mesin tarif** (`backend/pricing.py`): satu config `platform_pricing` (margin 30%, PPN 11%, kurs, nilai kredit, biaya provider USD per fitur). `RATES` (cache 30 dtk, refresh paksa saat PUT) dipakai `text_credits`, `rate("image"|"profile"|"stt"|"tts")`, dan realtime `credits_per_min`. Default dikalibrasi ke tarif lama (2/1k char, 25, 8, 5, 4, 75). Admin: `GET/PUT /api/admin/pricing`, kartu "Tarif & Margin Platform".
- **Platform Admin** = `ADMIN_EMAIL` (admin@aivora.ai): `require_platform_admin` untuk overview/users/tasks/pricing/trial/realtime-pricing/rate-limits; `public_user.is_platform_admin`; nav/route `/admin` hanya untuk platform admin. Pemilik workspace lain tetap Team/Kredit/usage-report (scoped).
- Email verification: **ditunda** atas permintaan user (butuh penyedia email).
- Tested: iteration_14 — backend 10/10, FE 100%.

## Update 2026-06 (p) — Code review deployed app: perbaikan keamanan
- **HIGH fixed**: `GET /api/admin/personas` kini di-scope ke workspace pemanggil (sebelumnya bocor lintas-tenant).
- Anggota (role user) dari workspace yang trial-nya kedaluwarsa ikut diblokir (`quota_exceeded` cek plan pemilik).
- Throttle login: 10 percobaan / 5 menit per IP & per akun → 429 (`ratelimit.login_allowed`); `_hits` dipangkas berkala.
- `_finish_stream` melaporkan saldo dompet workspace (bukan saldo pribadi anggota).
- Catatan: cache tarif & rate limit per-proses (deploy 1 worker) — bila scale-out perlu Redis.
- Tested: iteration_15 — backend 11/11, FE 100%.

## Update 2026-06 (q) — Diskusi fitur lanjutan (DITUNDA oleh user)
- User bertanya: avatar interaktif ala Runway Characters, vision (webcam/berbagi layar), integrasi Zoom/Meet/Teams. Agen memaparkan opsi (vision via image input gpt-realtime; Zoom/Meet/Teams via Recall.ai/Meeting BaaS atau SDK resmi, atau alternatif "Oryntix sebagai host" dengan WebRTC). User memutuskan **tunda dulu semua rencana**. Tidak ada perubahan kode.

## Backlog (ditunda)
- Vision: snapshot webcam/layar → sesi Realtime / chat teks (image input), tarif per gambar.
- Zoom/Meet/Teams: bot meeting (Recall.ai / Meeting BaaS) atau kamera+share screen WebRTC di ruang meeting Oryntix.
- Avatar interaktif (Runway LiveKit / HeyGen-Simli / animasi 2.5D).

## Update 2026-06 (r) — Panel Chat Meeting + mic ala ChatGPT Voice (noise gate adaptif, RNNoise, semantic VAD)
- **Panel Chat Meeting** (`components/MeetingChatPanel.jsx`) di RealtimeMeeting, RealtimeCall, VideoRoom: panel kanan 360px (desktop, default terbuka) / bottom sheet 70vh (mobile, default tertutup); tombol 💬 dengan badge belum dibaca; preferensi di localStorage `aivora_meeting_chat_open`. Isi panel **hanya pesan teks/data** (`via:"meeting_chat"`), transkrip suara tetap di caption. User mengetik → asisten menjawab **hanya teks** (markdown tabel/kode/tautan; URL .mp4/.webm/gambar di-embed; `media[]` didukung untuk tool mendatang). Backend: `MsgIn.channel="meeting_chat"` → satu persona menjawab (atau yang di-@mention), tanpa Moderator, prompt `MEETING_CHAT_STYLE`; pesan tersimpan dengan `via`. Tanya-jawab panel disuntikkan ke sesi Realtime sebagai konteks `[Chat panel] ...`. `Markdown.jsx` kini merender tabel pipe.
- **Mic**: `lib/micPipeline.js` — mic → RNNoise (WASM worklet, `public/audio/rnnoise-worklet.js`+wasm, paket `@sapphi-red/web-noise-suppressor`) → **noise gate adaptif** (`public/audio/gate-worklet.js`: noise floor adaptif, margin 18/12/6 dB untuk Rendah/Sedang/Tinggi, attack dengan look-ahead, hold) → MediaStream yang dikirim ke OpenAI/recorder. Suara orang jauh di bawah ambang → hening. Backend `vad_config()`: **semantic_vad** (eagerness = sensitivitas, via `?sensitivity=` atau `settings.mic_sensitivity`), `interrupt_response:false` — browser **mengonfirmasi sela** hanya bila gate terbuka ≥300 ms (`BARGE_CONFIRM_MS`) lalu `response.cancel`+`output_audio_buffer.clear`. Ubah sensitivitas saat panggilan → `session.update` live.
- **Menu pengaturan mic** (`components/MicSettingsMenu.jsx`): ikon ⚙ di bar kontrol → popover: Sensitivitas (Rendah/Sedang/Tinggi), toggle Peredam bising (AI), meter level + garis ambang. Persist: localStorage `aivora_mic_prefs` + `PUT /api/auth/settings {mic_sensitivity, noise_suppression}`.
- Tested: iteration_16 — backend 11/11, FE 100% (desktop, mobile, RealtimeCall, regresi). **Kualitas gate/RNNoise dengan suara nyata perlu uji manual user.**
- Backlog: Tahap 2 tool-use & routing (Seedance video/gambar/dokumen dari chat meeting, model per topik) — hasil masuk `media[]` panel.

## Update 2026-06 (s) — Tool-use (gambar & dokumen), routing model, 3 layout meeting, memori lampiran, nada sanguinis
- **Tool-use** (`backend/tools.py`, `chat._tool_turn`): deteksi niat (regex `wants_tool` + planner LLM JSON `plan_tool`) di `POST /conversations/{cid}/send` (chat biasa & panel meeting). **Gambar** (Gemini image, `rate("image")`=25 ≥ `confirm_threshold` 20) → pesan asisten dengan `pending_tool{kind,prompt,credits}` → UI `ToolRequestCard` → `POST /conversations/{cid}/messages/{mid}/run-tool` (buat, simpan ke object storage `aivora/images/{uid}/..`, `media:[{type:image,path}]`) atau `/cancel-tool`. **Dokumen** → langsung dibuat: LLM (model hasil routing) menulis markdown → `.docx` (python-docx) + `.pdf` (fpdf2, LiberationSans) + `.md` di `aivora/docs/{uid}/{id}/` → `media[]` 3 file; SSE event `status` saat proses. `GET /api/files/{path}` kini boleh diakses seluruh anggota workspace (`_same_workspace`). Usage: `image_generation`, `document_generation`.
- **Routing model** (`tools.route_model`): IT/coding (regex) → `it_model` (Claude Sonnet), riset panjang (regex / teks+lampiran >3500 char) → `research_model` (Gemini Pro), lainnya model persona. Config platform admin `GET/PUT /api/admin/model-routing` {enabled, it_model, research_model, confirm_threshold} + kartu `ModelRoutingCard` di Admin → Pricing. Toggle workspace `settings.smart_routing` (`SmartRoutingToggle` di halaman Tim, `PUT /auth/settings`). Pesan asisten menyimpan `model_key/model_label/routed`; UI badge "via Claude Sonnet" (`ModelBadge`).
- **Layout meeting** (`components/MeetingShell.jsx`): tombol `layout-btn` → popover 3 mode: *Peserta utama* (tiles + panel kanan), *Chat utama* (chat memenuhi stage, `ParticipantRail` kolom kanan 280px dengan status/caption; mobile strip horizontal), *Sejajar* (50:50). Persist localStorage `aivora_meeting_layout`. Dipakai RealtimeMeeting, RealtimeCall, VideoRoom; `MeetingChatPanel` punya `variant` side|main.
- **Memori lampiran**: `attachment_text` (≤4000 char) disimpan di pesan user dan ikut `_history_text` (≤1500/pesan) → pertanyaan lanjutan tentang lampiran terjawab; nama berkas buatan asisten juga masuk riwayat.
- **Nada sanguinis**: `SANGUINE_TONE` di `_persona_system` (hangat, ceria, humor ringan, tetap akurat).
- `MessageExtras.jsx`: `MediaList` (gambar/video/file chips Word·PDF·Markdown), `ToolRequestCard`, `ModelBadge`, `fileUrl`. Chat.jsx & panel meeting merender ketiganya + status streaming.
- Deps: `python-docx`, `fpdf2` (requirements.txt).
- Tested: iteration_17 — backend 13/13, FE 100% (layout 3 mode + persist, tool gambar konfirmasi/batal/jalankan, dokumen 3 file, routing badge, admin card, toggle workspace, memori lampiran).

## Update 2026-06 (t) — Code review fixes (kualitas kode)
- `chat.py`: `send_message` dipecah (`_store_user_message`, `_pick_responders`, `_reply_extra`, `_collect`, `_moderator_if_stuck`); `_persona_reply` kini menerima dataclass **`ReplyCtx`** (`meta`, `sse()`), `_prepare_ctx`; `_tool_turn` → `_image_turn`/`_document_turn`/`_emit_final`; `_process_attachments` → `_attachment_context` + `_pdf_text`. `nudge` memakai `ReplyCtx`.
- `agents._orchestrate` → `_plan_steps`, `_run_step`, `_merge_outputs`, `_attach_video`. `llm.quota_exceeded` → `_workspace_owner`, `_trial_expired`, `_daily_limit_hit`. `files.serve_file` → `_bearer`, `_path_parts`. `reminders.respond` → `_reminder_message`, `_private_conv`, `_store_opening`.
- `tools.route_model`: `.get("smart_routing", True)` (hilangkan `is False`); `plan_tool`/tool turns inisialisasi variabel defensif; pernyataan `;` dipisah (tools.py, video_gen.py). `models.list_models() -> dict`.
- Tests: `assert x is True/False` → `assert x` / `assert not (x)`; variabel tak terpakai & import ganda dibersihkan; `ruff --select E4,E7,E9,F` bersih untuk backend + tests.
- Regresi: pytest iter16 11/11, iter17 13/13; curl nudge & reminder respond OK. (iter15 gagal 3 hanya karena throttle login 429 dari tes brute-force di file yang sama — bukan regresi kode.)

## Update 2026-06 (u) — Batch 7 item + turn-taking natural (iteration_18 lulus: BE 14/14, FE 100%)
- **Pagination**: `GET /conversations?limit&offset` (sidebar 20/muat), `GET /conversations/{cid}/messages?limit=50&before=&archived=` → `{messages, has_more, archived_count, long_chat}` (scroll-ke-atas memuat lama, `applyPage/loadOlder` di Chat.jsx); Wallet/Workspace/Reminders `LoadMore` 20/klik (client-side).
- **Rangkuman otomatis & arsip**: `_long_chat` (≥40 pesan / ≥15k char sejak snooze) → SSE `summary_request` + `long_chat` → `SummaryPrompt`; `POST /compact` (LLM merge ke `conversation.memory_summary`, pesan live → `archived:true`, catatan `is_summary`), `POST /summary-later`; arsip hanya via `ArchiveModal` (tidak masuk memori asisten). Akhir meeting: `/summary` lalu `/compact`.
- **Format notulen**: `settings.notulen_fields` (owner; `NotulenFormatCard` di Profil), `POST /notulen-check` → `useNotulenGate` dialog *Lanjutkan pembahasan / Tetap akhiri* di RealtimeMeeting & VideoRoom; `/summary` memakai heading sesuai kolom.
- **Suara**: `VOICES` 13 (10 Realtime: marin, cedar, …) + `VOICE_INFO`, fallback TTS marin/cedar; form persona tag "Realtime". **Moderator membuka meeting** (`MODERATOR_OPENING`), `NO_REPEAT`/`NO_REPEAT_TEXT`.
- **Turn-taking natural**: `SPEAKING_STYLE` (tenang, jelas, tidak terburu-buru, mengalah halus); eagerness semantic_vad dipetakan low/low/medium; `BARGE_CONFIRM_MS=700`; default sensitivitas **Rendah**.
- **Mesin harga**: `usd_per_credit=0.001` (1.000 kredit = $1), `usd_to_credits()`; Realtime ditagih per respons dari `response.usage` (`POST /realtime/calls/{id}/usage`, tarif rt_*_usd_1m) + biaya koneksi $0.02/mnt; `video_per_sec`; admin PlatformPricingCards field baru; DB config diperbarui (provider_usd_per_min 0.02).
- **UI**: `ErrorBoundary` global (anti layar putih), PDF dideteksi dari ekstensi + batas 8MB, sidebar sticky `h-screen` (Workspace Usage & Logout selalu tampil), login Microsoft & "Lihat Video" dihapus, tombol Google (placeholder menunggu Client ID/Secret).
- Bug "layar putih upload PDF" **tidak tereproduksi** di preview (PDF 16KB & 3MB OK) — ErrorBoundary + validasi ditambahkan; minta user cek ulang di versi deploy terbaru.

## Update 2026-06 (v) — Hemat token Realtime + meeting dipandu Moderator (belum diuji suara nyata)
- **Konteks kompak** (`_voice_context`): ringkasan ≤600 char + 6 pesan terakhir ≤1000 char (sebelumnya 12 pesan/3000 char); instruksi statis di depan, konteks di akhir (prefix cache stabil).
- **Pemangkasan konteks klien** (`ContextPruner` di `realtimeSession.js`): item audio lama (≥14 item, sisakan 6) dihapus (`conversation.item.delete`) dan diganti 1 item teks ringkas di `previous_item_id:"root"`; dipanggil antar giliran (`response.done` di RealtimeCall, saat antrian kosong di RealtimeMeeting).
- **Meeting Moderator** (`realtime_voice.py`): persona pertama / `conversation.moderator_persona_id` = moderator (`role: moderator`, mic + transkripsi + tool `delegate` enum nama panelis); panelis (`role: panelist`) **tanpa audio masuk** (`turn_detection: null`, WebRTC `recvonly`), menerima ucapan user & agen lain sebagai teks `[Nama]: ...`, bicara hanya saat disebut namanya atau didelegasikan. Alur: moderator `response.function_call_arguments.done` → panelis menjawab → `function_call_output` ke moderator → moderator melengkapi 1-2 kalimat. `PATCH /conversations/{cid}/moderator` + picker di header meeting (menyambung ulang).
- **Hanya bicara saat diminta**: moderator TTS terpisah, `/moderate` silence 20 dtk & "stuck" dihapus dari RealtimeMeeting (endpoint masih ada untuk VideoRoom lama). Bug `reportUsage(ev)` sebelum parse di RealtimeSession diperbaiki (usage meeting kini tertagih).
- Spesialisasi panel dari `get_routing()` (it_model → "THE IT/CODING EXPERT", research_model → "THE RESEARCH EXPERT") + `PROVIDER_HINT`.


## Update 2026-06 (w) — Verifikasi email, undangan tim via email, multi-workspace (iteration_19 lulus: BE 27/27, FE 7/7)
- **Mailer** (`mailer.py`, aiosmtplib): SMTP Hostinger port 465 (env `SMTP_HOST/PORT/USER/PASSWORD/FROM/FROM_NAME`); template verifikasi & undangan (HTML+teks). `EMAIL_DEBUG_LINKS=true` (preview saja) → respons API menyertakan `debug_link`. Tautan memakai `APP_URL` env → `app_url` dari body (window.location.origin) → header Origin.
- **Verifikasi email** (`auth.py`): register → `verified:false`, token SHA-256 di `email_tokens`, respons `{pending_verification, mail_sent, debug_link?}` tanpa token; login belum verifikasi → 403 `{code:"unverified"}`; `POST /auth/resend-verification`; `GET /auth/verify-email?token=` → login otomatis. Akun lama otomatis `verified:true` (migrasi).
- **Multi-workspace**: `users.owner_id` = workspace aktif; koleksi `workspace_members {workspace_id,user_id,status:joined}` (migrasi anggota lama); `member_ids()/is_member()/role_for()`; `GET /auth/workspaces`, `POST /auth/switch-workspace`; role dihitung dinamis di `current_user`. Semua query anggota (`/admin/workspace-users`, usage report, peserta meeting, join link) memakai membership.
- **Undangan tim** (`team.py`, koleksi `workspace_invites` status pending/joined/rejected/removed): `POST/GET /team/invites`, `/team/invites/{id}/resend`, `DELETE`; publik `GET /team/invites/by-token/{t}`, `POST .../accept` (user baru buat password; user lama harus login dengan email yang sama), `POST .../reject`; in-app `GET /team/my-invites`, `POST /team/my-invites/{id}/accept|reject`; `DELETE /team/members/{uid}` (keluarkan, akun tetap). Undangan tidak kedaluwarsa.
- **Frontend**: `Auth.jsx` layar "Cek email Anda" + peringatan unverified & kirim ulang; `VerifyEmail.jsx` (/verify-email); `InvitePage.jsx` (/invite/:token); `Team.jsx` → form "Undang via Email", daftar undangan berstatus (kirim ulang/batalkan), keluarkan anggota; `WorkspaceSwitcher.jsx` di sidebar (pilih workspace + kartu undangan Bergabung/Tolak, polling 60 dtk); `AuthContext.applyAuth/switchWorkspace`.


## Backlog batch berikut
- Google OAuth sendiri (Client ID/Secret dari user) → login Google.
- Produksi: set secret SMTP_* seperti preview; JANGAN set `EMAIL_DEBUG_LINKS=true` di produksi (tautan verifikasi akan bocor di respons API).

- Tugas terjadwal dari meeting/chat → Ruang Kerja (tawaran "bahas satu per satu / terima beres"), buat meeting dari Ruang Kerja, revisi hasil di meeting, unduh Word di Ruang Kerja, menu Kalender.

## Next tasks
- Uji manual Mode Realtime (sela, giliran multi-agen) & panggilan pengingat dengan mikrofon nyata (user).
- Verifikasi email saat daftar (ditunda; perlu Resend/SendGrid key).
- Re-publish agar trial/platform-admin aktif di produksi; set ADMIN_EMAIL/ADMIN_PASSWORD produksi.
- (P3) CORS pin untuk produksi; rate limit lintas-instance (Redis) bila dideploy multi-replica.
- (Backlog P1) Payment gateway nyata; (P2) kamera WebRTC antar-manusia (ditunda);
