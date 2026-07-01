"""Отправка транзакционных писем через SMTP (stdlib, в threadpool)."""

from __future__ import annotations

import logging
import smtplib
import socket
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from app.config import Settings
from app.domain.tenant.project_context import get_current_project

log = logging.getLogger("app.smtp")


class SmtpDeliveryError(RuntimeError):
    """Ошибка доставки письма через SMTP (с понятным сообщением для API)."""


@dataclass(frozen=True)
class _SmtpRuntimeConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str
    smtp_from_name: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    app_name: str


def _smtp_bool(settings: dict, key: str, default: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _resolved_smtp_config(cfg: Settings) -> _SmtpRuntimeConfig:
    project = get_current_project()
    p = project.smtp_settings if project and isinstance(project.smtp_settings, dict) else {}
    host = str(p.get("host") or cfg.smtp_host or "").strip()
    user = str(p.get("username") or p.get("user") or cfg.smtp_user or "").strip()
    from_email = str(p.get("from_email") or cfg.smtp_from_email or user or "").strip()
    from_name = str(p.get("from_name") or cfg.smtp_from_name or cfg.app_name or "VPN").strip()
    return _SmtpRuntimeConfig(
        smtp_host=host,
        smtp_port=int(p.get("port") or cfg.smtp_port),
        smtp_user=user,
        smtp_password=str(p.get("password") or cfg.smtp_password or ""),
        smtp_from_email=from_email,
        smtp_from_name=from_name,
        smtp_use_tls=_smtp_bool(p, "use_tls", bool(cfg.smtp_use_tls)),
        smtp_use_ssl=_smtp_bool(p, "use_ssl", bool(cfg.smtp_use_ssl)),
        app_name=cfg.app_name,
    )


def smtp_configured(cfg: Settings) -> bool:
    return bool((_resolved_smtp_config(cfg).smtp_host or "").strip())


def smtp_configured_in_env(cfg: Settings) -> bool:
    """Startup-check helper: at import time there is no request project context."""
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


def _message_id_domain(from_header: str) -> str | None:
    _, addr = parseaddr(from_header)
    mail = (addr or "").strip()
    if "@" not in mail:
        return None
    return mail.rsplit("@", 1)[-1]


def _build_email_message(
    cfg: Settings,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> EmailMessage:
    from_header = _from_address(cfg)
    msg = EmailMessage()
    msg["From"] = from_header
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=_message_id_domain(from_header))
    msg["Auto-Submitted"] = "auto-generated"
    msg["Content-Language"] = "ru"
    reply_to = (cfg.smtp_from_email or cfg.smtp_user or "").strip()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body, charset="utf-8")
    if html_body:
        msg.add_alternative(html_body, subtype="html", charset="utf-8")
    return msg


def send_email_sync(
    cfg: Settings,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    smtp_cfg = _resolved_smtp_config(cfg)
    host = (smtp_cfg.smtp_host or "").strip()
    if not host:
        raise RuntimeError("SMTP не настроен (smtp_host пуст)")

    msg = _build_email_message(
        smtp_cfg,
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

    user = (smtp_cfg.smtp_user or "").strip() or None
    password = smtp_cfg.smtp_password or None
    port = int(smtp_cfg.smtp_port)

    try:
        if smtp_cfg.smtp_use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return

        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if smtp_cfg.smtp_use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
    except Exception as e:
        raise SmtpDeliveryError(smtp_delivery_error_message(e, host=host, port=port)) from e


def send_verification_email_sync(cfg: Settings, *, to_email: str, verify_url: str) -> None:
    smtp_cfg = _resolved_smtp_config(cfg)
    brand = (smtp_cfg.smtp_from_name or cfg.app_name or "VPN").strip()
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
        'background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;">'
        "Подтвердить email</a></p>"
        f'<p>Или перейдите по ссылке: <a href="{verify_url}">{verify_url}</a></p>'
        "<p>Если вы не регистрировались — проигнорируйте это письмо.</p>"
    )
    send_email_sync(cfg, to_email=to_email, subject=subject, text_body=text, html_body=html)
    log.info("verification email sent to %s", to_email)
