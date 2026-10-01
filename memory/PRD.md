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

## Next tasks
- Konfirmasi endpoint id Seedance via satu run video nyata, lalu salin output ke object storage.
- VAD auto-stop agar mode panggilan benar-benar hands-free tanpa tekan Kirim.
- True token-by-token streaming.
