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

## Next tasks
- Add voice interaction (Phase 2) when requested.
- Wire a real payment provider for top-up when moving beyond MVP.
