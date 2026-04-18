"""
Задачи очереди установки ПО на VPN-узел.

Функции вызываются процессом RQ; путь задачи: worker.jobs.install_server_software
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.server import Server

log = logging.getLogger("worker.provision")

_REMOTE_SCRIPT = Path(__file__).resolve().parent / "scripts" / "install_xray_on_remote.sh"

ProvisionComponent = Literal["all", "xray", "prometheus", "cleanup"]


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


def _ssh_base_cmd(server: Server) -> list[str]:
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        raise RuntimeError(
            "Не найден исполняемый файл ssh. Установите OpenSSH-клиент на машине воркера.",
        )
    cmd: list[str] = [
        ssh_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=30",
        "-p",
        str(settings.provision_ssh_port),
    ]
    key = (settings.provision_ssh_key_path or "").strip()
    if key:
        cmd.extend(["-i", key])
    extra = (settings.provision_ssh_extra_args or "").strip()
    if extra:
        cmd.extend(shlex.split(extra))
    target = f"{settings.provision_ssh_user}@{server.host}"
    cmd.extend([target, "bash", "-s"])
    return cmd


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


def _xray_env_lines(server: Server) -> str:
    remote_env = (
        f"export VPN_SERVER_PORT={server.port}\n"
        f"export VPN_SERVER_ID={server.id}\n"
        f"export VPN_XRAY_INSTALLER_URL={shlex.quote(settings.provision_xray_installer_url)}\n"
        f"export VPN_VLESS_UUID={shlex.quote(server.vless_uuid)}\n"
        f"export VPN_REALITY_SHORT_ID={shlex.quote(server.reality_short_id)}\n"
        f"export VPN_REALITY_DEST={shlex.quote(server.reality_dest)}\n"
        f"export VPN_REALITY_SERVER_NAMES={shlex.quote(server.reality_server_names)}\n"
        f"export VPN_REALITY_FINGERPRINT={shlex.quote(server.reality_fingerprint)}\n"
        f"export VPN_VLESS_FLOW={shlex.quote(server.vless_flow)}\n"
    )
    pk = (server.reality_private_key or "").strip()
    if pk:
        remote_env += f"export VPN_REALITY_PRIVATE_KEY={shlex.quote(pk)}\n"
    return remote_env


def _run_ssh_remote_provision(db: Session, server: Server, *, component: ProvisionComponent) -> None:
    if not _REMOTE_SCRIPT.is_file():
        raise FileNotFoundError(f"Нет скрипта установки: {_REMOTE_SCRIPT}")

    script_body = _REMOTE_SCRIPT.read_text(encoding="utf-8")
    remote_env = f"export VPN_PROVISION_COMPONENT={shlex.quote(component)}\n"

    if component == "cleanup":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += f"export VPN_XRAY_INSTALLER_URL={shlex.quote(settings.provision_xray_installer_url)}\n"
    elif component == "prometheus":
        remote_env += f"export VPN_SERVER_ID={server.id}\n"
        remote_env += _node_exporter_env_lines(force_install=True)
    elif component == "xray":
        remote_env += _xray_env_lines(server)
        remote_env += _node_exporter_env_lines(force_install=False)
    else:
        remote_env += _xray_env_lines(server)
        remote_env += _node_exporter_env_lines(force_install=None)

    payload = (remote_env + script_body).replace("\r\n", "\n").replace("\r", "\n")
    cmd = _ssh_base_cmd(server)

    log.info(
        "SSH provision component=%s %s@%s server_id=%s",
        component,
        settings.provision_ssh_user,
        server.host,
        server.id,
    )
    result = subprocess.run(
        cmd,
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=settings.provision_subprocess_timeout,
    )
    stdout_t = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr_t = (result.stderr or b"").decode("utf-8", errors="replace")
    if result.returncode != 0:
        err = (stderr_t + "\n" + stdout_t).strip()
        raise RuntimeError(err[-12000:] or f"ssh завершился с кодом {result.returncode}")

    if component in ("all", "xray"):
        _persist_reality_keys(db, server, stdout_t)


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
    Установка по SSH: all | xray | prometheus (node_exporter) | cleanup.
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
