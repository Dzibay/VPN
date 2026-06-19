"""
Динамическое обновление VLESS-клиентов через Xray HandlerService по SSH:

``inbounduser`` → дифф с БД → ``rmu`` / ``adu`` без перезапуска Xray.

По умолчанию включено. Если не вышло — вызывающий код пишет текст ошибки в лог и делает полный sync_clients.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shlex
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, settings as default_settings
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.ssh.provision_ssh import ssh_run_script_with_user_fallback
from app.infrastructure.xray.xray_clients import vless_client_entries_for_server

log = logging.getLogger("app.xray_dynamic_sync")

_EMAIL_SUFFIX_RE = re.compile(r".*@(vpn|cascade)$")
_INBOUND_EMAIL_RE = re.compile(r'"email"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _clip(blob: str, limit: int = 2500) -> str:
    t = blob.strip()
    if len(t) <= limit:
        return t
    return f"…(+{len(t) - limit} символов)\n" + t[-limit:]


def _collect_emails_from_json_tree(obj: Any) -> set[str]:
    out: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            em = o.get("email")
            if isinstance(em, str):
                clean = em.encode("utf-8").decode("unicode_escape").strip('"')
                if _EMAIL_SUFFIX_RE.match(clean):
                    out.add(clean)
            v = o.get("users")
            if isinstance(v, list):
                for x in v:
                    walk(x)
            for val in o.values():
                walk(val)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return out


def parse_emails_from_inbound_user_stdout(stdout: str) -> set[str]:
    raw = stdout.lstrip()
    if not raw:
        raise ValueError("Пустой ответ inbounduser")
    try:
        data, _end = json.JSONDecoder().raw_decode(raw)
        return _collect_emails_from_json_tree(data)
    except json.JSONDecodeError:
        emails: set[str] = set()
        for m in _INBOUND_EMAIL_RE.finditer(raw):
            token = m.group(1).encode("utf-8").decode("unicode_escape")
            if _EMAIL_SUFFIX_RE.match(token):
                emails.add(token)
        if not emails:
            raise
        return emails


def _adu_json_for_adds(
    *,
    server: Server,
    inbound_tag: str,
    adds: list[dict[str, object]],
) -> str:
    clients: list[dict[str, object]] = []
    for c in adds:
        entry: dict[str, object] = {
            "id": c["id"],
            "email": c["email"],
            "level": int(c.get("level") or 0),
        }
        if "flow" in c:
            entry["flow"] = c["flow"]
        clients.append(entry)
    doc = {
        "inbounds": [
            {
                "tag": inbound_tag,
                "listen": "0.0.0.0",
                "port": int(server.port),
                "protocol": "vless",
                "settings": {
                    "clients": clients,
                    "decryption": "none",
                },
            }
        ]
    }
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


def try_dynamic_xray_client_sync(
    db: Session,
    server: Server,
    *,
    cfg: Settings | None = None,
) -> tuple[bool, str | None]:
    """
    (True, None) — список на узле совпадает с БД (в т.ч. без изменений) или изменения применены без полного SSH sync_clients.

    (False, None) — динамика выключена: сразу полный sync_clients, без сообщения об ошибке.

    (False, msg) — динамика не удалась: ``msg`` нужно записать в лог (обычно ERROR), затем полный sync_clients.
    """
    cfg = cfg or default_settings
    if not cfg.xray_dynamic_client_sync_enabled:
        return False, None
    if (server.proxy_kind or "vless").strip().lower() == "vless_vk_cdn_xhttp":
        tag = "VKCDN"
    else:
        tag = (cfg.xray_vless_inbound_tag or "").strip()
    if not tag:
        return False, 'Не задан xray_vless_inbound_tag (тег inbound в config на узле)'

    ssh_timeout = float(cfg.provision_subprocess_timeout)

    desired_rows = vless_client_entries_for_server(db, server)
    desired_by_email = {str(r["email"]): r for r in desired_rows}
    desired_emails = set(desired_by_email.keys())

    api_listen = shlex.quote(f"127.0.0.1:{int(cfg.xray_remote_api_port)}")
    bin_q = shlex.quote((cfg.xray_remote_binary_path or "/usr/local/bin/xray").strip())
    timeout_s = max(3, int(cfg.xray_api_operation_timeout_seconds))
    tag_q = shlex.quote(tag)

    probe_script = """set -u
TERM="${{TERM:-xterm-256color}}"
BIN_INIT={bin_q}
API={api_listen}
TAG={tag_q}
TIMEOUT={timeout}
BIN="$BIN_INIT"
if [[ -z "${{BIN}}" || ! -x "${{BIN}}" ]]; then
  if X2=$(command -v xray 2>/dev/null) && [[ -n "$X2" && -x "$X2" ]]; then BIN="$X2"; fi
fi
if [[ -z "${{BIN}}" || ! -x "${{BIN}}" ]]; then BIN=/usr/local/bin/xray; fi
"$BIN" api inbounduser --server="$API" -timeout="$TIMEOUT" -tag="$TAG" </dev/null 2>&1
""".format(
        bin_q=bin_q,
        api_listen=api_listen,
        tag_q=tag_q,
        timeout=timeout_s,
    )

    rc, stdout_t, stderr_t, _user = ssh_run_script_with_user_fallback(
        server,
        probe_script,
        timeout=ssh_timeout,
        login_shell=False,
    )

    merged = ((stdout_t or "") + ("\n" + stderr_t if stderr_t else "")).strip()
    if rc != 0:
        detail = _clip(f"SSH rc={rc}\n{_clip(merged, 3800)}")
        return False, f"server_id={server.id} inbounduser: {detail}"

    try:
        current_emails = parse_emails_from_inbound_user_stdout(merged)
    except (json.JSONDecodeError, ValueError) as e:
        snippet = _clip(merged)
        return (
            False,
            f"server_id={server.id} разбор ответа inbounduser: {e}. Вывод:\n{snippet}",
        )

    to_remove = sorted(current_emails - desired_emails)
    to_add_mail = sorted(desired_emails - current_emails)
    to_add = [desired_by_email[e] for e in to_add_mail]

    n_ops = len(to_remove) + len(to_add)
    if n_ops == 0:
        return True, None

    chunks: list[str] = [
        "set -euo pipefail",
        'TERM="${TERM:-xterm-256color}"',
        f"BIN_INIT={bin_q}",
        f"API={api_listen}",
        f"TAG={tag_q}",
        f"TIMEOUT={timeout_s}",
        'BIN="$BIN_INIT"',
        'if [[ -z "$BIN" || ! -x "$BIN" ]]; then',
        '  if X2=$(command -v xray 2>/dev/null) && [[ -n "$X2" && -x "$X2" ]]; then BIN="$X2"; fi',
        "fi",
        'if [[ -z "$BIN" || ! -x "$BIN" ]]; then BIN=/usr/local/bin/xray; fi',
    ]

    for em in to_remove:
        chunks.append(
            f'$BIN api rmu --server="$API" -timeout="$TIMEOUT" -tag="$TAG" '
            + shlex.quote(em)
            + ' </dev/null 2>/dev/null || true',
        )

    if to_add:
        adu_b64 = base64.standard_b64encode(
            _adu_json_for_adds(server=server, inbound_tag=tag, adds=to_add).encode("utf-8"),
        ).decode("ascii")
        tf = shlex.quote(f"/tmp/vpn-adu-{server.id}.json")
        chunks.append(f"echo {shlex.quote(adu_b64)} | base64 -d > {tf}")
        chunks.append(f'$BIN api adu --server="$API" -timeout="$TIMEOUT" {tf} </dev/null')
        chunks.append(f"rm -f {tf}")

    apply_script = "\n".join(chunks) + "\n"
    arc, aout, aerr, ssh_u = ssh_run_script_with_user_fallback(
        server,
        apply_script,
        timeout=ssh_timeout,
        login_shell=False,
    )

    if arc != 0:
        tail = _clip(((aout or "") + "\n" + (aerr or "")).strip())
        return (
            False,
            (
                f"server_id={server.id} после rmu/adu: SSH rc={arc}, ssh_user={ssh_u}. "
                f"Вывод:\n{tail}"
            ),
        )

    log.info(
        "Динамический sync: server_id=%s (%s@%s): −%s +%s пользователей, без рестарта Xray",
        server.id,
        ssh_u,
        server.host,
        len(to_remove),
        len(to_add),
    )
    return True, None
