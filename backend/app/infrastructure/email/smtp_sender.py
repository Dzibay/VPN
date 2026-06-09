"""Отправка транзакционных писем через SMTP (stdlib, в threadpool)."""

from __future__ import annotations

import logging
import smtplib
import socket
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from app.config import Settings
from app.domain.public_urls import public_spa_base_url

log = logging.getLogger("app.smtp")

_LOGO_CID = "podorozhnik-logo"
_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "podorozhnik-logo.png"


class SmtpDeliveryError(RuntimeError):
    """Ошибка доставки письма через SMTP (с понятным сообщением для API)."""


def smtp_configured(cfg: Settings) -> bool:
    return bool((cfg.smtp_host or "").strip())


def smtp_delivery_error_message(exc: BaseException, *, host: str, port: int) -> str:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return (
            f"Не удалось подключиться к SMTP-серверу {host}:{port} (таймаут). "
            "На Timeweb Cloud исходящие почтовые порты (25, 465, 587, 2525) часто "
            "заблокированы — разблокируйте их в панели сервера или через поддержку. "
            "На серверах с Wireguard разблокировка может быть недоступна; тогда используйте "
            "внешний почтовый API (HTTPS) или отдельный SMTP-релей."
        )
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in {111, 10061}:
        return (
            f"SMTP-сервер {host}:{port} отклонил соединение. "
            "Проверьте SMTP_PORT/SMTP_USE_SSL/SMTP_USE_TLS и доступность порта с сервера API."
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Ошибка авторизации SMTP: проверьте SMTP_USER (полный email) и SMTP_PASSWORD."
    return f"Не удалось отправить письмо через SMTP ({host}:{port}): {exc}"


def _from_address(cfg: Settings) -> str:
    addr = (cfg.smtp_from_email or cfg.smtp_user or "noreply@localhost").strip()
    name = (cfg.smtp_from_name or cfg.app_name or "VPN").strip()
    return formataddr((name, addr))


def _logo_src(cfg: Settings) -> tuple[str, bytes | None]:
    """(src для <img>, байты PNG для CID) — вложение предпочтительнее внешней ссылки."""
    if _LOGO_PATH.is_file():
        return f"cid:{_LOGO_CID}", _LOGO_PATH.read_bytes()
    base = public_spa_base_url(cfg)
    if base:
        return f"{base}/icons/podorozhnik-logo.png", None
    return "", None


def _build_email_message(
    cfg: Settings,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None,
) -> MIMEMultipart:
    msg = MIMEMultipart("related")
    msg["From"] = _from_address(cfg)
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Auto-Submitted"] = "auto-generated"
    reply_to = (cfg.smtp_from_email or cfg.smtp_user or "").strip()
    if reply_to:
        msg["Reply-To"] = reply_to

    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        alt.attach(MIMEText(html_body, "html", "utf-8"))

    _, logo_bytes = _logo_src(cfg)
    if logo_bytes is not None:
        img = MIMEImage(logo_bytes, _subtype="png")
        img.add_header("Content-ID", f"<{_LOGO_CID}>")
        img.add_header("Content-Disposition", "inline", filename="podorozhnik-logo.png")
        msg.attach(img)
    return msg


def send_email_sync(
    cfg: Settings,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    host = (cfg.smtp_host or "").strip()
    if not host:
        raise RuntimeError("SMTP не настроен (smtp_host пуст)")

    msg = _build_email_message(
        cfg,
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

    user = (cfg.smtp_user or "").strip() or None
    password = cfg.smtp_password or None
    port = int(cfg.smtp_port)

    try:
        if cfg.smtp_use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return

        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if cfg.smtp_use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
    except Exception as e:
        raise SmtpDeliveryError(smtp_delivery_error_message(e, host=host, port=port)) from e


def _verification_html(cfg: Settings, *, brand: str, verify_url: str) -> str:
    logo_src, _ = _logo_src(cfg)
    logo_block = ""
    if logo_src:
        logo_block = (
            f'<p style="margin:0 0 20px;text-align:center;">'
            f'<img src="{logo_src}" alt="{brand}" width="72" height="72" '
            'style="display:inline-block;width:72px;height:72px;border-radius:16px;" />'
            f"</p>"
        )
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
        'color:#111827;line-height:1.5;max-width:520px;">'
        f"{logo_block}"
        "<p style=\"margin:0 0 12px;\">Здравствуйте!</p>"
        "<p style=\"margin:0 0 16px;\">Для завершения регистрации нажмите кнопку:</p>"
        f'<p style="margin:0 0 20px;text-align:center;">'
        f'<a href="{verify_url}" style="display:inline-block;padding:12px 22px;'
        "background:#2563eb;color:#ffffff;text-decoration:none;border-radius:10px;"
        'font-weight:600;">Подтвердить email</a></p>'
        f'<p style="margin:0 0 8px;font-size:14px;color:#6b7280;">'
        f'Или перейдите по ссылке: <a href="{verify_url}">{verify_url}</a></p>'
        '<p style="margin:16px 0 0;font-size:14px;color:#6b7280;">'
        "Если вы не регистрировались — проигнорируйте это письмо.</p>"
        "</div>"
    )


def send_verification_email_sync(cfg: Settings, *, to_email: str, verify_url: str) -> None:
    brand = (cfg.smtp_from_name or cfg.app_name or "VPN").strip()
    subject = f"Подтверждение регистрации — {brand}"
    text = (
        "Здравствуйте!\n\n"
        "Для завершения регистрации перейдите по ссылке:\n"
        f"{verify_url}\n\n"
        "Если вы не регистрировались на сайте — просто проигнорируйте это письмо.\n"
    )
    html = _verification_html(cfg, brand=brand, verify_url=verify_url)
    send_email_sync(cfg, to_email=to_email, subject=subject, text_body=text, html_body=html)
    log.info("verification email sent to %s", to_email)
