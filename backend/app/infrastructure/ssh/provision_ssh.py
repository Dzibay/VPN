"""
Общий SSH-клиент для команд на узле (воркер и API сбора статистики Xray).
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import threading
import time
from collections.abc import Callable

from app.config import settings
from app.infrastructure.persistence.models.server import Server

log = logging.getLogger("app.provision_ssh")


def server_ssh_user(server: Server) -> str:
    """SSH-логин узла из БД; по умолчанию root."""
    raw = getattr(server, "ssh_user", None) or "root"
    return (str(raw).strip() or "root")


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


def ssh_bash_s_cmd_for_user(
    server: Server,
    ssh_user: str,
    *,
    login_shell: bool = False,
) -> list[str]:
    """
    Удалённая команда: bash -s (как в провижининге).
    Если логин не root — `sudo -n -E …` (нужен NOPASSWD в sudoers).
    """
    target = f"{ssh_user}@{server.host}"
    if login_shell:
        sh_argv = ["bash", "-l", "-s"]
    else:
        sh_argv = ["bash", "-s"]
    base = ssh_base_argv(server) + [target]
    u = (ssh_user or "").strip()
    if u != "root":
        return base + ["sudo", "-n", "-E", *sh_argv]
    return base + sh_argv


def ssh_run_script(
    server: Server,
    script: str | bytes,
    *,
    timeout: float,
    login_shell: bool = False,
    output_callback: Callable[[str, str], None] | None = None,
) -> tuple[int, str, str, str]:
    """
    SSH + bash -s, stdin = script.

    Возвращает: returncode, stdout, stderr, used_ssh_user.
    """
    data = (
        script.encode("utf-8")
        if isinstance(script, str)
        else (script or b"")
    )
    if not data.endswith(b"\n"):
        data = data + b"\n"
    u = server_ssh_user(server)
    cmd = ssh_bash_s_cmd_for_user(server, u, login_shell=login_shell)
    log.debug("ssh %s@%s", u, server.host)
    if output_callback is None:
        result = subprocess.run(
            cmd,
            input=data,
            capture_output=True,
            timeout=timeout,
        )
        out = (result.stdout or b"").decode("utf-8", errors="replace")
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        rc = int(result.returncode)
    else:
        rc, out, err = _run_script_streaming(
            cmd,
            data,
            timeout=timeout,
            output_callback=output_callback,
        )
    return rc, out, err, u


def _run_script_streaming(
    cmd: list[str],
    data: bytes,
    *,
    timeout: float,
    output_callback: Callable[[str, str], None],
) -> tuple[int, str, str]:
    """Popen-вариант subprocess.run: отдаёт stdout/stderr построчно в callback."""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    out_lines: list[str] = []
    err_lines: list[str] = []

    def _writer() -> None:
        try:
            if proc.stdin is not None:
                proc.stdin.write(data.decode("utf-8", errors="replace"))
                proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def _reader(stream_name: str, target: list[str], pipe) -> None:
        try:
            for line in iter(pipe.readline, ""):
                target.append(line)
                output_callback(stream_name, line.rstrip("\n"))
        except Exception:
            log.exception("ssh streaming reader failed (%s)", stream_name)
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    threads = [
        threading.Thread(target=_writer, daemon=True),
        threading.Thread(target=_reader, args=("stdout", out_lines, proc.stdout), daemon=True),
        threading.Thread(target=_reader, args=("stderr", err_lines, proc.stderr), daemon=True),
    ]
    for t in threads:
        t.start()

    deadline = time.monotonic() + float(timeout)
    while proc.poll() is None:
        if time.monotonic() >= deadline:
            proc.kill()
            for t in threads:
                t.join(timeout=1)
            raise subprocess.TimeoutExpired(cmd, timeout)
        time.sleep(0.1)

    for t in threads:
        t.join(timeout=2)
    return int(proc.returncode or 0), "".join(out_lines), "".join(err_lines)


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
    rc, out, err, _u = ssh_run_script(
        server,
        remote_bash_lc,
        timeout=timeout,
        login_shell=login_shell,
    )
    return rc, out, err
