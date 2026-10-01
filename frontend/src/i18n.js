import React, { createContext, useContext, useState } from "react";

const DICT = {
  id: {
    "nav.home": "Beranda", "nav.personas": "Persona", "nav.chat": "Chat",
    "nav.workspace": "Ruang Kerja", "nav.reminders": "Pengingat", "nav.wallet": "Kredit",
    "nav.profile": "Profil", "nav.admin": "Admin", "nav.logout": "Keluar",
    "common.loading": "Memuat...", "common.save": "Simpan", "common.cancel": "Batal",
    "common.delete": "Hapus", "common.create": "Buat", "common.credits": "kredit",
    "common.back": "Kembali", "common.search": "Cari...", "common.send": "Kirim",
    "auth.welcome": "Selamat datang di Aivora", "auth.tagline": "Asisten AI Anda, di sisi Anda.",
    "auth.login": "Masuk", "auth.register": "Daftar", "auth.email": "Email",
    "auth.password": "Kata sandi", "auth.name": "Nama", "auth.noAccount": "Belum punya akun?",
    "auth.hasAccount": "Sudah punya akun?",
    "home.greeting": "Halo", "home.quick": "Aksi Cepat", "home.newPersona": "Buat Persona",
    "home.delegate": "Delegasikan Tugas", "home.startChat": "Mulai Chat",
    "home.running": "Tugas Berjalan", "home.recent": "Hasil Terbaru", "home.wallet": "Ringkasan Kredit",
    "home.empty": "Belum ada aktivitas. Mulai dengan membuat persona atau memberi tugas pada Aivora.",
    "persona.create": "Buat Persona Anda", "persona.describe": "Deskripsikan dengan AI",
    "persona.photo": "Unggah Foto", "persona.combine": "Gabungan",
    "chat.placeholder": "Tulis pesan...", "chat.new": "Chat Baru",
    "work.delegate": "Beri tujuan untuk Aivora kerjakan...", "work.goal": "Tujuan",
    "wallet.balance": "Saldo Kredit", "wallet.topup": "Isi Ulang", "wallet.history": "Riwayat Transaksi",
    "reminders.new": "Pengingat Baru", "reminders.title": "Judul", "reminders.when": "Waktu Mulai",
    "reminders.before": "Ingatkan sebelum", "common.minutes": "menit",
  },
  en: {
    "nav.home": "Home", "nav.personas": "Personas", "nav.chat": "Chat",
    "nav.workspace": "Workspace", "nav.reminders": "Reminders", "nav.wallet": "Credits",
    "nav.profile": "Profile", "nav.admin": "Admin", "nav.logout": "Log out",
    "common.loading": "Loading...", "common.save": "Save", "common.cancel": "Cancel",
    "common.delete": "Delete", "common.create": "Create", "common.credits": "credits",
    "common.back": "Back", "common.search": "Search...", "common.send": "Send",
    "auth.welcome": "Welcome to Aivora", "auth.tagline": "Your AI, in your corner.",
    "auth.login": "Sign in", "auth.register": "Sign up", "auth.email": "Email",
    "auth.password": "Password", "auth.name": "Name", "auth.noAccount": "No account yet?",
    "auth.hasAccount": "Already have an account?",
    "home.greeting": "Hello", "home.quick": "Quick Actions", "home.newPersona": "Create Persona",
    "home.delegate": "Delegate a Task", "home.startChat": "Start Chat",
    "home.running": "Running Tasks", "home.recent": "Recent Outputs", "home.wallet": "Credit Summary",
    "home.empty": "No activity yet. Start by creating a persona or giving Aivora a task.",
    "persona.create": "Create Your Persona", "persona.describe": "Describe with AI",
    "persona.photo": "Upload a Photo", "persona.combine": "Combine Both",
    "chat.placeholder": "Type a message...", "chat.new": "New Chat",
    "work.delegate": "Give Aivora a goal to work on...", "work.goal": "Goal",
    "wallet.balance": "Credit Balance", "wallet.topup": "Top up", "wallet.history": "Transaction History",
    "reminders.new": "New Reminder", "reminders.title": "Title", "reminders.when": "Start time",
    "reminders.before": "Remind before", "common.minutes": "min",
  },
};

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(localStorage.getItem("aivora_lang") || "id");
  const change = (l) => { setLang(l); localStorage.setItem("aivora_lang", l); };
  const t = (key) => (DICT[lang] && DICT[lang][key]) || (DICT.en[key]) || key;
  return <I18nContext.Provider value={{ lang, setLang: change, t }}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
