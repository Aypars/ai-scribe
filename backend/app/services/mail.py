"""Transactional email via SMTP."""

from __future__ import annotations

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class MailError(Exception):
    pass


def smtp_configured() -> bool:
    return bool(settings.smtp_host.strip())


def _from_header() -> str:
    return (settings.smtp_from or settings.smtp_user or "ai-scribe@localhost").strip()


def send_mail(*, to: str, subject: str, text: str, html_body: str) -> None:
    if not smtp_configured():
        raise MailError("SMTP ayarlı değil")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = to
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")

    host = settings.smtp_host.strip()
    port = settings.smtp_port
    user = settings.smtp_user.strip()
    password = settings.smtp_password
    timeout = 20

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(message)
            return
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
    except Exception as exc:
        logger.exception("SMTP send failed")
        raise MailError("E-posta gönderilemedi") from exc


def _reset_email_html(reset_url: str) -> str:
    safe = html.escape(reset_url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="tr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light" />
    <title>Şifreni yenile</title>
  </head>
  <body style="margin:0;padding:0;background-color:#e7f3f1;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
      Yeni şifre belirlemek için 1 saatlik bağlantı.
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#e7f3f1" style="background-color:#e7f3f1;padding:40px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;">
            <tr>
              <td style="padding:0 4px 18px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;letter-spacing:0.22em;font-size:12px;font-weight:700;color:#0f766e;">
                AI-SCRIBE
              </td>
            </tr>
            <tr>
              <td bgcolor="#ffffff" style="background-color:#ffffff;border:1px solid #b6ddd8;border-radius:16px;overflow:hidden;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td bgcolor="#0f766e" height="6" style="background-color:#0f766e;font-size:0;line-height:0;">&nbsp;</td>
                  </tr>
                  <tr>
                    <td style="padding:32px 28px 28px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
                      <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#0f766e;">Hesap güvenliği</p>
                      <h1 style="margin:0 0 14px;font-size:24px;line-height:1.3;font-weight:700;color:#134e4a;">Şifreni yenile</h1>
                      <p style="margin:0 0 24px;font-size:15px;line-height:1.65;color:#334155;">
                        AI-SCRIBE hesabın için şifre sıfırlama istendi. Yeni şifreni aşağıdan belirle.
                        Bu bağlantı <strong>1 saat</strong> sonra geçersiz olur.
                      </p>
                      <table role="presentation" cellspacing="0" cellpadding="0">
                        <tr>
                          <td bgcolor="#0f766e" style="border-radius:10px;background-color:#0f766e;">
                            <a href="{safe}" style="display:inline-block;padding:14px 24px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;">
                              Yeni şifre belirle
                            </a>
                          </td>
                        </tr>
                      </table>
                      <p style="margin:28px 0 8px;font-size:12px;line-height:1.55;color:#64748b;">
                        Buton çalışmazsa bu adresi tarayıcıya yapıştır:
                      </p>
                      <p style="margin:0;word-break:break-all;font-size:12px;line-height:1.5;color:#0f766e;">
                        {safe}
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 8px 0;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:12px;line-height:1.6;color:#64748b;">
                Bu isteği sen yapmadıysan maili yok say. Şifren değişmez.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_password_reset(to: str, reset_url: str) -> None:
    text = (
        "AI-SCRIBE\n\n"
        "Hesabın için şifre sıfırlama istendi.\n"
        "Yeni şifreni belirlemek için bağlantıyı aç (1 saat geçerli):\n\n"
        f"{reset_url}\n\n"
        "Bu isteği sen yapmadıysan bu postayı yok say. Şifren değişmez."
    )
    send_mail(
        to=to,
        subject="AI-SCRIBE — şifreni yenile",
        text=text,
        html_body=_reset_email_html(reset_url),
    )
