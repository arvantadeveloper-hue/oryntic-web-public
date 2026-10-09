# Katalog Harga Oryntix — struktur & kalkulasi

Dibuat 2026-10-09. Sumber data: dokumen Mongo `config/pricing_catalog` (seed di `backend/pricing_catalog.py`).

## 1. Hierarki

```
provider (openai | gemini | anthropic | seedance | oryntix)
└── service / model (gpt-live, gpt-image, gpt-luna, gemini-nano-banana, claude-sonnet, seedance-2-5, turn-relay, …)
    └── komponen harga (text_in, text_out, cached_in, audio_in, audio_out, image_in, image_out,
                        per_minute, per_second, per_call, per_search, per_session, per_hour, per_gb, …)
        └── satuan + qty dasar (unit, qty_basis)
```

Field komponen: `id, label, modality, direction, unit, qty_basis, usd, flat_qty, margin_pct, tax_pct, enabled, doc_col, note`.
Satuan yang didukung: token, character, minute, second, image, request, call, search, session, container_hour, GB, GB_day, profile, snapshot, page, song, video_second.

## 2. Satu rumus (ubah di satu tempat)

`pricing_catalog.quote(service_id, component_id, qty, pricing, feature, variant)`:

```
base_usd  = usd × qty ÷ qty_basis
sell_usd  = base_usd × (1 + margin%) × (1 + PPN%)     # urutan ada di PIPELINE = ["margin","tax"]
credits   = sell_usd ÷ usd_per_credit                 # 1 kredit = $0.001
```

- `qty = None` → memakai **qty flat dari docs**: `flat_qty[variant or "default"]`.
  Contoh: `gemini-nano-banana/image_out` = 1.290 token/gambar ($30/1M → $0,0387); `gpt-image/image_out` 1024² low/medium/high = 272 / 1.056 / 4.160 token.
- **Rantai margin & PPN**: komponen → layanan → provider → `margin_overrides[feature]` → global (`margin_pct` 30%, `tax_pct` 11%). Kosong/null = ikut induk.
- Mengubah urutan/menambah langkah (diskon, pembulatan) = ubah `PIPELINE` + satu loop di `quote()`.

## 3. Penagihan nyata yang sudah memakai katalog

| Jalur | Komponen katalog |
|---|---|
| Chat per model | `<model_id>/text_in` + `text_out` (`pricing.model_text_credits`) |
| Panggilan Realtime (usage report) | `<realtime_model>/audio_in·audio_out·text_in·text_out·cached_in` |
| Koneksi Realtime per menit | `gpt-live/per_minute` ($0,05 — docs OpenAI) |
| Gambar | `gemini-nano-banana/image_out` (1.290 token flat) |
| Tool provider | `openai:web_search/per_call`, `openai:code_interpreter/per_session`, `openai:image_generation/per_image`, `gemini:google_search/per_request`, `anthropic:web_search/per_search`, `anthropic:code_execution/per_hour` |
| Video | `seedance-2-5/per_second`, `seedance-2-0/per_second` |
| Data panggilan teman | `turn-relay/per_gb` (margin khusus 50%) |
| STT / TTS / cuplikan layar / profil persona | `openai-whisper`, `openai-tts`, `openai-vision`, `persona-profile` |

Fallback: bila komponen tidak ada/di-nonaktifkan, `pricing.py` memakai field lama (`model_prices`, `tool_prices`, `*_usd`).

## 4. API admin (platform staff/admin)

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/admin/pricing-catalog` | katalog + tabel terhitung + daftar satuan + pipeline + global |
| PUT | `/api/admin/pricing-catalog` | simpan katalog (langsung dipakai penagihan, cache 30 dtk) |
| POST | `/api/admin/pricing-catalog/quote` | simulator: `{service_id, component_id, qty?, variant?, feature?}` |
| POST | `/api/admin/pricing-catalog/import?provider_id=` | scrape halaman docs → **diff** (tidak menyimpan) |
| POST | `/api/admin/pricing-catalog/import/apply` | terapkan baris diff yang disetujui |

UI: `/admin` → tab **Katalog Harga** (`PricingCatalogCard.jsx`).

## 5. Catatan impor dari docs

- OpenAI: kolom baris tabel `input, cached, cache_write, output` → `doc_cols {text_in:0, cached_in:1, text_out:3}`.
- Anthropic: `input, output, 5m write, 1h write, cache hit` → `doc_cols {text_in:0, text_out:1, cached_in:4}`.
- Gemini: harga memuat promo bertanggal ("$0.75 through December 31, 2026. $1.50 starting January 1, 2027") sehingga tidak bisa dipetakan aman → `doc_cols {}` (impor melaporkan 0 baris, perbarui manual).
- Tool & layanan tanpa `doc_model` dilaporkan di `unmatched` agar admin tahu harus edit manual.

## 6. Status uji (2026-10-09)

`/app/backend/tests/test_pricing_catalog_iter40.py` — 16/16 lulus: kalkulasi (gpt-live 3 menit = 217 kredit, gpt-image high = 181 kredit, nano banana flat 1.290 = 56 kredit), persistensi PUT→GET, rantai override margin, impor Anthropic/OpenAI, Gemini 0 baris, otorisasi (user biasa 403), regresi chat (kredit terpotong normal).
