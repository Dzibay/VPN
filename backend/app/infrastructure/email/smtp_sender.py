"""Отправка транзакционных писем через SMTP (stdlib, в threadpool)."""

from __future__ import annotations

import logging
import smtplib
import socket
from email.message import EmailMessage
from email.utils import formataddr

from app.config import Settings

log = logging.getLogger("app.smtp")


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

    msg = EmailMessage()
    msg["From"] = _from_address(cfg)
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Auto-Submitted"] = "auto-generated"
    reply_to = (cfg.smtp_from_email or cfg.smtp_user or "").strip()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

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


def send_verification_email_sync(cfg: Settings, *, to_email: str, verify_url: str) -> None:
    brand = (cfg.smtp_from_name or cfg.app_name or "VPN").strip()
    subject = f"Подтверждение регистрации — {brand}"
    text = (
        "Здравствуйте!\n\n"
        "Для завершения регистрации перейдите по ссылке:\n"
        f"{verify_url}\n\n"
        "Если вы не регистрировались на сайте — просто проигнорируйте это письмо.\n"
    )
    html = (
        "<p>Здравствуйте!</p>"
        "<p>Для завершения регистрации нажмите кнопку:</p>"
        f'<p><a href="{verify_url}" style="display:inline-block;padding:10px 18px;'
        'background:#1D9A5C;color:#fff;text-decoration:none;border-radius:8px;">'
        "Подтвердить email</a></p>"
        f'<p>Или перейдите по ссылке: <a href="{verify_url}">{verify_url}</a></p>'
        "<p>Если вы не регистрировались — проигнорируйте это письмо.</p>"
    )
    send_email_sync(cfg, to_email=to_email, subject=subject, text_body=text, html_body=html)
    log.info("verification email sent to %s", to_email)
