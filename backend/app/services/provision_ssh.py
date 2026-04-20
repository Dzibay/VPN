"""
Общий SSH-клиент для команд на узле (воркер и API сбора статистики Xray).
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess

from app.core.config import settings
from app.models.server import Server

log = logging.getLogger("app.provision_ssh")


def ssh_base_argv(server: Server) -> list[str]:
    """Аргументы ssh до user@host (без цели и удалённой команды)."""
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        raise RuntimeError(
            "Не найден исполняемый файл ssh. Установите OpenSSH-клиент.",
        )
    cmd: list[str] = [
        ssh_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=30",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-p",
        str(settings.provision_ssh_port),
    ]
    key = (settings.provision_ssh_key_path or "").strip()
    if key:
        cmd.extend(["-i", key])
    extra = (settings.provision_ssh_extra_args or "").strip()
    if extra:
        cmd.extend(shlex.split(extra))
    return cmd


def ssh_run_bash_lc(
    server: Server,
    remote_bash_lc: str,
    *,
    timeout: float,
    login_shell: bool = False,
) -> tuple[int, str, str]:
    """
    Выполнить на узле скрипт bash, переданный по stdin (bash -s / bash -l -s).

    Не используем «bash -c одна_строка» в argv после user@host: у OpenSSH на Windows
    оставшиеся аргументы часто склеиваются без кавычек, и удалённый bash -c получает
    только первый токен — тогда вместо `xray api statsquery` запускается один `xray`
    и он читает конфиг из STDIN (как в логе «Using config from STDIN»).
    Тот же приём, что у провижининга: bash -s + скрипт в stdin.
    """
    target = f"{settings.provision_ssh_user}@{server.host}"
    bash_argv = ["bash", "-l", "-s"] if login_shell else ["bash", "-s"]
    cmd = ssh_base_argv(server) + [target] + bash_argv
    log.debug("ssh bash %s на %s", bash_argv, target)
    script = remote_bash_lc if remote_bash_lc.endswith("\n") else remote_bash_lc + "\n"
    result = subprocess.run(
        cmd,
        input=script.encode("utf-8"),
        capture_output=True,
        timeout=timeout,
    )
    out = (result.stdout or b"").decode("utf-8", errors="replace")
    err = (result.stderr or b"").decode("utf-8", errors="replace")
    return result.returncode, out, err
