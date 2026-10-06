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
