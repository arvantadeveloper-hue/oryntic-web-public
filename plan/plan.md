# Persona AI (Aivora) — Rencana MVP

Asisten pribadi AI yang bisa Anda suruh bekerja: ia memecah tujuan Anda menjadi tugas, mengerjakannya bersama beberapa agent, lalu melaporkan hasilnya. Dilengkapi persona yang bisa Anda ciptakan sendiri, chat cerdas, workspace hasil kerja, dan pengingat proaktif.

## Untuk siapa
Individu dan profesional yang ingin satu asisten AI personal untuk mendelegasikan pekerjaan (riset, penulisan, analisis, perencanaan), mengobrol dengan karakter AI buatan sendiri, dan diingatkan atas jadwal/tugas mereka.

## Catatan platform (penting untuk disetujui)
Spesifikasi asli menyebut mobile native (React Native/Expo), Go, dan PostgreSQL. Yang dibangun di sini adalah **aplikasi web responsif** (bisa dibuka di browser HP dan desktop). Konsekuensinya untuk MVP:
- Tidak ada aplikasi mobile native, tidak ada panggilan VoIP masuk ala CallKit/telepon sungguhan. Pengingat "panggilan" ditampilkan sebagai layar panggilan **di dalam web app** + notifikasi in-app.
- Avatar hidup (HeyGen), digital human realtime, voice realtime, joget sinkron musik: **tidak di MVP** (fase lanjutan, butuh akun/API provider & pengujian khusus).
- Top-up kredit via IAP tidak mungkin di web. MVP memakai **kredit + top-up tersimulasi** (saldo diberikan/di-set, pemotongan berdasarkan pemakaian nyata dicatat). Pembayaran asli menyusul bila pindah ke mobile atau pakai gateway web.

## Fitur inti & pengalaman (MVP — yang dibangun sekarang)

**1. Akun & Onboarding**
- Daftar/masuk dengan email + password, verifikasi sederhana, kelola sesi, logout.
- Onboarding singkat: nama panggilan, bahasa, zona waktu, persetujuan syarat & privasi.

**2. Create Your Persona (pembuat karakter)**
- **Describe with AI**: tulis karakter yang diinginkan, GPT menyusun profil terstruktur (identitas, kepribadian, gaya bicara, penampilan, bahasa), Anda tinjau & setujui.
- **Upload Foto (opsional)**: unggah foto sebagai referensi penampilan + konfirmasi hak penggunaan. Foto dipakai sebagai acuan deskripsi visual (bukan menebak kepribadian/atribut sensitif).
- **Gabungan**: foto + instruksi teks.
- Gambar karakter (potret) dibuat dengan **Gemini image**. Bisa regenerate.
- Character editor: ubah identitas, kepribadian, penampilan, bahasa, batasan. Simpan versi, duplikat, hapus.

**3. Chat dengan AI**
- Percakapan streaming dengan persona terpilih (GPT), dukung markdown/list/kode.
- Riwayat percakapan, pencarian, salin pesan, regenerate, hapus percakapan.
- Lampiran teks/gambar/PDF sederhana sebagai konteks.

**4. Memori dengan kendali pengguna**
- Memori jangka panjang per-persona: lihat, edit, hapus, nonaktifkan. Tidak semua chat otomatis jadi memori permanen.

**5. Asisten yang bekerja + Kolaborasi Multi-Agent (inti produk)**
- Aivora sebagai koordinator. Anda beri satu tujuan; Aivora memecahnya jadi subtugas, menetapkan agent berperan (mis. Research, Writing, Analyst, Reviewer), menjalankannya, menggabungkan hasil, dan melaporkan hasil akhir.
- Panggilan agent secara natural lewat bahasa biasa (mis. "minta analis cek dokumen ini").
- Tampilan proses: ringkasan tugas, agent yang ditugaskan, status tiap subtugas, progres, retry bila gagal, output akhir.

**6. Task Manager & Workspace**
- Setiap pekerjaan jadi task dengan status (Draft, Queued, Running, Waiting input, Completed, Failed, Cancelled).
- Hasil kerja (dokumen/ringkasan/laporan) tersimpan di workspace: judul, instruksi, tanggal, agent terkait, input, hasil, ringkasan pemakaian.
- Pencarian, filter, sorting. Ekspor dokumen (mis. teks/markdown/PDF sederhana).

**7. Sistem Reminder proaktif**
- Buat aktivitas/jadwal dengan waktu, zona waktu, dan pengingat (5/10/15/30/60/120 menit atau khusus).
- Penjadwal backend memicu pengingat tepat waktu; Aivora menyusun pesan pengingat (mis. ringkas agenda/tugas belum selesai — hanya dari data nyata).
- Pengiriman: notifikasi in-app + layar "panggilan masuk" bergaya di dalam web app (avatar + nama persona + Terima/Tolak). Pengaturan opt-in, jam tenang, batas per hari.

**8. Dompet Kredit (transparan)**
- Saldo kredit, kredit terpakai, riwayat transaksi.
- Setiap aktivitas berbiaya (chat GPT, generate profil, generate gambar) mencatat usage event & memotong kredit berdasarkan pemakaian nyata.
- Top-up tersimulasi di MVP (lihat catatan platform). Tampilkan estimasi sebelum aktivitas mahal bila memungkinkan.

**9. Admin dasar**
- Kelola user, lihat daftar persona/task, lihat konfigurasi provider & tarif kredit, ringkasan pemakaian/biaya. (Konsol admin penuh + mesin harga dinamis = fase lanjutan.)

## Alur pengguna (ringkas)
1. Daftar → onboarding singkat.
2. Buat persona (deskripsi/foto) → setujui profil → dapat gambar karakter.
3. Chat dengan persona, atau beri Aivora sebuah tujuan kerja.
4. Aivora memecah tugas → agent mengerjakan → status terlihat di workspace → hasil akhir tersimpan & bisa diekspor.
5. Buat pengingat → saat waktunya, muncul notifikasi/layar panggilan → asisten menyampaikan pengingat.
6. Pantau saldo kredit & riwayat pemakaian di Profil/Wallet.

## Branding — Aivora (dari aset yang dilampirkan)
- **Nama/brand:** Aivora. **Tagline:** "Your AI, in your corner."
- **Logomark:** huruf "A" bergaya pita 3D gradasi biru. Dipakai di sidebar, splash, favicon, dan layar panggilan.
- **Color palette:**
  - Aivora Blue `#00D1FF`
  - Aivora Purple `#7C3AED`
  - Deep Navy `#0B132B`
  - Slate `#334155`
  - Soft Blue `#E0F2FE`
  - Light `#F8FAFC`
- **Arah tema:** tema gelap premium (Deep Navy sebagai dasar) dengan aksen gradasi biru→ungu; tersedia juga varian terang. Logo punya versi primary dark, primary light, monochrome black, dan reversed white — dipakai sesuai latar.
- **Aset tersimpan (dipakai saat build):**
  - Horizontal light logo: https://customer-assets-cm19k8pv.emergentagent.net/job_ai-companion-test-5/artifacts/qokjecym_Aivora_Horizontal_Light_Logo.png
  - Primary dark logo: https://customer-assets-cm19k8pv.emergentagent.net/job_ai-companion-test-5/artifacts/zfh3gxgw_Aivora_Primary_Dark_Logo.png
  - Logo variations: https://customer-assets-cm19k8pv.emergentagent.net/job_ai-companion-test-5/artifacts/i3ngo81h_Aivora_Logo_Variations.png
  - Standalone mark: https://customer-assets-cm19k8pv.emergentagent.net/job_ai-companion-test-5/artifacts/7x1kdqac_Aivora_Standalone_Mark.png
  - Color palette & typography: https://customer-assets-cm19k8pv.emergentagent.net/job_ai-companion-test-5/artifacts/fctb6041_Aivora_Color_Palette_and_Typography.png

## Rasa UI/UX
Premium, modern, personal, dan futuristik tanpa berlebihan, mengikuti brand kit Aivora di atas (tema gelap Deep Navy + aksen gradasi biru/ungu). Hierarki visual jelas, spacing lega, animasi halus dan bermakna, state lengkap (loading/empty/success/error). Prioritaskan interaksi dengan persona & pekerjaan, bukan dashboard padat. Responsif untuk HP dan desktop. Dukungan bahasa UI minimal Indonesia & Inggris. UI final dirancang bersama design agent.

## Fase implementasi

**Fase 1 — MVP (dibangun sekarang)**
Akun & onboarding, pembuat persona (teks/foto + gambar Gemini), chat streaming + memori, kolaborasi multi-agent + task manager/workspace, sistem reminder (in-app), dompet kredit dengan pencatatan pemakaian nyata + top-up simulasi, admin dasar. Bahasa UI ID/EN.

**Fase 2 — Suara, pembayaran, admin lanjut**
Voice interaction (STT/TTS), pembayaran top-up nyata (gateway web/mobile IAP), konsol admin penuh + katalog harga provider + penyesuaian margin, group chat/meeting multi-persona, multibahasa penuh + RTL, RBAC peran (finance/ops/support/auditor).

**Fase 3 — Digital human & mobile native**
Avatar hidup realtime (mis. HeyGen) & lip-sync, video call dengan avatar, panggilan VoIP masuk native (CallKit/PushKit, Android Telecom) via aplikasi mobile, joget avatar sinkron musik, monitoring harga otomatis & rekonsiliasi penuh.

## Asumsi (keputusan yang diambil tanpa bertanya lagi)
- Dibangun sebagai **web app responsif** (bukan Expo/mobile native).
- **Autentikasi: email + password (JWT)** karena Anda tidak menyebut Google login.
- **Teks: GPT** (versi terbaru), **gambar: Gemini image**, memakai Universal Key Emergent (tanpa Anda menyetor API key sendiri).
- **Multi-agent memakai satu model (GPT) dengan peran/instruksi berbeda**, bukan banyak model terpisah — sesuai spesifikasi.
- Reminder & scheduler berjalan di backend; pengiriman via in-app (bukan telepon sungguhan).
- Top-up kredit **tersimulasi**; tidak ada pemrosesan pembayaran nyata di MVP.
- HeyGen/digital human, voice realtime, VoIP native, joget-musik, mesin harga dinamis penuh, dan lokalisasi penuh **ditunda** ke fase berikutnya.
- Admin MVP cukup read-only + aksi dasar; bukan konsol operasional penuh.
- Bahasa antarmuka awal: Indonesia & Inggris.
