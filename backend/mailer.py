import logging
import os
from email.message import EmailMessage
from html import escape

import aiosmtplib

log = logging.getLogger("aivora")
BRAND = "Oryntix"


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def debug_links(request=None) -> bool:
    """Debug links (raw tokens in API responses) are ONLY ever shown on preview/local hosts, even if the flag leaks into production."""
    if os.environ.get("EMAIL_DEBUG_LINKS", "").lower() != "true":
        return False
    if request is None:
        return False
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip().split(":")[0].lower()
    return host.endswith(".preview.emergentagent.com") or host in ("localhost", "127.0.0.1")


async def send_email(to: str, subject: str, html: str, text: str) -> bool:
    if not configured():
        log.warning("SMTP not configured — email to %s skipped (%s)\n%s", to, subject, text)
        return False
    port = int(os.environ.get("SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["From"] = f"{os.environ.get('SMTP_FROM_NAME') or BRAND} <{os.environ.get('SMTP_FROM') or os.environ['SMTP_USER']}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        await aiosmtplib.send(msg, hostname=os.environ["SMTP_HOST"], port=port, username=os.environ["SMTP_USER"],
                              password=os.environ["SMTP_PASSWORD"], use_tls=port == 465, start_tls=port != 465, timeout=20)
        return True
    except Exception as e:
        log.error("SMTP send to %s failed: %s", to, e)
        return False


def _layout(title: str, body: str, cta: str, link: str, footer: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#0a0f1f;font-family:Segoe UI,Arial,sans-serif;padding:32px 16px">
<table role="presentation" width="100%" style="max-width:520px;margin:0 auto;background:#111a33;border-radius:16px;color:#fff">
<tr><td style="padding:32px 32px 8px"><p style="margin:0;font-size:22px;font-weight:700;letter-spacing:.3px">{BRAND}</p></td></tr>
<tr><td style="padding:8px 32px"><h2 style="margin:0 0 12px;font-size:20px">{title}</h2>
<p style="margin:0;font-size:15px;line-height:1.6;color:rgba(255,255,255,.8)">{body}</p></td></tr>
<tr><td style="padding:24px 32px"><a href="{link}" style="display:inline-block;background:linear-gradient(90deg,#2F6BFF,#7C3AED);color:#fff;text-decoration:none;font-weight:700;padding:14px 26px;border-radius:12px;font-size:15px">{cta}</a>
<p style="margin:16px 0 0;font-size:12px;color:rgba(255,255,255,.5);word-break:break-all">Atau salin tautan ini: {link}</p></td></tr>
<tr><td style="padding:8px 32px 32px;font-size:12px;color:rgba(255,255,255,.45)">{footer}</td></tr></table></body></html>"""


def verification_email(name: str, link: str) -> tuple:
    n = escape(name or "")
    subject = f"Verifikasi email Anda — {BRAND}"
    body = f"Halo {n}, terima kasih sudah mendaftar. Klik tombol di bawah untuk memverifikasi alamat email dan mulai menggunakan workspace {BRAND} Anda."
    html = _layout("Verifikasi email Anda", body, "Verifikasi Email", link, "Jika Anda tidak mendaftar, abaikan email ini.")
    text = f"Halo {name},\n\nVerifikasi email Anda untuk mulai menggunakan {BRAND}:\n{link}\n\nJika Anda tidak mendaftar, abaikan email ini."
    return subject, html, text


def reset_email(name: str, link: str) -> tuple:
    n = escape(name or "")
    subject = f"Atur ulang password — {BRAND}"
    body = f"Halo {n}, kami menerima permintaan untuk mengatur ulang password akun {BRAND} Anda. Klik tombol di bawah untuk membuat password baru. Tautan berlaku 1 jam."
    html = _layout("Atur ulang password", body, "Buat Password Baru", link, "Jika Anda tidak meminta ini, abaikan email ini — password Anda tidak berubah.")
    text = f"Halo {name},\n\nAtur ulang password {BRAND} Anda lewat tautan berikut (berlaku 1 jam):\n{link}\n\nJika Anda tidak meminta ini, abaikan email ini."
    return subject, html, text


def friend_request_email(inviter: str, link: str) -> tuple:
    i = escape(inviter or BRAND)
    subject = f"{inviter} ingin berteman dengan Anda — {BRAND}"
    body = f"{i} mengirim permintaan pertemanan di {BRAND}. Setelah Anda setujui, kalian bisa chat dan berbagi grup bersama asisten AI."
    html = _layout("Permintaan pertemanan", body, "Lihat Permintaan", link, "Anda bisa menerima atau menolak permintaan ini dari menu Teman.")
    text = f"{inviter} ingin berteman dengan Anda di {BRAND}.\nLihat permintaan di: {link}"
    return subject, html, text


def friend_invite_email(inviter: str, link: str) -> tuple:
    i = escape(inviter or BRAND)
    subject = f"{inviter} mengajak Anda bergabung di {BRAND}"
    body = f"{i} ingin berteman dengan Anda di {BRAND} — platform asisten AI pribadi. Daftar gratis dengan alamat email ini; permintaan pertemanannya otomatis menunggu Anda."
    html = _layout("Ajakan bergabung", body, "Daftar Sekarang", link, "Gunakan alamat email yang sama saat mendaftar agar permintaan pertemanan langsung muncul.")
    text = f"{inviter} mengajak Anda bergabung di {BRAND}.\nDaftar di: {link}"
    return subject, html, text


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def efaktur_reminder_email(count: int, total_ppn: int, items: list, link: str) -> tuple:
    subject = f"{count} pengeluaran menunggu e-faktur — {BRAND}"
    rows = "".join(
        f"<tr><td style='padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.07);font-size:13px'>{escape(str(e.get('date', '')))} · {escape(str(e.get('vendor', '')))}</td>"
        f"<td style='padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.07);font-size:13px;text-align:right;color:#8fb4ff'>{_rp(e.get('ppn_idr', 0))}</td></tr>"
        for e in items[:20]
    )
    html = f"""<!doctype html><html><body style="margin:0;background:#0a0f1f;font-family:Segoe UI,Arial,sans-serif;padding:32px 16px">
<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#111a33;border-radius:16px;color:#fff">
<tr><td style="padding:28px 32px 4px"><table role="presentation"><tr><td style="width:36px;height:36px;background:linear-gradient(135deg,#2F6BFF,#7C3AED);border-radius:10px;text-align:center;font-weight:800;font-size:18px;color:#fff">O</td><td style="padding-left:10px;font-size:20px;font-weight:800">{BRAND}</td></tr></table></td></tr>
<tr><td style="padding:12px 32px 0"><h2 style="margin:0 0 10px;font-size:19px">Pengingat e-Faktur</h2>
<p style="margin:0;font-size:14px;line-height:1.6;color:rgba(255,255,255,.8)">Ada <b>{count}</b> pengeluaran kena PPN yang belum dilampiri e-faktur (total PPN masukan <b>{_rp(total_ppn)}</b>). Unggah e-faktur agar PPN masukan sah dikreditkan.</p></td></tr>
<tr><td style="padding:14px 32px 0"><table style="width:100%;border-collapse:collapse;background:rgba(255,255,255,.03);border-radius:10px">{rows}</table></td></tr>
<tr><td style="padding:22px 32px 8px"><a href="{link}" style="display:inline-block;background:linear-gradient(90deg,#2F6BFF,#7C3AED);color:#fff;text-decoration:none;font-weight:700;padding:13px 24px;border-radius:12px;font-size:14px">Buka Pengeluaran</a></td></tr>
<tr><td style="padding:8px 32px 30px;font-size:12px;color:rgba(255,255,255,.45)">Email otomatis dari back-office {BRAND}. Dikirim tiap akhir bulan.</td></tr></table></body></html>"""
    lines = "\n".join(f"- {e.get('date', '')} {e.get('vendor', '')}: PPN {_rp(e.get('ppn_idr', 0))}" for e in items[:20])
    text = f"{count} pengeluaran menunggu e-faktur (total PPN masukan {_rp(total_ppn)}).\n{lines}\n\nBuka Pengeluaran: {link}"
    return subject, html, text


def budget_alert_email(month: str, breaches: list, link: str) -> tuple:
    subject = f"Anggaran terlampaui ({month}) — {BRAND}"
    rows = "".join(
        f"<tr><td style='padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.07);font-size:13px'>{escape(str(label))}</td>"
        f"<td style='padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.07);font-size:13px;text-align:right'>Anggaran {_rp(b)}</td>"
        f"<td style='padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.07);font-size:13px;text-align:right;color:#ff8a8a'>Terpakai {_rp(s)}</td></tr>"
        for (label, b, s) in breaches
    )
    html = f"""<!doctype html><html><body style="margin:0;background:#0a0f1f;font-family:Segoe UI,Arial,sans-serif;padding:32px 16px">
<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#111a33;border-radius:16px;color:#fff">
<tr><td style="padding:28px 32px 4px"><table role="presentation"><tr><td style="width:36px;height:36px;background:linear-gradient(135deg,#2F6BFF,#7C3AED);border-radius:10px;text-align:center;font-weight:800;font-size:18px;color:#fff">O</td><td style="padding-left:10px;font-size:20px;font-weight:800">{BRAND}</td></tr></table></td></tr>
<tr><td style="padding:12px 32px 0"><h2 style="margin:0 0 10px;font-size:19px;color:#ff8a8a">⚠ Anggaran bulan {escape(month)} terlampaui</h2>
<p style="margin:0;font-size:14px;line-height:1.6;color:rgba(255,255,255,.8)">Pengeluaran bulan berjalan telah melewati ambang anggaran yang ditetapkan:</p></td></tr>
<tr><td style="padding:14px 32px 0"><table style="width:100%;border-collapse:collapse;background:rgba(255,255,255,.03);border-radius:10px">{rows}</table></td></tr>
<tr><td style="padding:22px 32px 8px"><a href="{link}" style="display:inline-block;background:linear-gradient(90deg,#2F6BFF,#7C3AED);color:#fff;text-decoration:none;font-weight:700;padding:13px 24px;border-radius:12px;font-size:14px">Tinjau Pengeluaran</a></td></tr>
<tr><td style="padding:8px 32px 30px;font-size:12px;color:rgba(255,255,255,.45)">Peringatan otomatis dari back-office {BRAND}.</td></tr></table></body></html>"""
    lines = "\n".join(f"- {label}: anggaran {_rp(b)}, terpakai {_rp(s)}" for (label, b, s) in breaches)
    text = f"Anggaran bulan {month} terlampaui:\n{lines}\n\nTinjau: {link}"
    return subject, html, text

