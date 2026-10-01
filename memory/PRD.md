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

## Next tasks
- Uji manual Mode Realtime (sela, giliran multi-agen) & panggilan pengingat dengan mikrofon nyata (user).
- (P3) CORS pin untuk produksi; rate limit lintas-instance (Redis) bila dideploy multi-replica.
- (Backlog P1) Payment gateway nyata; (P2) kamera WebRTC antar-manusia (ditunda); Moderator "buntu"/hening untuk RealtimeMeeting.
