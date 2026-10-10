# Oryntix Platform — Back-office (project terpisah)

Konsol admin platform Oryntix (dasbor, laporan keuangan, tarif & margin per model, paket kredit, pengguna, staf & peran, trial & batas, rate limit).
Dipisahkan dari aplikasi utama agar bisa dideploy sebagai project tersendiri, mis. **https://admin.oryntix.com**.

## Arsitektur
- **Backend sudah dipindahkan ke backend utama Oryntix** (`/app/backend/platform_api/`), semua endpoint di bawah `/api/platform/*` — lihat `API_SPEC.md` (juga `GET /api/docs` di backend utama). Folder `backend/` di sini dihapus; arahkan `REACT_APP_BACKEND_URL` frontend admin ke URL backend utama.
- `frontend/` — React (CRA + craco + Tailwind). Seluruh situs adalah konsol platform (`/`), login khusus staf platform (`platform_role`: `super_admin` / `finance`).

## Menjalankan
```bash
# frontend
cd frontend && cp .env.example .env  # REACT_APP_BACKEND_URL = URL backend UTAMA Oryntix
yarn install && yarn start
```

## Catatan penting
- Login staf memakai `POST /api/auth/login` backend utama; semua data konsol lewat `/api/platform/*` (alias lama `/api/admin/pricing|rate-limits|support-agent|model-routing` tetap ada).
- Perubahan tarif/trial/rate-limit disimpan di koleksi `config` dan langsung dipakai backend utama (cache tarif di-refresh otomatis).
- Di aplikasi utama, menu "Oryntix Platform" muncul di sidebar bila env `REACT_APP_PLATFORM_URL` diisi (tautan eksternal ke situs ini).
- Di Emergent: buat project baru → unggah/push folder ini → set env di atas → deploy.

## Perubahan path API (frontend)
Semua pemanggilan di `frontend/src` sudah memakai `/api/platform/*` (tarif `/platform/pricing`, `/platform/pricing/preview`, `/platform/trial`, `/platform/rate-limits`, Asisten `/platform/support-agent*`, Conversation Behaviour `/platform/realtime-behaviour`). Login tetap `/api/auth/login`.
Halaman baru **Conversation Behaviour** (`/behaviour`, super_admin) ditambahkan. Build diverifikasi (`yarn build`) terhadap backend utama.
Cara publish: salin isi folder `frontend/` ke repo `oryntix-web-admin/frontend`, set `REACT_APP_BACKEND_URL=<URL backend utama>` dan `REACT_APP_PLATFORM_MODE=1`, lalu deploy.
