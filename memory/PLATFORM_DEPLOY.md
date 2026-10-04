# Deploy Oryntix Platform (back-office) ke admin.oryntix.com — jalur B

Satu codebase, dua deployment. Frontend yang sama bisa berjalan sebagai **app pengguna** (default) atau **situs admin saja**
("platform mode": env `REACT_APP_PLATFORM_MODE=1` atau hostname diawali `admin.`/`platform.` → back-office dirender di `/`).

## Langkah
1. **Project baru**: di Emergent, fork/duplikat project ini (atau "Save to GitHub" lalu buat project dari repo yang sama).
2. **Secrets project admin** (frontend): `REACT_APP_BACKEND_URL=https://oryntix.com` (domain app utama), `REACT_APP_PLATFORM_MODE=1`.
   Backend project admin tidak dipakai (boleh dibiarkan; semua data lewat API app utama).
3. **Deploy** project admin → Manage Publishes → Domain → tambahkan `admin.oryntix.com` (A record ke IP Emergent, SSL otomatis).
4. **Secrets project utama** (backend): `CORS_ORIGINS=https://oryntix.com,https://admin.oryntix.com` → Re-publish.
5. Login di admin.oryntix.com dengan akun staf (ADMIN_EMAIL = Super Admin). Tautan "atur password" undangan staf mengarah ke
   domain app utama (`/reset-password`), tetap valid.

## Catatan
- Peran dibaca dari DB tiap request; token JWT sama dengan app utama (disimpan per-origin di localStorage).
- Hostname `admin.*` otomatis memicu platform mode walau env tidak diset.
- Biaya: deployment kedua ±50 kredit/bulan; custom domain gratis.
