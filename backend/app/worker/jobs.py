"""
Задачи очереди установки ПО на VPN-узел.

Функции вызываются процессом RQ; путь задачи: ``app.worker.jobs.install_server_software``.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.core.time import utc_now
from app.domain.servers.reality_defaults import normalize_reality_spider_x
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.ssh.provision_ssh import ssh_run_script_with_user_fallback
from app.infrastructure.xray.xray_clients import (
    vless_client_uuids_csv_for_server,
    vless_clients_b64_for_server,
)
from app.infrastructure.xray.xray_dynamic_sync import try_dynamic_xray_client_sync
from app.infrastructure.xray.xray_stats_collect import collect_xray_traffic_for_server

log = logging.getLogger("worker.provision")

_SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
_REMOTE_SCRIPT = _SCRIPTS_DIR / "install_xray_on_remote.sh"
_REMOTE_SCRIPT_PARTS = (
    _SCRIPTS_DIR / "provision_common.sh",
    _SCRIPTS_DIR / "provision_cascade.sh",
    _SCRIPTS_DIR / "provision_vless.sh",
    _SCRIPTS_DIR / "provision_vless_grpc.sh",
    _SCRIPTS_DIR / "provision_vless_ws.sh",
    _SCRIPTS_DIR / "provision_vless_vk_cdn_xhttp.sh",
    _SCRIPTS_DIR / "provision_hysteria2.sh",
    _REMOTE_SCRIPT,
)


def _format_ssh_capture(stdout_t: str, stderr_t: str, *, limit: int = 14000) -> str:
    """
    Текст для исключения/логов. stderr в конце — иначе при обрезке [-N:] теряются ошибки,
    если stdout длинный (curl, install-release).
    """
    out = (stdout_t or "").strip()
    err = (stderr_t or "").strip()
    if not out and not err:
        return ""
    combined = out + ("\n--- stderr ---\n" + err if err else "")
    return combined if len(combined) <= limit else combined[-limit:]

ProvisionComponent = Literal[
    "all",
    "xray",
    "vless",
    "hysteria2",
    "prometheus",
    "fair_egress",
    "cleanup",
    "sync_clients",
]


def _remote_script_payload() -> str:
    """Собрать один self-contained bash payload из entrypoint и component scripts."""
    missing = [str(p) for p in _REMOTE_SCRIPT_PARTS if not p.is_file()]
    if missing:
        raise FileNotFoundError("Нет скриптов установки: " + ", ".join(missing))
    return "\n\n".join(p.read_text(encoding="utf-8") for p in _REMOTE_SCRIPT_PARTS)


def _parse_xray_meta(stdout: str) -> dict[str, str] | None:
    if "###XRAY_META###" not in stdout:
        return None
    try:
        block = stdout.split("###XRAY_META###", 1)[1].split("###END_META###", 1)[0]
    except IndexError:
        return None
    out: dict[str, str] = {}
    for line in block.strip().splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    if "private_key" not in out or "public_key" not in out:
        return None
    return out


def _persist_reality_keys(db: Session, server: Server, stdout: str) -> None:
    meta = _parse_xray_meta(stdout)
    if not meta:
        log.warning("Нет блока ###XRAY_META### в выводе SSH — ключи в БД не обновлены")
        return
    server.reality_private_key = meta["private_key"]
    server.reality_public_key = meta["public_key"]
    db.commit()


def _run_provision_command(server: Server) -> None:
    """Кастомная команда на машине воркера (перекрывает SSH+xray)."""
    env = os.environ.copy()
    env["SERVER_HOST"] = server.host
    env["SERVER_PORT"] = str(server.port)
    env["SERVER_ID"] = str(server.id)
    log.info("provision_command server_id=%s host=%s", server.id, server.host)
    subprocess.run(
        settings.provision_command.strip(),
        shell=True,
        check=True,
        env=env,
        timeout=settings.provision_subprocess_timeout,
    )


def _node_exporter_env_lines(*, force_install: bool | None) -> str:
    if force_install is True:
        ne_on = "1"
    elif force_install is False:
        ne_on = "0"
    else:
        ne_on = "1" if settings.provision_install_node_exporter else "0"
    lines = (
        f"export VPN_INSTALL_NODE_EXPORTER={ne_on}\n"
        f"export VPN_NODE_EXPORTER_VERSION={shlex.quote(settings.provision_node_exporter_version.strip() or '1.8.2')}\n"
        f"export VPN_NODE_EXPORTER_PORT={int(settings.provision_node_exporter_port)}\n"
        f"export VPN_NODE_EXPORTER_LISTEN_HOST={shlex.quote(settings.provision_node_exporter_listen_host.strip() or '0.0.0.0')}\n"
    )
    return lines


def _tls_sni_for_server(server: Server) -> str:
    return ((server.tls_sni or server.host or "").strip().rstrip("."))


def _google_routing_mode_for_server(server: Server) -> str:
    mode = (getattr(server, "google_routing_mode", None) or "exit").strip().lower()
    return mode if mode in ("exit", "entry") else "exit"


def _google_routing_env_line(server: Server) -> str:
    return f"export VPN_GOOGLE_ROUTING_MODE={shlex.quote(_google_routing_mode_for_server(server))}\n"


def _vless_grpc_env_lines(db: Session, server: Server, *, cfg: Settings) -> str:
    domain = _tls_sni_for_server(server)
    service_name = (server.grpc_service_name or "grpc").strip() or "grpc"
    uuids_csv = vless_client_uuids_csv_for_server(db, server)
    clients_b64 = vless_clients_b64_for_server(db, server)
    inbound_tag = (cfg.xray_vless_inbound_tag or "vpn-vless-in").strip() or "vpn-vless-in"
    email = (cfg.provision_certbot_email or "").strip()
    remote_env = (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_SERVER_ID={server.id}\n"
        f"export VPN_XRAY_INSTALLER_URL={shlex.quote(cfg.provision_xray_installer_url)}\n"
        f"export VPN_VLESS_UUID={shlex.quote(server.vless_uuid)}\n"
        f"export VPN_VLESS_INBOUND_TAG={shlex.quote(inbound_tag)}\n"
        f"export VPN_VLESS_CLIENT_UUIDS={shlex.quote(uuids_csv)}\n"
        f"export VPN_VLESS_CLIENTS_B64={shlex.quote(clients_b64)}\n"
        f"export VPN_XRAY_API_PORT={int(cfg.xray_remote_api_port)}\n"
        f"export VPN_TLS_DOMAIN={shlex.quote(domain)}\n"
        f"export VPN_GRPC_SERVICE_NAME={shlex.quote(service_name)}\n"
    )
    if email:
        remote_env += f"export VPN_TLS_CERTBOT_EMAIL={shlex.quote(email)}\n"
    remote_env += _google_routing_env_line(server)
    remote_env += _cascade_xray_env_for_ru_entry(db, server)
    return remote_env


def _vless_ws_env_lines(db: Session, server: Server, *, cfg: Settings) -> str:
    domain = _tls_sni_for_server(server)
    ws_path = (server.ws_path or "/vless").strip() or "/vless"
    if not ws_path.startswith("/"):
        ws_path = "/" + ws_path
    uuids_csv = vless_client_uuids_csv_for_server(db, server)
    clients_b64 = vless_clients_b64_for_server(db, server)
    inbound_tag = (cfg.xray_vless_inbound_tag or "vpn-vless-in").strip() or "vpn-vless-in"
    email = (cfg.provision_certbot_email or "").strip()
    remote_env = (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_SERVER_ID={server.id}\n"
        f"export VPN_XRAY_INSTALLER_URL={shlex.quote(cfg.provision_xray_installer_url)}\n"
        f"export VPN_VLESS_UUID={shlex.quote(server.vless_uuid)}\n"
        f"export VPN_VLESS_INBOUND_TAG={shlex.quote(inbound_tag)}\n"
        f"export VPN_VLESS_CLIENT_UUIDS={shlex.quote(uuids_csv)}\n"
        f"export VPN_VLESS_CLIENTS_B64={shlex.quote(clients_b64)}\n"
        f"export VPN_XRAY_API_PORT={int(cfg.xray_remote_api_port)}\n"
        f"export VPN_TLS_DOMAIN={shlex.quote(domain)}\n"
        f"export VPN_WS_PATH={shlex.quote(ws_path)}\n"
    )
    if email:
        remote_env += f"export VPN_TLS_CERTBOT_EMAIL={shlex.quote(email)}\n"
    remote_env += _google_routing_env_line(server)
    remote_env += _cascade_xray_env_for_ru_entry(db, server)
    return remote_env


def _vless_vkcdn_xhttp_env_lines(db: Session, server: Server, *, cfg: Settings) -> str:
    origin_domain = (server.origin_domain or server.host or "").strip().rstrip(".")
    cdn_domain = (server.cdn_domain or "").strip().rstrip(".")
    xhttp_path = (server.xhttp_path or "/uploadfiles/").strip() or "/uploadfiles/"
    if not xhttp_path.startswith("/"):
        xhttp_path = "/" + xhttp_path
    if not xhttp_path.endswith("/"):
        xhttp_path += "/"
    uuids_csv = vless_client_uuids_csv_for_server(db, server)
    clients_b64 = vless_clients_b64_for_server(db, server)
    inbound_tag = "VKCDN"
    email = (cfg.provision_certbot_email or "").strip()
    remote_env = (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_SERVER_ID={server.id}\n"
        f"export VPN_XRAY_INSTALLER_URL={shlex.quote(cfg.provision_xray_installer_url)}\n"
        f"export VPN_VLESS_UUID={shlex.quote(server.vless_uuid)}\n"
        f"export VPN_VLESS_INBOUND_TAG={shlex.quote(inbound_tag)}\n"
        f"export VPN_VLESS_CLIENT_UUIDS={shlex.quote(uuids_csv)}\n"
        f"export VPN_VLESS_CLIENTS_B64={shlex.quote(clients_b64)}\n"
        f"export VPN_XRAY_API_PORT={int(cfg.xray_remote_api_port)}\n"
        f"export VPN_ORIGIN_DOMAIN={shlex.quote(origin_domain)}\n"
        f"export VPN_CDN_DOMAIN={shlex.quote(cdn_domain)}\n"
        f"export VPN_XHTTP_PATH={shlex.quote(xhttp_path)}\n"
        "export VPN_XHTTP_LOCAL_PORT=4443\n"
    )
    if email:
        remote_env += f"export VPN_TLS_CERTBOT_EMAIL={shlex.quote(email)}\n"
    remote_env += _google_routing_env_line(server)
    return remote_env


def _xray_env_lines(db: Session, server: Server) -> str:
    uuids_csv = vless_client_uuids_csv_for_server(db, server)
    clients_b64 = vless_clients_b64_for_server(db, server)
    inbound_tag = (settings.xray_vless_inbound_tag or "vpn-vless-in").strip() or "vpn-vless-in"
    remote_env = (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_SERVER_ID={server.id}\n"
        f"export VPN_XRAY_INSTALLER_URL={shlex.quote(settings.provision_xray_installer_url)}\n"
        f"export VPN_VLESS_UUID={shlex.quote(server.vless_uuid)}\n"
        f"export VPN_VLESS_INBOUND_TAG={shlex.quote(inbound_tag)}\n"
        f"export VPN_VLESS_CLIENT_UUIDS={shlex.quote(uuids_csv)}\n"
        f"export VPN_VLESS_CLIENTS_B64={shlex.quote(clients_b64)}\n"
        f"export VPN_XRAY_API_PORT={int(settings.xray_remote_api_port)}\n"
        f"export VPN_REALITY_SHORT_ID={shlex.quote(server.reality_short_id)}\n"
        f"export VPN_REALITY_DEST={shlex.quote(server.reality_dest)}\n"
        f"export VPN_REALITY_SERVER_NAMES={shlex.quote(server.reality_server_names)}\n"
        f"export VPN_REALITY_FINGERPRINT={shlex.quote(server.reality_fingerprint)}\n"
        f"export VPN_REALITY_SPIDER_X={shlex.quote(normalize_reality_spider_x(server.reality_spider_x))}\n"
        f"export VPN_VLESS_FLOW={shlex.quote(server.vless_flow)}\n"
    )
    pk = (server.reality_private_key or "").strip()
    if pk:
        remote_env += f"export VPN_REALITY_PRIVATE_KEY={shlex.quote(pk)}\n"
    remote_env += _google_routing_env_line(server)
    remote_env += _cascade_xray_env_for_ru_entry(db, server)
    return remote_env


def _hysteria2_env_lines(server: Server) -> str:
    """Параметры для установки Hysteria2."""
    host = (server.host or "").strip() or "localhost"
    password = ((server.vless_uuid or "").replace("-", "")[:32] or f"hysteria{int(server.id)}")
    return (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_HYSTERIA2_DOMAIN={shlex.quote(host)}\n"
        f"export VPN_HYSTERIA2_PASSWORD={shlex.quote(password)}\n"
    )


def _cascade_xray_env_for_ru_entry(db: Session, server: Server) -> str:
    """РФ-вход → exit: транспорт магистрали по proxy_kind exit (vless / vless_grpc / vless_ws)."""
    if not server.is_cascade_ru_entry or not server.cascade_next_server_id:
        return "export VPN_CASCADE_ENABLED=0\n"
    eid = int(server.cascade_next_server_id)
    cu = (server.cascade_egress_client_uuid or "").strip()
    if not cu:
        raise RuntimeError(
            "Каскад: у РФ-входа (id=%s) нет cascade_egress_client_uuid; "
            "сохраните ссылку на exit в админке (или пересоздайте каскад)" % (server.id,)
        )
    ex = db.get(Server, eid)
    if ex is None:
        raise RuntimeError("Каскад: внешний сервер id=%s не найден" % eid)
    ekind = (ex.proxy_kind or "vless").strip().lower()
    if ekind not in ("vless", "vless_grpc", "vless_ws"):
        raise RuntimeError(
            "Каскад: exit id=%s proxy_kind=%s не поддерживается (vless, vless_grpc, vless_ws)"
            % (ex.id, ekind)
        )
    ehost = (ex.host or "").strip() or "127.0.0.1"
    eport = int(ex.port)
    ru_direct = "1" if settings.cascade_ru_split_routing else "0"
    lines = [
        "export VPN_CASCADE_ENABLED=1\n",
        f"export VPN_CASCADE_RU_DIRECT={ru_direct}\n",
        f"export VPN_CASCADE_EGRESS_TRANSPORT={shlex.quote(ekind)}\n",
        f"export VPN_CASCADE_EGRESS_ADDRESS={shlex.quote(ehost)}\n",
        f"export VPN_CASCADE_EGRESS_PORT={eport}\n",
        f"export VPN_CASCADE_EGRESS_CLIENT_UUID={shlex.quote(cu)}\n",
    ]
    if ekind == "vless":
        pbk = (ex.reality_public_key or "").strip()
        if not pbk:
            raise RuntimeError(
                "Каскад: на exit id=%s (REALITY) нет reality_public_key — сначала установите Xray"
                % ex.id
            )
        eflow = (ex.vless_flow or "xtls-rprx-vision").strip() or "xtls-rprx-vision"
        efp = (ex.reality_fingerprint or "chrome").strip() or "chrome"
        e_short = (ex.reality_short_id or "").strip() or "0123456789abcdef"
        e_names = (ex.reality_server_names or "").strip() or "www.amazon.com,amazon.com"
        e_spider = normalize_reality_spider_x(ex.reality_spider_x)
        lines.extend(
            [
                f"export VPN_CASCADE_EGRESS_PBK={shlex.quote(pbk)}\n",
                f"export VPN_CASCADE_EGRESS_SERVER_NAMES={shlex.quote(e_names)}\n",
                f"export VPN_CASCADE_EGRESS_SHORT_ID={shlex.quote(e_short)}\n",
                f"export VPN_CASCADE_EGRESS_FINGERPRINT={shlex.quote(efp)}\n",
                f"export VPN_CASCADE_EGRESS_FLOW={shlex.quote(eflow)}\n",
                f"export VPN_CASCADE_EGRESS_SPIDER_X={shlex.quote(e_spider)}\n",
            ]
        )
    else:
        sni = _tls_sni_for_server(ex)
        lines.append(f"export VPN_CASCADE_EGRESS_TLS_SNI={shlex.quote(sni)}\n")
        if ekind == "vless_grpc":
            svc = (ex.grpc_service_name or "grpc").strip() or "grpc"
            lines.append(f"export VPN_CASCADE_EGRESS_GRPC_SERVICE={shlex.quote(svc)}\n")
        elif ekind == "vless_ws":
            wpath = (ex.ws_path or "/vless").strip() or "/vless"
            if not wpath.startswith("/"):
                wpath = "/" + wpath
            lines.append(f"export VPN_CASCADE_EGRESS_WS_PATH={shlex.quote(wpath)}\n")
    return "".join(lines)


def _run_ssh_remote_provision(db: Session, server: Server, *, component: ProvisionComponent) -> None:
    script_body = _remote_script_payload()
    # Иначе на удалённой стороне TERM пустой → tput в сторонних скриптах (install-release.sh) даёт ошибку и ненулевой exit.
    remote_env = 'export TERM="${TERM:-xterm-256color}"\n'
    remote_env += f"export VPN_PROVISION_COMPONENT={shlex.quote(component)}\n"
    proxy_kind = (getattr(server, "proxy_kind", None) or "vless").strip().lower()
    if proxy_kind not in ("vless", "vless_grpc", "vless_ws", "vless_vk_cdn_xhttp", "hysteria2"):
        proxy_kind = "vless"
    remote_env += f"export VPN_PROXY_KIND={shlex.quote(proxy_kind)}\n"

    if component == "cleanup":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += f"export VPN_XRAY_INSTALLER_URL={shlex.quote(settings.provision_xray_installer_url)}\n"
    elif component == "prometheus":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += _node_exporter_env_lines(force_install=True)
    elif component == "fair_egress":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
    elif component in ("xray", "vless"):
        if proxy_kind == "vless_grpc":
            remote_env += _vless_grpc_env_lines(db, server, cfg=settings)
        elif proxy_kind == "vless_ws":
            remote_env += _vless_ws_env_lines(db, server, cfg=settings)
        elif proxy_kind == "vless_vk_cdn_xhttp":
            remote_env += _vless_vkcdn_xhttp_env_lines(db, server, cfg=settings)
        else:
            remote_env += _xray_env_lines(db, server)
        remote_env += _node_exporter_env_lines(force_install=False)
    elif component == "sync_clients":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        if proxy_kind == "vless_grpc":
            remote_env += _vless_grpc_env_lines(db, server, cfg=settings)
        elif proxy_kind == "vless_ws":
            remote_env += _vless_ws_env_lines(db, server, cfg=settings)
        elif proxy_kind == "vless_vk_cdn_xhttp":
            remote_env += _vless_vkcdn_xhttp_env_lines(db, server, cfg=settings)
        else:
            remote_env += _xray_env_lines(db, server)
    elif component == "hysteria2":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += _hysteria2_env_lines(server)
        remote_env += _node_exporter_env_lines(force_install=False)
    else:
        if proxy_kind == "hysteria2":
            remote_env += _hysteria2_env_lines(server)
        elif proxy_kind == "vless_grpc":
            remote_env += _vless_grpc_env_lines(db, server, cfg=settings)
        elif proxy_kind == "vless_ws":
            remote_env += _vless_ws_env_lines(db, server, cfg=settings)
        elif proxy_kind == "vless_vk_cdn_xhttp":
            remote_env += _vless_vkcdn_xhttp_env_lines(db, server, cfg=settings)
        else:
            remote_env += _xray_env_lines(db, server)
        remote_env += _node_exporter_env_lines(force_install=None)

    payload = (remote_env + script_body).replace("\r\n", "\n").replace("\r", "\n")
    log.info(
        "SSH provision start component=%s server_id=%s host=%s timeout_s=%s",
        component,
        server.id,
        server.host,
        int(settings.provision_subprocess_timeout),
    )
    rc, stdout_t, stderr_t, used_user = ssh_run_script_with_user_fallback(
        server,
        payload,
        timeout=settings.provision_subprocess_timeout,
        login_shell=False,
    )
    log.info(
        "SSH provision component=%s %s@%s server_id=%s",
        component,
        used_user,
        server.host,
        server.id,
    )
    if rc != 0:
        if (stderr_t or "").strip():
            log.error(
                "SSH stderr (tail 8000) rc=%s:\n%s",
                rc,
                (stderr_t or "")[-8000:],
            )
        if (stdout_t or "").strip():
            log.error(
                "SSH stdout (tail 8000) rc=%s:\n%s",
                rc,
                (stdout_t or "")[-8000:],
            )
        detail = _format_ssh_capture(stdout_t, stderr_t)
        raise RuntimeError(
            f"ssh завершился с кодом {rc}\n"
            + (
                detail
                or "(пустой stdout/stderr — смотрите логи воркера выше)"
            ),
        )

    if component in ("all", "xray", "vless") and (server.proxy_kind or "vless") == "vless":
        _persist_reality_keys(db, server, stdout_t)
    # sync_clients не генерирует ключи REALITY


def _execute_provision(db: Session, server: Server, *, component: ProvisionComponent) -> None:
    custom = (settings.provision_command or "").strip()
    if custom:
        if component != "all":
            raise RuntimeError(
                "Задан provision_command: поддерживается только полный прогон (component=all). "
                "Отключите provision_command для пошаговой установки и очистки по SSH.",
            )
        _run_provision_command(server)
    else:
        _run_ssh_remote_provision(db, server, component=component)


def _finalize_success(db: Session, server: Server, *, component: ProvisionComponent) -> None:
    db.refresh(server)
    if component == "cleanup":
        server.provision_ready = False
        server.provision_status = "idle"
        server.provision_error = None
        server.provision_job_id = None
        server.prometheus_instance = None
        server.reality_private_key = None
        server.reality_public_key = None
        db.commit()
        return

    server.provision_ready = True
    server.provision_status = "success"
    server.provision_error = None
    # prometheus_instance в БД только если нужен override (другой порт, hostname в scrape);
    # иначе пусто — в API/PromQL берётся host + provision_node_exporter_port
    db.commit()


def install_server_software(
    server_id: int,
    reconcile: bool = False,
    component: ProvisionComponent = "all",
) -> None:
    """
    Установка по SSH: all | xray | prometheus (node_exporter) | fair_egress | cleanup.
    Ожидает, что API уже выставил provision_status=queued.
    """
    db: Session = SessionLocal()
    try:
        server = db.get(Server, server_id)
        if server is None:
            log.error("Сервер id=%s не найден", server_id)
            return
        if server.provision_status != "queued":
            log.warning(
                "Пропуск id=%s: ожидался queued, сейчас %s",
                server_id,
                server.provision_status,
            )
            return

        server.provision_status = "running"
        server.provision_error = None
        db.commit()

        try:
            _execute_provision(db, server, component=component)
        except Exception as e:
            log.exception("Ошибка установки server_id=%s", server_id)
            db.refresh(server)
            server.provision_ready = False
            server.provision_status = "failed"
            server.provision_error = str(e)[:8000]
            db.commit()
            raise

        _finalize_success(db, server, component=component)
        log.info(
            "Провижининг завершён server_id=%s reconcile=%s component=%s",
            server_id,
            reconcile,
            component,
        )
    finally:
        db.close()


def sync_xray_clients_to_server(server_id: int) -> None:
    """
    Синхронизировать клиентов VLESS на узле с БД.

    По умолчанию: динамически через ``xray api`` (rmu/adu), без рестарта; при недоступности API,
    большом диффе или отключении в настройках — полная перезапись config и restart.
    """
    db: Session = SessionLocal()
    try:
        server = db.get(Server, server_id)
        if server is None:
            log.error("sync_xray_clients: сервер id=%s не найден", server_id)
            return
        if not server.provision_ready:
            log.warning(
                "sync_xray_clients: пропуск id=%s (узел не provision_ready)",
                server_id,
            )
            return
        if (server.proxy_kind or "vless").strip().lower() not in (
            "vless",
            "vless_grpc",
            "vless_ws",
            "vless_vk_cdn_xhttp",
        ):
            log.warning(
                "sync_xray_clients: пропуск id=%s (proxy_kind=%s)",
                server_id,
                server.proxy_kind,
            )
            return
        if server.provision_status in ("queued", "running"):
            log.warning(
                "sync_xray_clients: пропуск id=%s (идёт установка/очередь)",
                server_id,
            )
            return
        if (settings.provision_command or "").strip():
            raise RuntimeError(
                "Задан provision_command: SSH-синхронизация списка клиентов Xray недоступна",
            )
        dyn_ok, dyn_err = try_dynamic_xray_client_sync(db, server)
        if dyn_ok:
            return
        if dyn_err:
            log.error(
                "sync_xray_clients: динамическое обновление не удалось — %s. Выполняется полное (config + restart).",
                dyn_err,
            )
        _run_ssh_remote_provision(db, server, component="sync_clients")
    finally:
        db.close()


def sync_xray_clients_all_servers() -> None:
    """
    Обновить inbound на всех узлах с provision_ready.

    На узлах как у ``sync_xray_clients_to_server`` (динамика → при сбое полный sync). Разным server_id можно
    идти параллельно (``xray_sync_all_servers_parallelism``).
    """
    db = SessionLocal()
    try:
        stmt = select(Server.id).where(
            Server.provision_ready.is_(True),
            Server.proxy_kind.in_(("vless", "vless_grpc", "vless_ws", "vless_vk_cdn_xhttp")),
        )
        ids = list(db.scalars(stmt).all())
    finally:
        db.close()
    errors: list[str] = []
    if not ids:
        return
    workers = max(1, min(int(settings.xray_sync_all_servers_parallelism), len(ids)))

    def _run_one(sid: int) -> None:
        sync_xray_clients_to_server(sid)

    if workers <= 1:
        for sid in ids:
            try:
                _run_one(sid)
            except Exception as e:
                errors.append(f"{sid}: {e!s}")
                log.exception("sync_xray_clients_all: server_id=%s", sid)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fut_map = {pool.submit(_run_one, sid): sid for sid in ids}
            for fut in as_completed(fut_map):
                sid = fut_map[fut]
                try:
                    fut.result()
                except Exception as e:
                    errors.append(f"{sid}: {e!s}")
                    log.exception("sync_xray_clients_all: server_id=%s", sid)
    if errors:
        raise RuntimeError("; ".join(errors[:24]))


def collect_xray_user_traffic_all_servers(schedule_lock_token: str | None = None) -> dict[str, Any]:
    """
    RQ-вход батча сбора трафика Xray по всем активным provision_ready узлам.

    Расписательный lock (см. ``xray_traffic_scheduler``) держится всё время батча и
    снимается здесь по завершении (в т.ч. при ошибке) — поэтому периодический
    планировщик не запускает второй батч параллельно (нет дублей в ``user_server_traffic``).
    """
    from app.infrastructure.xray.xray_traffic_scheduler import release_schedule_lock

    try:
        return _collect_xray_user_traffic_all_servers_impl()
    finally:
        release_schedule_lock(schedule_lock_token)


def _collect_xray_user_traffic_all_servers_impl() -> dict[str, Any]:
    """Последовательный сбор трафика по узлам; компактный результат (хранится в RQ)."""
    log.info("collect_xray_user_traffic_all_servers: старт батча")
    db: Session = SessionLocal()
    try:
        stmt = (
            select(Server.id)
            .where(
                Server.provision_ready.is_(True),
                Server.is_active.is_(True),
                Server.proxy_kind.in_(("vless", "vless_grpc", "vless_ws", "vless_vk_cdn_xhttp")),
            )
            .order_by(Server.id.asc())
        )
        ids = list(db.scalars(stmt).all())
    finally:
        db.close()

    stagger = float(settings.xray_traffic_collect_stagger_seconds)
    errors: list[dict[str, int | str]] = []
    ok_n = 0
    for i, sid in enumerate(ids):
        if i > 0 and stagger > 0:
            time.sleep(stagger)
        one = collect_xray_user_traffic(int(sid))
        if one.get("ok"):
            ok_n += 1
        else:
            err_txt = (one.get("error") or "unknown")[:800]
            errors.append({"server_id": int(sid), "error": err_txt})

    failed_n = len(ids) - ok_n
    log.info(
        "collect_xray_user_traffic_all_servers: готово узлов=%s ok=%s failed=%s",
        len(ids),
        ok_n,
        failed_n,
    )

    trial_result: dict[str, object] = {}
    if ok_n > 0:
        from app.domain.subscription.traffic_limit import enforce_traffic_limits_after_collect

        enforce_db: Session = SessionLocal()
        try:
            enforced = enforce_traffic_limits_after_collect(enforce_db)
            trial_result = {
                "traffic_limit_over": enforced.over_limit_count,
                "traffic_limit_sync_enqueued": enforced.sync_enqueued,
                "traffic_notify_low": enforced.notify_low_created,
                "traffic_notify_over": enforced.notify_over_created,
            }
            if (
                enforced.over_limit_count
                or enforced.notify_low_created
                or enforced.notify_over_created
            ):
                log.info(
                    "collect_xray_user_traffic_all_servers: over limit=%s sync=%s "
                    "notify_low=%s notify_over=%s",
                    enforced.over_limit_count,
                    enforced.sync_enqueued,
                    enforced.notify_low_created,
                    enforced.notify_over_created,
                )
        except Exception:
            log.exception(
                "collect_xray_user_traffic_all_servers: ошибка проверки лимита трафика триала",
            )
            try:
                enforce_db.rollback()
            except Exception:
                pass
        finally:
            enforce_db.close()

    return {
        "servers_total": len(ids),
        "ok": ok_n,
        "failed": failed_n,
        "errors_sample": errors[:40],
        **trial_result,
    }


def collect_xray_user_traffic(server_id: int) -> dict[str, Any]:
    """
    RQ: SSH + xray api statsquery на узле (тот же ключ/окружение, что и провижининг).
    Возвращает сериализуемый dict для API (опрос статуса задачи).
    """
    log.info(
        "collect_xray_user_traffic: старт задачи RQ server_id=%s",
        server_id,
    )
    db: Session = SessionLocal()
    try:
        server = db.get(Server, server_id)
        if server is None:
            log.error("collect_xray_user_traffic: сервер id=%s не найден", server_id)
            return {
                "ok": False,
                "error": "Сервер не найден",
                "detail": None,
                "collected_at": None,
            }
        log.info(
            "collect_xray_user_traffic: SSH statsquery %s@%s server_id=%s (как при провижининге)",
            settings.provision_ssh_user,
            server.host,
            server_id,
        )
        err, detail = collect_xray_traffic_for_server(db, server)
        collected_at: datetime | None = None
        if err is None:
            db.commit()
            collected_at = utc_now()
            pu = getattr(detail, "parsed_users", None) if detail else None
            log.info(
                "collect_xray_user_traffic: готово server_id=%s host=%s пользователей в ответе=%s",
                server_id,
                server.host,
                pu if pu is not None else "—",
            )
        else:
            db.rollback()
            log.warning(
                "collect_xray_user_traffic: без обновления БД server_id=%s: %s",
                server_id,
                (err or "")[:400],
            )
        return {
            "ok": err is None,
            "error": err,
            "detail": detail.model_dump() if detail else None,
            "collected_at": collected_at.isoformat() if collected_at else None,
        }
    except Exception as e:
        log.exception("collect_xray_user_traffic server_id=%s", server_id)
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(e)[:2000],
            "detail": None,
            "collected_at": None,
        }
    finally:
        db.close()
