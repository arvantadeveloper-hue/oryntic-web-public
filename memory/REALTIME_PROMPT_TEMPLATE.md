# Realtime prompt — DIPINDAHKAN KE KODE (2026-06)

Prompt dashboard OpenAI (`pmpt_...`) TIDAK dipakai lagi. `OPENAI_REALTIME_PROMPT_ID` dikosongkan dan kode jalurnya dihapus dari `realtime_voice.py`.

Sumber tunggal konfigurasi persona (chat teks + suara): `backend/assistant_persona.py`
- `CORE_SECTIONS` (bagian 1–10) + `CLOSING_SECTIONS` (13–17) → teks & suara
- `SPOKEN_SECTIONS` (11 Spoken Language, 12 Interruptions) → hanya suara
- `{{language}}` diganti nama bahasa pengguna oleh `persona_block()`
- Konteks per panggilan (persona, memori, peran moderator/panelis, riwayat, pembuka) ditambahkan oleh `chat._persona_system` + `realtime_voice._session_instructions`.

Model Realtime: `OPENAI_REALTIME_MODEL=gpt-realtime-2.1` (harga sama dengan gpt-realtime-2). Di produksi: set `OPENAI_REALTIME_MODEL=gpt-realtime-2.1` dan kosongkan/hapus `OPENAI_REALTIME_PROMPT_ID` di Secrets.
