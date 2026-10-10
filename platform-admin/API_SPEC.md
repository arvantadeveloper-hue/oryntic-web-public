# Oryntix Platform API — Spesifikasi (`/api/platform/*`)

Backend konsol admin (`oryntix-web-admin`) kini hidup di backend utama Oryntix, paket `backend/platform_api/`.
Semua endpoint berada di bawah **`/api/platform/`** (path lama `/api/admin/pricing`, `/api/admin/rate-limits`,
`/api/admin/support-agent`, `/api/admin/model-routing` tetap berfungsi sebagai alias).
Spesifikasi OpenAPI lengkap (termasuk skema body): **`GET /api/openapi.json`**, Swagger UI: **`GET /api/docs`**.

## Autentikasi & peran
- Login: `POST /api/auth/login {email, password}` → `{access_token, user}`; kirim `Authorization: Bearer <access_token>`.
- Sesi: `GET /api/platform/me` → profil + `platform_role` + daftar peran.
- Peran (dibaca dari DB, bukan dari JWT): **`super_admin`** (semua), **`finance`** (laporan, pengeluaran, baca tarif). `ADMIN_EMAIL` di env selalu `super_admin`.
- Error: `401` tanpa/invalid token · `403` peran tidak cukup (`"Akses staf platform diperlukan"` / `"Platform admin access required"`) · `400/404` validasi domain · `422` validasi body (Pydantic: `{detail:[{loc,msg,type}]}`).
- Setiap perubahan dicatat ke `platform_audit` (`GET /api/platform/audit`).

## Ringkasan endpoint
| Area | Method & path | Peran |
|---|---|---|
| Dasbor | `GET /stats?days=30` | staff |
| Staf | `GET /staff` · `POST /staff {email, role, name?}` · `PUT /staff/{uid} {role}` · `DELETE /staff/{uid}` | super_admin |
| Pengguna | `GET /users?q&before&limit` · `POST /users/{uid}/credits {delta≥1, note}` · `POST /users/{uid}/disable {disabled, reason}` · `GET /users/{uid}/history` | super_admin |
| Audit | `GET /audit?limit&q&action&start&end` · `GET /audit/export.csv` | super_admin |
| Keuangan | `GET /finance?date_from&date_to&group=day\|month` · `GET /finance/export.csv` · `GET /finance/ppn?year` · `GET /finance/ppn/export.csv` · `GET /finance/pnl?year` · `GET /finance/pnl/export.csv\|pdf?year` · `GET /finance/pnl/range[...]?date_from&date_to&group` | staff |
| Pengeluaran | `GET /expenses?q&category&start&end` · `POST /expenses` (multipart: date, category, vendor, amount_idr, description, taxable, efaktur_no, file) · `DELETE /expenses/{eid}` · `GET /expenses/export.csv` · `GET /expenses/pending-efaktur` · `PUT /expenses/{eid}/efaktur` (multipart) · `GET /expenses/{eid}/file` · `GET/POST /expenses/recurring` · `PUT/DELETE /expenses/recurring/{rid}` · `POST /expenses/recurring/run` · `GET/PUT /expenses/budget` | staff |
| Asisten Oryntix | `GET /support-agent` (staff) · `PUT /support-agent` · `GET /support-agent/avatars?page&page_size&mine` (staff) · `POST /support-agent/preview {message, session_id?}` | super_admin |
| **Pricing** | lihat bagian di bawah | |
| **Karakter Persona** | `GET/POST /persona-characters` · `PUT/DELETE /persona-characters/{cid}` — lihat bagian di bawah | staff baca · super_admin ubah |
| Cron | `POST /cron/recurring-expenses` · `POST /cron/efaktur-reminder` — header `Authorization: Bearer <WEBHOOK_CRON_SECRET>`; dijadwalkan di `.emergent/crons.yml` | cron |

---

## Pricing API (mesin tarif milik backend utama: `pricing.py`, `pricing_catalog.py`, `ratelimit.py`)

Rumus satu-satunya: **kredit = biaya provider (USD) × (1 + margin) × (1 + PPN) ÷ `usd_per_credit`**, dibulatkan ke atas.
Margin per komponen → per layanan → per provider → global (`margin_pct`). 1 kredit = $0,001 (default).

### 1. `GET /api/platform/pricing` — tarif global, paket, tabel ringkasan  *(staff)*
Respons:
```jsonc
{
  "pricing": { /* dokumen tarif global, lihat PlatformPricingIn */ },
  "rates": { "text_per_1k": 9.74, "image": 57, "profile": 38, "stt": 24, "tts": 19, "realtime_per_min": 73, "vision": 9,
             "bandwidth_per_mb": 0.813, "video_per_sec": 1154.4, "video20_per_sec": 865.8,
             "video_res_mult": {"480p": 0.6, "720p": 1.0, "1080p": 1.6}, "video_real_person_mult": 1.45, "video_audio_mult": 1.0 },
  "features": [ { "feature": "text", "label": "Teks / chat", "unit": "1k karakter", "provider_usd": 0.00675, "margin_pct": 30,
                  "source": "text-default/per_1k_chars", "override": false, "credits_exact": 9.7402, "credits": 10 } ],
  "models":   [ { "id": "gpt-astra", "label": "GPT Astra", "provider": "openai", "in_usd_1m": 10, "out_usd_1m": 50,
                  "credits_in_per_1k": 3.608, "credits_out_per_1k": 18.038, "credits_typical": 19 } ],
  "realtime_models": [ { "id": "gpt-live-1", "label": "GPT-Live", "catalog_id": "gpt-live", "per_min_usd": 0.05, "credits_per_min": 73,
                         "audio_in": 0, "audio_out": 0, "text_in": 0, "text_out": 0, "cached_in": 0 } ],
  "tools":    [ { "id": "openai:web_search", "provider": "openai", "label": "Pencarian web", "unit": "pencarian", "usd": 0.01, "credits": 15 } ],
  "packages": [ { "id": "starter", "name": "Starter", "usd": 3.0, "credits": 3000, "price_idr": 69000, "discount_pct": 0, "best_value": false } ],
  "trial":    { "trial_days": 7, "trial_daily_limit": 100, "trial_credits": 700 },
  "providers": [ /* ringkasan provider aktif */ ],
  "tariff":   { "method": "…", "profile_generation_credits": 38, "image_generation_credits": 57, "text_credits_per_1k_chars": 9.74 }
}
```

### 2. `PUT /api/platform/pricing` — simpan tarif global  *(super_admin, audit `pricing.update`)*
Body **PlatformPricingIn** (wajib: `margin_pct`, `tax_pct`, `usd_to_idr`, `idr_per_credit`):
| Field | Tipe | Batas / default | Arti |
|---|---|---|---|
| `margin_pct` | number | 0–500 | margin global (%) |
| `tax_pct` | number | 0–100 | PPN (%) |
| `usd_to_idr` | number | > 0 | kurs untuk harga paket |
| `idr_per_credit` | number | > 0 | tampilan saja |
| `usd_per_credit` | number | > 0, default 0.001 | nilai 1 kredit |
| `margin_overrides` | object `{feature: pct}` | — | margin khusus per fitur |
| `chars_per_token` | number | 1–10, default 4 | konversi karakter→token |
| `package_margin_pct` | number | 0–500, default 15 | margin paket kredit |
| `package_round_idr` | integer | 1–1.000.000, default 1000 | pembulatan harga paket |
| `packages` | array **PackageTierIn** `{id ^[a-z0-9_-]+$, name, usd>0, discount_pct 0–100, best_value}` | — | tier paket |
| `video_res_480_mult` / `video_res_1080_mult` / `video_real_person_mult` / `video_audio_mult` | number | >0; default 0.6 / 1.6 / 1.45 / 1.0 | pengali video |

Respons: `{pricing, rates, features, models, packages, tools}` (nilai tersimpan).

### 3. `POST /api/platform/pricing/preview` — simulasi tanpa menyimpan  *(super_admin)*
Body = PlatformPricingIn. Respons: `{rates, features, models, packages, tools}`.

### 4. `GET /api/platform/trial` → `{trial}` *(staff)* · `PUT /api/platform/trial` *(super_admin, audit `trial.update`)*
Body **TrialIn**: `trial_days` 0–365 · `trial_daily_limit` 0–100.000 · `trial_credits` 0–1.000.000. Respons `{trial}`.

### 5. `GET /api/platform/rate-limits` *(staff)* · `PUT /api/platform/rate-limits` *(super_admin, audit `rate_limits.update`)*
Body **LimitsIn**: `chat_per_min`* 1–1000 · `chat_per_hour` 1–100.000 (300) · `chat_min_interval_ms` 0–60.000 (1500) · `chat_max_inflight` 1–50 (4) · `chat_dup_per_30s` 1–100 (3) · `voice_per_min`* 1–1000 · `calls_per_hour`* 1–1000 · `max_call_minutes`* 1–600 · `generation_per_hour`* 1–1000 · `storage_quota_mb` 1–100.000 (50). (* wajib). Respons: dokumen limit tersimpan.

### 6. Katalog harga — `GET /api/platform/pricing-catalog`  *(staff)*
```jsonc
{
  "catalog": { "version": 3, "providers": [ {
      "id": "openai", "label": "OpenAI", "docs_url": "https://…/pricing", "margin_pct": null, "tax_pct": null,
      "doc_cols": {"text_in": 0, "cached_in": 1, "text_out": 3},
      "services": [ { "id": "gpt-luna", "label": "GPT Luna", "kind": "text|realtime|image|stt|tts|vision|tool|video|music",
                      "doc_model": "gpt-6-luna", "margin_pct": null, "tax_pct": null, "note": "",
                      "components": [ { "id": "text_in", "label": "Input", "unit": "token", "qty_basis": 1000000, "usd": 0.1,
                                        "modality": "text|audio|image", "direction": "input|output|flat",
                                        "margin_pct": null, "tax_pct": null, "enabled": true, "doc_col": 0, "note": "" } ] } ] } ] },
  "table":  [ /* catalog + per komponen "unit_label" dan "calc": {path, unit_usd, base_usd, margin_pct, tax_pct, margin_usd, tax_usd, total_usd, credits_exact, credits} */ ],
  "units":    { "token": "token", "minute": "menit", "image": "gambar", "call": "panggilan API", "GB_day": "GB per hari", … },
  "pipeline": ["margin", "tax"],
  "globals":  { "margin_pct": 30.0, "tax_pct": 11.0, "usd_per_credit": 0.001 },
  "feature_map": { "text": ["text-default", "per_1k_chars"], "image": ["gemini-nano-banana", "image_out"], … }
}
```
- `null` pada `margin_pct`/`tax_pct` = mewarisi level di atasnya. `usd` selalu harga per `qty_basis` unit (mis. $/1M token → `qty_basis` 1000000).

### 7. `PUT /api/platform/pricing-catalog` — simpan katalog  *(super_admin, audit `catalog.update`)*
Body **CatalogIn** `{ "version": 2, "providers": [ …struktur yang sama dengan `catalog.providers` ] }`. Respons `{catalog, table, rates, features, models, tools}`.

### 8. `POST /api/platform/pricing-catalog/quote` — hitung kredit satu komponen  *(staff)*
Body **QuoteIn** `{ "service_id": "gpt-luna", "component_id": "text_in", "qty": 1000, "feature": null }` (`qty` null → kuantitas flat dari dokumen).
Respons = objek `calc` (lihat di atas) untuk kuantitas tersebut; `404` jika komponen tidak ada/dinonaktifkan.

### 9. Impor harga dari halaman provider  *(super_admin)*
- `POST /api/platform/pricing-catalog/import?provider_id=openai` → `{ "provider_id", "rows": [ {service_id, component_id, label, old_usd, new_usd, changed} ], … }` (tidak menyimpan; `502` bila halaman gagal dibaca).
- `POST /api/platform/pricing-catalog/import/apply` body **ImportApplyIn** `{ "provider_id": "openai", "rows": [ …baris yang dipilih… ] }` → `{catalog, table, rates}` (audit `catalog.import`).

### 10. Pengaturan terkait
- `GET/PUT /api/platform/realtime-behaviour` — **BehaviourIn**: `turn_detection` `semantic_vad|server_vad`*, `eagerness` `low|medium|high|auto`*, `interrupt_response` (false), `create_response` (true), `threshold` 0–1 (0.5), `prefix_padding_ms` 0–2000 (300), `silence_duration_ms` 100–5000 (500), `barge_confirm_ms` 200–5000 (1300), `backchannel_resume` (true), `backchannel_window_ms` 1000–30000 (8000), `note`.
- `GET/PUT /api/platform/model-routing` — **RoutingIn**: `enabled` (true), `it_model`* `^[a-z0-9-]+$`, `research_model`*, `confirm_threshold`* 0–1000.

## Karakter Persona API (`/api/platform/persona-characters`)
Preset "Karakter Persona" yang dipilih pengguna saat membuat persona (combo box di langkah *Describe with AI / Combine Both / From Photo*).
Karakter **bawaan** (`id: "default"`, `builtin: true`) = prompt inti `assistant_persona.py` (CORE_SECTIONS) — hanya bisa dibaca. Jika pengguna memilih karakter lain, **prompt karakter tersebut MENIMPA** prompt inti bawaan untuk persona itu (chat teks maupun suara Realtime); instruksi lain (bahasa, memori, tools, profil persona) tetap berlaku.

| Method & path | Peran | Keterangan |
|---|---|---|
| `GET /api/platform/persona-characters` | staff | `{items:[Character]}` — bawaan selalu pertama, lalu urut `sort`, `name`; termasuk `prompt` lengkap |
| `POST /api/platform/persona-characters` | super_admin | body **CharacterIn** → `201 Character`; audit `persona_character.create` |
| `PUT /api/platform/persona-characters/{cid}` | super_admin | body **CharacterIn** → `Character`; `400` bila `cid="default"`; `404` tidak ada; audit `persona_character.update` |
| `DELETE /api/platform/persona-characters/{cid}` | super_admin | → `{ok:true, personas_reset:n}` — persona pengguna yang memakainya otomatis kembali ke bawaan; `400` bila bawaan |

**CharacterIn**
| Field | Tipe | Batas | Arti |
|---|---|---|---|
| `name` | string | 1–80 | nama yang tampil di combo box |
| `description` | string | ≤ 600 | *Deskripsi Karakter* — ditampilkan di bawah combo box dan dipakai AI saat menyusun profil persona |
| `prompt` | string | 20–20.000 | *Prompt Karakter* — menggantikan CORE_SECTIONS (`{{language}}` boleh dipakai sebagai placeholder bahasa) |
| `enabled` | bool | default true | nonaktif = tidak muncul untuk pengguna; persona yang sudah memakainya jatuh ke bawaan |
| `sort` | int | 0–10.000, default 100 | urutan tampil |

**Character** (respons) = CharacterIn + `id`, `builtin`, `created_at`, `updated_at`.

Sisi pengguna (app utama): `GET /api/personas/characters` → `{items:[{id,name,description,enabled,sort,builtin}], default:"default"}` (hanya yang aktif, tanpa prompt); `POST /api/personas/generate-profile {description (penampilan), method, photo_b64?, character_id?}`; `POST /api/personas {…, character_id}`; `PUT /api/personas/{pid} {…, character_id?}` → `400 "Karakter persona tidak ditemukan atau dinonaktifkan"` bila id tidak valid.

## Cron (`.emergent/crons.yml`)
| name | jadwal (Asia/Jakarta) | endpoint |
|---|---|---|
| `recurring-expenses` | tanggal 1, 01:00 | `POST /api/platform/cron/recurring-expenses` — buat pengeluaran langganan bulan ini + cek anggaran |
| `efaktur-reminder` | tanggal 25, 09:00 | `POST /api/platform/cron/efaktur-reminder` — email finance soal e-faktur yang belum diunggah |
Keduanya mengembalikan `{ok:true, queued:true}` segera dan bekerja di background; `401` bila secret salah.

## Env yang dipakai paket platform
`MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `WEBHOOK_CRON_SECRET`, `PLATFORM_URL` (tautan di email finance), `LIVEAVATAR_API_KEY`, `EMERGENT_LLM_KEY` (object storage e-faktur), SMTP (`SMTP_*`) untuk email.
Seeder staf finance: `cd backend && SEED_FINANCE_EMAIL=… SEED_FINANCE_PASSWORD=… python seed_finance.py`.
