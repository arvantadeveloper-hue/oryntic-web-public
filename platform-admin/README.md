# Oryntix Platform — Back-office (project terpisah)

Konsol admin platform Oryntix (dasbor, laporan keuangan, tarif & margin per model, paket kredit, pengguna, staf & peran, trial & batas, rate limit).
Dipisahkan dari aplikasi utama agar bisa dideploy sebagai project tersendiri, mis. **https://admin.oryntix.com**.

## Arsitektur
- `backend/` — FastAPI tipis yang **berbagi MongoDB yang sama** dengan backend utama Oryntix (koleksi `users`, `config`, `usage`, `wallet_tx`, `audit`, ...). Router: `/api/auth/*` (login/me), `/api/platform/*`, `/api/platform/finance/*`, `/api/admin/pricing|trial|rate-limits`.
- `frontend/` — React (CRA + craco + Tailwind). Seluruh situs adalah konsol platform (`/`), login khusus staf platform (`platform_role`: `super_admin` / `finance`).

## Menjalankan
```bash
# backend
cd backend && cp .env.example .env   # isi MONGO_URL, DB_NAME, JWT_SECRET (WAJIB sama dengan backend utama), ADMIN_EMAIL/PASSWORD, SMTP
pip install -r requirements.txt && uvicorn server:app --host 0.0.0.0 --port 8001

# frontend
cd frontend && cp .env.example .env  # REACT_APP_BACKEND_URL = URL backend ini
yarn install && yarn start
```

## Catatan penting
- `JWT_SECRET` harus identik dengan backend utama supaya token staf valid di kedua sisi (login bisa dilakukan di salah satu).
- Perubahan tarif/trial/rate-limit disimpan di koleksi `config` dan langsung dipakai backend utama (cache tarif di-refresh otomatis).
- Di aplikasi utama, menu "Oryntix Platform" muncul di sidebar bila env `REACT_APP_PLATFORM_URL` diisi (tautan eksternal ke situs ini).
- Di Emergent: buat project baru → unggah/push folder ini → set env di atas → deploy.
