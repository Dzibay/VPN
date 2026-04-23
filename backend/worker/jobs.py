"""
Задачи очереди установки ПО на VPN-узел.

Функции вызываются процессом RQ; путь задачи: worker.jobs.install_server_software
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.server import Server
from app.services.provision_ssh import ssh_run_script_with_user_fallback
from app.services.xray_clients import (
    vless_client_uuids_csv_for_server,
    vless_clients_b64_for_server,
)
from app.services.xray_stats_collect import collect_xray_traffic_for_server

log = logging.getLogger("worker.provision")

_REMOTE_SCRIPT = Path(__file__).resolve().parent / "scripts" / "install_xray_on_remote.sh"


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
    "prometheus",
    "fair_egress",
    "cleanup",
    "sync_clients",
]


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


def _xray_env_lines(db: Session, server: Server) -> str:
    uuids_csv = vless_client_uuids_csv_for_server(db, server)
    clients_b64 = vless_clients_b64_for_server(db, server)
    remote_env = (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_SERVER_ID={server.id}\n"
        f"export VPN_XRAY_INSTALLER_URL={shlex.quote(settings.provision_xray_installer_url)}\n"
        f"export VPN_VLESS_UUID={shlex.quote(server.vless_uuid)}\n"
        f"export VPN_VLESS_CLIENT_UUIDS={shlex.quote(uuids_csv)}\n"
        f"export VPN_VLESS_CLIENTS_B64={shlex.quote(clients_b64)}\n"
        f"export VPN_XRAY_API_PORT={int(settings.xray_remote_api_port)}\n"
        f"export VPN_REALITY_SHORT_ID={shlex.quote(server.reality_short_id)}\n"
        f"export VPN_REALITY_DEST={shlex.quote(server.reality_dest)}\n"
        f"export VPN_REALITY_SERVER_NAMES={shlex.quote(server.reality_server_names)}\n"
        f"export VPN_REALITY_FINGERPRINT={shlex.quote(server.reality_fingerprint)}\n"
        f"export VPN_VLESS_FLOW={shlex.quote(server.vless_flow)}\n"
    )
    pk = (server.reality_private_key or "").strip()
    if pk:
        remote_env += f"export VPN_REALITY_PRIVATE_KEY={shlex.quote(pk)}\n"
    remote_env += _cascade_xray_env_for_ru_entry(db, server)
    return remote_env


def _cascade_xray_env_for_ru_entry(db: Session, server: Server) -> str:
    """
    РФ-вход: VLESS+REALITY outbound на внешний exit (тот же протокол, что у клиентов к exit).
    """
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
    pbk = (ex.reality_public_key or "").strip()
    if not pbk:
        raise RuntimeError(
            "Каскад: на внешнем узле id=%s (host=%s) нет reality_public_key — "
            "сначала установите Xray на exit" % (ex.id, ex.host)
        )
    ehost = (ex.host or "").strip() or "127.0.0.1"
    eport = int(ex.port)
    eflow = (ex.vless_flow or "xtls-rprx-vision").strip() or "xtls-rprx-vision"
    efp = (ex.reality_fingerprint or "chrome").strip() or "chrome"
    e_short = (ex.reality_short_id or "").strip() or "0123456789abcdef"
    e_names = (ex.reality_server_names or "").strip() or "www.amazon.com,amazon.com"
    return (
        "export VPN_CASCADE_ENABLED=1\n"
        f"export VPN_CASCADE_EGRESS_ADDRESS={shlex.quote(ehost)}\n"
        f"export VPN_CASCADE_EGRESS_PORT={eport}\n"
        f"export VPN_CASCADE_EGRESS_CLIENT_UUID={shlex.quote(cu)}\n"
        f"export VPN_CASCADE_EGRESS_PBK={shlex.quote(pbk)}\n"
        f"export VPN_CASCADE_EGRESS_SERVER_NAMES={shlex.quote(e_names)}\n"
        f"export VPN_CASCADE_EGRESS_SHORT_ID={shlex.quote(e_short)}\n"
        f"export VPN_CASCADE_EGRESS_FINGERPRINT={shlex.quote(efp)}\n"
        f"export VPN_CASCADE_EGRESS_FLOW={shlex.quote(eflow)}\n"
    )


def _run_ssh_remote_provision(db: Session, server: Server, *, component: ProvisionComponent) -> None:
    if not _REMOTE_SCRIPT.is_file():
        raise FileNotFoundError(f"Нет скрипта установки: {_REMOTE_SCRIPT}")

    script_body = _REMOTE_SCRIPT.read_text(encoding="utf-8")
    # Иначе на удалённой стороне TERM пустой → tput в сторонних скриптах (install-release.sh) даёт ошибку и ненулевой exit.
    remote_env = 'export TERM="${TERM:-xterm-256color}"\n'
    remote_env += f"export VPN_PROVISION_COMPONENT={shlex.quote(component)}\n"

    if component == "cleanup":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += f"export VPN_XRAY_INSTALLER_URL={shlex.quote(settings.provision_xray_installer_url)}\n"
    elif component == "prometheus":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += _node_exporter_env_lines(force_install=True)
    elif component == "fair_egress":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
    elif component == "xray":
        remote_env += _xray_env_lines(db, server)
        remote_env += _node_exporter_env_lines(force_install=False)
    elif component == "sync_clients":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += _xray_env_lines(db, server)
    else:
        remote_env += _xray_env_lines(db, server)
        remote_env += _node_exporter_env_lines(force_install=None)

    payload = (remote_env + script_body).replace("\r\n", "\n").replace("\r", "\n")
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

    if component in ("all", "xray"):
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
    Перезаписать inbound Xray на узле: список UUID = активные подписки (или fallback UUID узла).
    Не трогает provision_status и не требует очереди провижининга.
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
        _run_ssh_remote_provision(db, server, component="sync_clients")
    finally:
        db.close()


def sync_xray_clients_all_servers() -> None:
    """Обновить inbound на всех узлах с provision_ready."""
    db = SessionLocal()
    try:
        stmt = select(Server.id).where(Server.provision_ready.is_(True))
        ids = list(db.scalars(stmt).all())
    finally:
        db.close()
    errors: list[str] = []
    for sid in ids:
        try:
            sync_xray_clients_to_server(sid)
        except Exception as e:
            errors.append(f"{sid}: {e!s}")
            log.exception("sync_xray_clients_all: server_id=%s", sid)
    if errors:
        raise RuntimeError("; ".join(errors[:24]))


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
            collected_at = datetime.now(timezone.utc)
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
