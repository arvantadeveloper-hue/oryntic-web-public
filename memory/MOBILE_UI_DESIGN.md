# Oryntix Mobile — Blueprint UI/UX: Welcome, Login & Dashboard (Android & iOS)

Dokumen desain untuk developer mobile (React Native / Expo). Konsisten dengan tema web Oryntix saat ini
(navy gelap `#0A1128` untuk permukaan brand + konten terang `#F4F6FB` dengan kartu putih radius besar).
Bahasa UI: **Indonesia (default) + English** (ikut `settings.app_language`, sama seperti web).

Mockup referensi (hasil render, bukan aset final — pakai sebagai arah rasa visual):
- Welcome/Onboarding: https://static.prod-images.emergentagent.com/jobs/7c4c21b3-5636-4f0b-a827-715fd3f3daab/images/052d5d4aca3323c2a2601f4b6c70a81f79310de98e18ef8ae912c9d34a3ac4aa.jpeg
- Login: https://static.prod-images.emergentagent.com/jobs/7c4c21b3-5636-4f0b-a827-715fd3f3daab/images/ad4c2d01e3894fc36aa18f71e35e9b75bf9bb43a0cd7d70e880dd2601030c1be.jpeg
- Dashboard: https://static.prod-images.emergentagent.com/jobs/7c4c21b3-5636-4f0b-a827-715fd3f3daab/images/df916dc53207d1a1d9c0abab1dc9a5378b721c5d76d89cd0e1d9bacf60eecad8.jpeg

---

## 1. Design tokens (sinkron dengan `frontend/src/index.css`)

```ts
export const color = {
  bg:        '#F4F6FB',  // latar aplikasi (light)
  card:      '#FFFFFF',
  line:      '#E6EAF2',  // border kartu/input
  ink:       '#0F172A',  // teks utama
  muted:     '#64748B',  // teks sekunder
  faint:     '#94A3B8',  // placeholder, caption
  blue:      '#2F6BFF',  // primary
  blueDark:  '#2458E0',  // pressed
  blueSoft:  '#EEF3FF',  // chip/ikon bg
  cyan:      '#22B8FF',
  purple:    '#7C3AED',
  navy:      '#0A1128',  // permukaan brand (header welcome/login, tab aktif gelap)
  navy2:     '#111B3A',
  success:   '#10B981',
  warning:   '#F59E0B',
  danger:    '#EF4444',
};

export const gradient = {
  primary: ['#2F6BFF', '#7C3AED'],              // tombol utama (120deg)
  hero:    ['#EAF0FF', '#F2F5FF', '#E6F4FF'],   // kartu hero dashboard
  navyGlow: 'radial 60% 30% at 50% 0% rgba(47,107,255,.18) → transparan',
};

export const radius = { sm: 10, md: 14, lg: 20, xl: 24, xxl: 28, pill: 999 };
export const space  = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 28, xxxl: 40 };
export const shadow = {           // iOS: shadow*, Android: elevation
  card:  { color: 'rgba(16,24,40,0.06)', offsetY: 6, radius: 20, elevation: 2 },
  float: { color: 'rgba(47,107,255,0.28)', offsetY: 8, radius: 20, elevation: 6 },
};
```

Dark mode: **tidak ada di Tahap 1** (web juga light-only). Siapkan token lewat satu objek `theme`
agar penambahan dark mode nanti tidak menyentuh komponen.

## 2. Tipografi

Font: **Plus Jakarta Sans** (`@expo-google-fonts/plus-jakarta-sans`: 400/500/600/700/800).
Mono (kode di chat): **JetBrains Mono**. Skala mobile (dp, lineHeight ≈ 1.35×):

| Token | Size / Weight | Pemakaian |
|---|---|---|
| `display` | 30 / 800 | Judul welcome ("Asisten AI pribadi Anda") |
| `h1` | 24 / 700 | Judul layar ("Masuk", "Selamat pagi") |
| `h2` | 19 / 700 | Judul kartu/section |
| `h3` | 16 / 600 | Nama asisten, item list |
| `body` | 15 / 400 | Paragraf, isi pesan |
| `bodySm` | 13.5 / 400 | Subjudul list, deskripsi |
| `label` | 13 / 600 | Label tombol, tab |
| `caption` | 11.5 / 500 | Timestamp, helper, legal |

Letter-spacing `-0.2` untuk ≥19dp, `0` untuk teks kecil. `allowFontScaling` ON; uji sampai 130% font OS
(semua tombol tinggi minimum 48dp, teks tombol boleh 2 baris).

## 3. Komponen inti (reusable)

| Komponen | Spesifikasi |
|---|---|
| `Button` variant `primary` | tinggi 52, radius 16, gradient `primary`, teks putih 15/700, pressed `scale .98` + opacity .92 |
| `Button` variant `solid` | bg `blue`, pressed `blueDark` |
| `Button` variant `soft` | bg putih, border `line`, teks `ink` |
| `Button` variant `ghost` | tanpa bg, teks `blue` |
| `Input` | tinggi 52, radius 14, bg putih, border `line`, ikon kiri 18dp `faint`, focus border `blue` + ring `rgba(47,107,255,.14)` 3dp, error border `danger` + helper 11.5 `danger` |
| `Card` | bg putih, radius 24, padding 16–20, `shadow.card`, border `line` 1dp |
| `Pill` | radius pill, h 28, px 10, bg `blueSoft`, teks 12/700 `blue` (varian warning/success untuk status) |
| `Avatar` | 40 / 48 / 56 dp bulat, fallback inisial di bg `blueSoft` teks `blue` |
| `SectionHeader` | judul `h2` + aksi kanan `ghost` 13/600 |
| `ListRow` | tinggi min 64, avatar + (judul `h3`, subtitle `bodySm` 1 baris ellipsis) + meta kanan (jam `caption`, badge belum dibaca 8dp `blue`) |
| `EmptyState` | ikon lucide 28 dalam bulatan 56 `blueSoft`, judul `h3`, deskripsi `bodySm`, 1 tombol |
| `Skeleton` | blok radius 12 abu `#EDF1F7` + shimmer 1.6s (sama seperti `.render-shimmer` web) |
| `Toast` | `react-native-toast-message`, kartu putih radius 16, garis kiri 4dp per status |
| `BottomSheet` | `@gorhom/bottom-sheet`, radius atas 28, handle 36×4 `#CBD5E1` |

Ikon: **lucide-react-native**, stroke 1.75, ukuran 18 (inline) / 22 (tab) / 28 (empty state).
**Tanpa emoji sebagai ikon.** Animasi: `react-native-reanimated` — fade+translateY 10dp 250ms untuk entrance
(ekuivalen `.fade-up` web), stagger 40ms antar kartu dashboard.

## 4. Layar 1 — Welcome / Onboarding (`/welcome`)

Tampil hanya saat `!token && !hasSeenOnboarding` (AsyncStorage `oryntix_onboarded`).
Latar **navy** `#0A1128` + 2 radial glow (biru atas-tengah, ungu kanan-bawah) + titik grid halus 6% opacity.

```
┌─────────────────────────────┐  safe-area top
│                 [ID|EN] ⌄   │  language toggle, 44dp hit area
│                             │
│          ◼ mark 88dp        │  logo mark + glow ring (pulse 2.4s, opsional)
│                             │
│   Asisten AI pribadi Anda   │  display 30/800, putih, max 2 baris
│   Bangun persona, chat,     │  body 15 #A3AFC9, max 3 baris
│   dan delegasikan tugas.    │
│                             │
│  ▢ Chat & panggilan suara   │  3 feature row: ikon 18 biru dlm kotak
│  ▢ Tim asisten multi-agen   │  40dp radius 12 rgba(255,255,255,.06)
│  ▢ Tugas jadi dokumen       │
│                             │
│          ● ○ ○              │  dots 8dp, aktif biru lebar 20
│                             │
│  [        Mulai         ]   │  primary, full width
│   Sudah punya akun? Masuk   │  ghost
└─────────────────────────────┘  safe-area bottom (min 16dp)
```

- 3 slide horizontal (`FlatList` paging, swipe + dots tappable):
  1. **Kenali Oryntix** — headline di atas, ilustrasi mark.
  2. **Tim asisten Anda** — mock 3 kartu asisten bertumpuk (ilustrasi statis).
  3. **Tugas selesai saat Anda tidur** — mock kartu tugas → dokumen.
- Tombol slide 1–2: `Lanjut`; slide 3: `Mulai sekarang` → `/register`. `Lewati` kanan atas (caption) di slide 1–2.
- Panggilan suara Realtime = **Tahap 2**. Di slide fitur, beri badge `Segera hadir` (pill abu `#EEF3FF`/`faint`)
  pada item yang belum aktif di build Tahap 1, dan tombol `Beri tahu saya` → sheet **daftar tunggu**
  (`POST /api/waitlist {feature, email}` — endpoint belum ada, lihat §9).
- Transisi keluar: fade 200ms ke layar auth.
- testID: `onb-slide-{0..2}`, `onb-next-btn`, `onb-skip-btn`, `onb-login-btn`, `onb-lang-toggle`, `onb-dot-{i}`, `onb-waitlist-btn`.

## 5. Layar 2 — Login / Daftar / Lupa password (`/login`)

Satu layar, 3 mode (`login | register | forgot`) seperti `pages/Auth.jsx` web. `KeyboardAvoidingView` +
`ScrollView keyboardShouldPersistTaps="handled"`.

```
┌─────────────────────────────┐
│███ navy header 34% tinggi ██│  mark 40 + "Oryntix" 22/700 putih
│███  Intelligence,        ███│  tagline caption #A3AFC9
│███  Orchestrated.        ███│  [ID|EN] kanan atas
│ ╭───────────────────────╮   │  kartu putih radius 28, margin-top -28 (overlap)
│ │ Masuk            h1   │   │
│ │ Lanjutkan dengan akun │   │  bodySm muted
│ │ 🎁 Gratis 700 kredit  │   │  (mode register) pill blueSoft
│ │ [G  Masuk dgn Google] │   │  soft button h52
│ │ ──  atau dengan email │   │  caption uppercase, garis line
│ │ [👤 Nama           ]  │   │  (register)
│ │ [✉  Email          ]  │   │
│ │ [🔒 Password     👁 ] │   │
│ │ [🔒 Ulangi Password]  │   │  (register) error inline bila beda
│ │           Lupa password?│ │  ghost kanan
│ │ [       Masuk       ] │   │  primary
│ │ Belum punya akun? Daftar│ │
│ │ Dengan masuk … Ketentuan│ │  caption + 2 link biru
│ ╰───────────────────────╯   │
└─────────────────────────────┘
```

Spesifikasi perilaku:
- **Validasi**: email regex, password ≥6, konfirmasi harus sama (tombol submit disabled + `auth-confirm-error`).
- **Loading**: tombol primary → spinner 18dp + teks `Memproses…`, input disabled.
- **Error API**: toast + banner inline di dalam kartu (bg `#FEF2F2`, teks `danger`).
- **Belum verifikasi** (login 403 `code:"unverified"`): banner amber `#FFFBEB` + tombol `Kirim ulang tautan`.
- **Setelah register / forgot**: layar penuh `PendingScreen` — ikon mail dalam bulatan 64 `blueSoft`,
  judul `Cek email Anda`, email di-bold, tombol `Kirim ulang tautan`, link `Masuk`.
- **Google**: `expo-auth-session/providers/google` → `POST /api/auth/google/mobile {id_token}`.
- **Deep link** verifikasi/reset: `oryntix://verify-email?token=` & `oryntix://reset-password?token=`
  (universal link `https://oryntix.com/...` juga).
- Token JWT → `expo-secure-store`; biometrik (`expo-local-authentication`) opsional Tahap 1.5: toggle
  `Buka dengan Face ID / sidik jari` di Profil, bukan di login pertama.
- testID: `auth-title`, `auth-google-btn`, `auth-name-input`, `auth-email-input`, `auth-password-input`,
  `auth-confirm-input`, `auth-confirm-error`, `auth-toggle-show`, `auth-forgot-btn`, `auth-submit-btn`,
  `auth-toggle-btn`, `auth-back-login`, `auth-terms-link`, `auth-privacy-link`, `verify-pending`,
  `verify-resend-btn`, `login-unverified`.

## 6. Layar 3 — Home / Dashboard (`/home`, tab 1)

Light background `#F4F6FB`, `FlatList`/`ScrollView` dengan `RefreshControl` (tint `blue`).
Urutan blok mengikuti web `Home.jsx` tapi disusun vertikal, 1 kolom:

```
┌─────────────────────────────┐  header (sticky, bg bg + blur 18 saat scroll)
│ ◍ Selamat pagi,   [1.240 ⚡]🔔│  avatar 40 → Profil; pill kredit → /wallet; bell badge merah
│   Andi                      │
├─────────────────────────────┤
│ ╭ Oryntix siap membantu ─╮  │  (A) Kartu Support Agent — bg gradient biru/ungu 8%
│ │ ◍  Tanya apa pun  [Chat]│  │  tombol Chat (solid) + ikon Panggil / Video (soft, 44dp)
│ ╰─────────────────────────╯  │
│ ╭ hero gradient ──────────╮  │  (B) Hero: "Ubah ide jadi hasil nyata."
│ │ Ubah ide jadi hasil     │  │  h1 ink, bodySm muted
│ │ [Mulai Chat] [Panggilan]│  │  primary + soft
│ ╰─────────────────────────╯  │
│ Pintasan                    │  (C) 4 tile: Chat, Tugas, Galeri, Kalender
│ [▢][▢][▢][▢]               │  kartu 1:1, ikon 22 biru dlm bulatan blueSoft, label 12/600
│ ┌ Statistik ──────────────┐ │  (D) 2×2 stat: Tugas aktif, Asisten, Dokumen, Kredit hari ini
│ │ 3 Tugas │ 5 Asisten     │ │  angka h1, label caption
│ ├ Asisten Anda   Lihat ›  ┤ │  (E) 3 ListRow + tombol + (admin) → /personas/new
│ ├ Aktivitas terbaru       ┤ │  (F) 3 item: ikon status + judul + waktu relatif
│ ├ Agenda hari ini         ┤ │  (G) pengingat/kalender ≤3, tombol "Buka Kalender"
│ ╰ Trial: 4 hari lagi  [↑] ╯ │  (H) banner trial / promo upgrade (gradient navy→blue)
└─────────────────────────────┘
│  ◉ Beranda  ◌ Chat  ◌ Tugas  ◌ Galeri  ◌ Profil │  tab bar
```

Detail:
- **Greeting** dinamis per jam (Selamat pagi/siang/sore/malam) + nama depan.
- **Kartu kredit/trial** hanya untuk role `admin` (pemilik workspace) — sama dengan gating web
  (anggota biasa tidak melihat kredit, Pintasan tanpa "Tugas baru" bila tidak berhak).
- **Skeleton** saat load: header asli + 1 hero skeleton + 2 kartu skeleton; **jangan** spinner full-screen.
- **Empty state** bila belum ada asisten: kartu "Buat asisten pertama Anda" dengan tombol primary
  (admin) atau "Mulai chat dengan Oryntix" (anggota).
- **Fitur Tahap 2** (panggilan suara Realtime, panggilan teman, video avatar): tombol tetap terlihat tapi
  diberi pill `Segera hadir`; tap → sheet daftar tunggu, bukan error.
- testID: `home-page`, `home-greeting`, `home-credit-pill`, `home-notif-btn`, `home-support-chat`,
  `home-support-call`, `home-hero`, `home-start-chat`, `qa-chat|qa-tasks|qa-gallery|qa-calendar`,
  `home-agents`, `home-persona-{id}`, `home-activity`, `home-agenda`, `home-trial-banner`,
  `tab-home|tab-chat|tab-tasks|tab-gallery|tab-profile`.

## 7. Navigasi & shell

- `expo-router` / React Navigation: stack `auth` (welcome, login, verify, reset) dan stack `app` (tabs).
- **Bottom tabs (5)**: Beranda, Chat (badge `unread_chats`), Tugas, Galeri, Profil.
  Tinggi 56 + safe-area inset bawah; bg putih, border atas `line`; ikon aktif `blue` + label 11.5/700,
  non-aktif `#8A95AD` tanpa label (atau label abu — pilih satu, konsisten).
  Menu lain (Kalender, Teman, Pengingat, Kredit, Integrasi, Arsip) ada di **Profil** sebagai daftar.
- Android: back handler → tab Beranda sebelum keluar; `StatusBar` light di layar navy, dark di layar terang
  (`expo-status-bar` per screen).
- iOS: hormati `useSafeAreaInsets`; tanpa header besar ala iOS (pakai header kustom di §6).
- Haptics ringan (`expo-haptics` `Light`) pada tombol primary & terima/tolak panggilan.

## 8. i18n (ID default, EN kedua)

Satu file `i18n/{id,en}.ts`; `settings.app_language` dari `GET /api/auth/me` menimpa pilihan lokal.
Contoh kunci untuk 3 layar ini:

| key | ID | EN |
|---|---|---|
| `onb.title1` | Asisten AI pribadi Anda | Your personal AI assistant |
| `onb.cta` | Mulai | Get started |
| `onb.haveAccount` | Sudah punya akun? Masuk | Already have an account? Sign in |
| `onb.soon` | Segera hadir | Coming soon |
| `onb.notify` | Beri tahu saya | Notify me |
| `auth.login` | Masuk | Sign in |
| `auth.register` | Daftar | Sign up |
| `auth.google` | Masuk dengan Google | Continue with Google |
| `auth.orEmail` | atau dengan email | or with email |
| `auth.forgot` | Lupa password? | Forgot password? |
| `auth.confirm` | Ulangi Password | Repeat password |
| `auth.legal` | Dengan masuk atau mendaftar, Anda menyetujui {terms} dan {privacy}. | By continuing you agree to {terms} and {privacy}. |
| `home.greetMorning` | Selamat pagi | Good morning |
| `home.shortcuts` | Pintasan | Shortcuts |
| `home.yourAgents` | Asisten Anda | Your assistants |
| `home.recent` | Aktivitas terbaru | Recent activity |
| `home.agenda` | Agenda hari ini | Today's agenda |
| `home.credits` | kredit | credits |

Aturan: angka/tanggal via `Intl` dengan locale aktif (`id-ID` → `1.240`, `10.30`), zona waktu dari
`settings.timezone`. Teks tombol maksimum 18 karakter agar tidak terpotong di EN.

## 9. Daftar tunggu "Segera hadir" (perlu backend kecil)

Belum ada endpoint. Usulan minimal (dikerjakan di project web/backend ini bila disetujui):
`POST /api/waitlist {feature: "voice_call"|"video_avatar"|"mobile_release", email?}` → simpan ke koleksi
`waitlist {user_id?, email, feature, created_at}`; respons `{ok:true}`. Sebelum itu, tombol `Beri tahu saya`
cukup menyimpan lokal + toast "Kami beri tahu saat fitur ini aktif."

## 10. Aksesibilitas & QA

- Kontras: teks `muted` di atas `bg` = 4.6:1 (lolos AA); jangan pakai `faint` untuk teks penting.
- Semua target tap ≥44×44; `accessibilityLabel` ID+EN; `accessibilityRole="button"`.
- Uji: iPhone SE (375×667), iPhone 15 Pro, Pixel 7, tablet 10" (kartu maks lebar 560, konten di tengah).
- Uji font OS 130%, mode hemat daya (matikan animasi bila `AccessibilityInfo.isReduceMotionEnabled`).
- Akun uji: `demo@aivora.ai / demo123456`.

## 11. Aset yang dibutuhkan

| Aset | Sumber |
|---|---|
| App icon 1024², adaptive icon Android (fg+bg `#0A1128`) | `frontend/public/brand/mark-512.png` |
| Splash (navy + mark 160dp, `resizeMode: contain`) | mark |
| Logo putih horizontal (header login) | `brand/logo-white.webp` |
| Ilustrasi 3 slide onboarding | buat baru (vector, palet token) |
| Font Plus Jakarta Sans + JetBrains Mono | `@expo-google-fonts/*` |

---
Status: dokumen desain saja — **belum ada kode mobile yang ditulis**. Pasangkan dengan
`/app/memory/MOBILE_BRIEF.md` (kontrak API & tahapan) saat memulai job mobile.
