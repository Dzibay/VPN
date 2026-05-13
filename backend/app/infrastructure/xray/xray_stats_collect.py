"""
Сбор счётчиков трафика Xray (statsquery по SSH) и обновление накопленных байт в БД.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import time
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import as_calendar_date, utc_today
from app.infrastructure.persistence.models.server import Server
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_server_traffic import UserServerTraffic
from app.domain.user_traffic import (
    user_server_traffic_latest_strictly_before_calendar_day_subquery,
    user_server_traffic_latest_subquery,
)
from app.domain.models.server_traffic import (
    ServerUserTrafficBundle,
    ServerUserTrafficRow,
    UserTrafficCollectDetail,
)
from app.infrastructure.ssh.provision_ssh import ssh_run_bash_lc

log = logging.getLogger("app.xray_stats")

_PREVIEW_LEN = 4500

USER_STAT_RE = re.compile(
    r"^user>>>u(?P<uid>\d+)@vpn>>>traffic>>>(?P<dir>uplink|downlink)$",
)


def _ssh_key_file_hint() -> str | None:
    """
    Если задан PROVISION_SSH_KEY_PATH — файл должен существовать на машине, где выполняется API/воркер.
    Пусто — ssh использует agent / ~/.ssh/id_* (как при провижининге).
    """
    key = (settings.provision_ssh_key_path or "").strip()
    if not key:
        return None
    p = Path(key).expanduser()
    try:
        is_reg = p.is_file()
    except OSError as exc:
        return (
            f"Не удалось открыть ключ SSH по PROVISION_SSH_KEY_PATH «{key}»: {exc}. "
            "В Docker воркер обычно UID 10001 — на хосте: chown -R 10001:10001 каталога с ключом, "
            "chmod 0700 на каталоге и 0600 на файле ключа (см. комментарий к сервису worker в deploy/docker-compose.yml)."
        )
    if not is_reg:
        return (
            f"PROVISION_SSH_KEY_PATH указывает на отсутствующий файл «{key}». "
            "Укажите тот же путь к приватному ключу, что на машине воркера (где работает SSH к узлам)."
        )
    return None


def _merge_axis(total: int, raw_old: int, raw_new: int) -> tuple[int, int]:
    """Накопление с учётом сброса счётчика при рестарте Xray."""
    if raw_new >= raw_old:
        delta = raw_new - raw_old
    else:
        total += raw_old
        delta = raw_new
    return total + delta, raw_new


def _timeout_exc_streams(e: subprocess.TimeoutExpired) -> tuple[str, str]:
    """Частичный stdout/stderr до kill процесса (Python 3.5+ subprocess)."""
    raw_o = getattr(e, "stdout", None)
    raw_e = getattr(e, "stderr", None)
    out = ""
    err = ""
    if raw_o is not None:
        out = raw_o.decode("utf-8", errors="replace") if isinstance(raw_o, bytes) else str(raw_o)
    if raw_e is not None:
        err = raw_e.decode("utf-8", errors="replace") if isinstance(raw_e, bytes) else str(raw_e)
    return out, err


def _preview(text: str, max_len: int = _PREVIEW_LEN) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return t[:max_len] + f"\n… (+{len(t) - max_len} симв.)"


def parse_statsquery_json(text: str) -> dict[int, dict[str, int]]:
    """user_id -> {'up': bytes, 'down': bytes} из ответа xray api statsquery."""
    # stdout+stderr могут содержать один валидный JSON и «хвост» (повторный JSON, строка лога).
    # json.loads на всём буфере даёт Extra data; берём только первое значение.
    text = text.lstrip()
    data, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(data, dict):
        data = {}
    stats = data.get("stat") or data.get("stats") or []
    if isinstance(stats, dict):
        stats = list(stats.values()) if stats else []
    merged: dict[int, dict[str, int]] = {}
    for item in stats:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        try:
            val = int(item.get("value") or 0)
        except (TypeError, ValueError):
            val = 0
        m = USER_STAT_RE.match(name)
        if not m:
            continue
        uid = int(m.group("uid"))
        direction = m.group("dir")
        if uid not in merged:
            merged[uid] = {"up": 0, "down": 0}
        if direction == "uplink":
            merged[uid]["up"] = val
        else:
            merged[uid]["down"] = val
    return merged


def _traffic_day_utc() -> date:
    """Календарный день для привязки строк в БД (UTC)."""
    return utc_today()


def _latest_prior_day_row(
    session: Session,
    uid: int,
    server_id: int,
    day: date,
) -> UserServerTraffic | None:
    stmt = (
        select(UserServerTraffic)
        .where(
            UserServerTraffic.user_id == uid,
            UserServerTraffic.server_id == server_id,
            UserServerTraffic.traffic_date < day,
        )
        .order_by(UserServerTraffic.traffic_date.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def _get_or_create_day_row(
    session: Session,
    uid: int,
    server: Server,
    day: date,
) -> UserServerTraffic | None:
    existing = session.get(UserServerTraffic, (uid, server.id, day))
    if existing is not None:
        return existing
    if session.get(User, uid) is None:
        return None
    prev = _latest_prior_day_row(session, uid, server.id, day)
    row = UserServerTraffic(
        user_id=uid,
        server_id=server.id,
        traffic_date=day,
        up_bytes=int(prev.up_bytes) if prev else 0,
        down_bytes=int(prev.down_bytes) if prev else 0,
        raw_up=int(prev.raw_up) if prev else 0,
        raw_down=int(prev.raw_down) if prev else 0,
    )
    session.add(row)
    return row


def _collect_base_detail(server: Server) -> UserTrafficCollectDetail:
    port_ssh = int(settings.provision_ssh_port)
    api_port = int(settings.xray_remote_api_port)
    bin_path = settings.xray_remote_binary_path.strip() or "/usr/local/bin/xray"
    listen = f"127.0.0.1:{api_port}"
    # Таймаут только на стороне Python (subprocess + XRAY_STATS_SSH_TIMEOUT_SECONDS).
    # STDIN закрыт (</dev/null): иначе на неинтерактивном SSH xray уходит в режим «читать конфиг из
    # STDIN» (лог: Using config from STDIN) и висит до таймаута вместо api statsquery.
    # Без «exec»: в редких случаях exec + замена shell давали пустой stdout при rc=0.
    remote = (
        f"{shlex.quote(bin_path)} api statsquery --server={listen} "
        f"</dev/null 2>&1"
    )
    fb = (settings.provision_ssh_user_fallback or "").strip()
    user_hint = (settings.provision_ssh_user or "root") + (f" → {fb}" if fb else "")
    return UserTrafficCollectDetail(
        ssh_target=f"{user_hint}@{server.host}",
        ssh_port=port_ssh,
        xray_api_listen=listen,
        remote_command=remote,
    )


def collect_xray_traffic_for_server(
    session: Session,
    server: Server,
) -> tuple[str | None, UserTrafficCollectDetail]:
    """
    SSH: xray api statsquery, разбор, обновление user_server_traffic.
    Возвращает (текст ошибки или None, детали для UI).
    """
    base = _collect_base_detail(server)

    if (settings.provision_command or "").strip():
        return (
            "Задан provision_command: сбор по SSH недоступен",
            base.model_copy(
                update={"skipped_reason": "Задан provision_command"},
            ),
        )
    if not server.provision_ready:
        return (
            "Узел не provision_ready",
            base.model_copy(update={"skipped_reason": "provision_ready = false"}),
        )

    key_err = _ssh_key_file_hint()
    if key_err:
        return (
            key_err,
            base.model_copy(
                update={"skipped_reason": "Проблема с PROVISION_SSH_KEY_PATH"},
            ),
        )

    remote = base.remote_command or ""
    ssh_timeout = float(settings.xray_stats_ssh_timeout_seconds)
    key_path = (settings.provision_ssh_key_path or "").strip()
    key_hint = os.path.basename(key_path) if key_path else "agent/по умолчанию"
    t0 = time.monotonic()
    log.info(
        "SSH statsquery: старт server_id=%s host=%s ssh_port=%s user=%s timeout=%.0fs key=%s remote_cmd=%s",
        server.id,
        server.host,
        settings.provision_ssh_port,
        settings.provision_ssh_user,
        ssh_timeout,
        key_hint,
        remote[:500] + ("…" if len(remote) > 500 else ""),
    )
    try:
        rc, out, err = ssh_run_bash_lc(
            server,
            remote,
            timeout=ssh_timeout,
        )
    except subprocess.TimeoutExpired as te:
        elapsed_ms = (time.monotonic() - t0) * 1000
        partial_out, partial_err = _timeout_exc_streams(te)
        log.warning(
            "SSH statsquery: ТАЙМАУТ server_id=%s host=%s за %.1f с (лимит %.0f с). "
            "Частичный stdout (%d симв.): %s | stderr (%d симв.): %s",
            server.id,
            server.host,
            elapsed_ms / 1000.0,
            ssh_timeout,
            len(partial_out),
            _preview(partial_out, 2000),
            len(partial_err),
            _preview(partial_err, 2000),
        )
        h = server.host
        u = settings.provision_ssh_user
        p = settings.provision_ssh_port
        return (
            f"SSH: таймаут {ssh_timeout:.0f} с (вся сессия). "
            "См. лог воркера (app.xray_stats): там фрагменты stdout/stderr до обрыва — по ним видно, "
            "завис ли TCP к узлу, SSH-сессия или уже `xray api` на VPS. "
            "BatchMode=yes — пароль не используется. "
            "Если `ssh -p PORT user@host true` с этой же машины быстрый, а таймаут только здесь — "
            "часто не отвечает Stats API Xray на 127.0.0.1 (порт, не запущен xray). "
            f"Проверка: `ssh -o BatchMode=yes -p {p} {u}@{h} true`. "
            f"Ключ как у воркера: PROVISION_SSH_KEY_PATH={key_hint}. "
            "При медленном канале увеличьте XRAY_STATS_SSH_TIMEOUT_SECONDS.",
            base.model_copy(
                update={
                    "duration_ms": round(elapsed_ms, 1),
                    "skipped_reason": f"Таймаут SSH ({ssh_timeout:.0f} с)",
                    "stdout_preview": _preview(partial_out) if partial_out.strip() else None,
                    "stderr_preview": _preview(partial_err) if partial_err.strip() else None,
                },
            ),
        )
    except Exception as e:
        log.exception("SSH statsquery server_id=%s", server.id)
        elapsed_ms = (time.monotonic() - t0) * 1000
        return (
            str(e)[:500],
            base.model_copy(
                update={
                    "duration_ms": round(elapsed_ms, 1),
                    "skipped_reason": "Исключение при SSH",
                    "stderr_preview": _preview(str(e), 800),
                },
            ),
        )

    elapsed_ms = (time.monotonic() - t0) * 1000
    log.info(
        "SSH statsquery: ответ за %.1f мс server_id=%s host=%s ssh_rc=%s len_stdout=%s len_stderr=%s",
        elapsed_ms,
        server.id,
        server.host,
        rc,
        len(out or ""),
        len(err or ""),
    )
    detail_after_ssh = base.model_copy(
        update={
            "exit_code": rc,
            "duration_ms": round(elapsed_ms, 1),
            "stdout_preview": _preview(out) if out.strip() else None,
            "stderr_preview": _preview(err) if err.strip() else None,
        },
    )

    combined = (out + "\n" + err).strip()
    low = combined.lower()
    if "permission denied" in low or "authentication failed" in low or "too many authentication failures" in low:
        return (
            "SSH: отказ в аутентификации (ключ не подошёл или на сервере только пароль). "
            "Пароль через этот клиент не передать (BatchMode). "
            "Добавьте публичный ключ в ~/.ssh/authorized_keys на узле или задайте верный PROVISION_SSH_KEY_PATH. "
            f"Фрагмент ответа: {combined[:320]}",
            detail_after_ssh,
        )
    if "connection refused" in low or "connect: connection refused" in low:
        return (
            "На узле не отвечает Xray Stats API по адресу с узла (127.0.0.1). "
            "Это не «закрытый порт с интернета»: запрос идёт уже после SSH, с самого VPS на localhost. "
            "Проверьте: процесс Xray запущен; в конфиге включены stats/policy и API; порт совпадает с "
            "XRAY_REMOTE_API_PORT в .env панели (тот же, что в inbound dokodemo/stats на узле). "
            f"Фрагмент вывода: {combined[:400]}",
            detail_after_ssh,
        )
    if not combined:
        api_port = int(settings.xray_remote_api_port)
        log.warning(
            "SSH statsquery: пустой stdout+stderr при ssh_rc=%s server_id=%s — "
            "на узле выполните вручную ту же команду и проверьте JSON (Stats API, порт %s).",
            rc,
            server.id,
            api_port,
        )
        return (
            "Пустой ответ SSH: после команды нет ни stdout, ни stderr. "
            "Проверьте на VPS: `xray api statsquery --server=127.0.0.1:"
            f"{api_port}` (процесс xray, совпадение порта с XRAY_REMOTE_API_PORT).",
            detail_after_ssh,
        )

    json_start = combined.find("{")
    if json_start < 0:
        return (
            f"xray statsquery: не JSON (код {rc}): {combined[:400]}",
            detail_after_ssh,
        )

    json_text = combined[json_start:]
    try:
        raw_by_user = parse_statsquery_json(json_text)
    except json.JSONDecodeError as e:
        return (
            f"JSON: {e}; фрагмент: {combined[:400]}",
            detail_after_ssh.model_copy(
                update={"stdout_preview": _preview(combined)},
            ),
        )

    # Fallback в Xray: email u0@vpn → счётчики user>>>u0@... → uid=0, в БД нет User.id=0.
    if 0 in raw_by_user:
        z = raw_by_user.pop(0)
        uid0 = session.scalar(select(User.id).order_by(User.id.asc()).limit(1))
        if uid0 is not None:
            if uid0 in raw_by_user:
                raw_by_user[uid0]["up"] = raw_by_user[uid0].get("up", 0) + z.get(
                    "up",
                    0,
                )
                raw_by_user[uid0]["down"] = raw_by_user[uid0].get("down", 0) + z.get(
                    "down",
                    0,
                )
            else:
                raw_by_user[uid0] = z
            log.info(
                "xray stats: uid=0 (u0@vpn) отнесён к user_id=%s server_id=%s",
                uid0,
                server.id,
            )
        else:
            log.warning(
                "xray stats: uid=0 (u0@vpn), в БД нет пользователей — трафик не сохранён (server_id=%s)",
                server.id,
            )

    day = _traffic_day_utc()
    for uid, vals in raw_by_user.items():
        raw_up = int(vals.get("up") or 0)
        raw_down = int(vals.get("down") or 0)
        row = _get_or_create_day_row(session, uid, server, day)
        if row is None:
            continue
        row.up_bytes, row.raw_up = _merge_axis(row.up_bytes, row.raw_up, raw_up)
        row.down_bytes, row.raw_down = _merge_axis(
            row.down_bytes,
            row.raw_down,
            raw_down,
        )

    session.flush()
    log.info(
        "xray traffic collected server_id=%s users=%s",
        server.id,
        len(raw_by_user),
    )
    ok_detail = detail_after_ssh.model_copy(
        update={"parsed_users": len(raw_by_user)},
    )
    return None, ok_detail


def load_user_traffic_bundle_rows(
    session: Session,
    server_id: int,
    *,
    collected_at: datetime | None = None,
    collect_error: str | None = None,
    collect_detail: UserTrafficCollectDetail | None = None,
) -> ServerUserTrafficBundle:
    """
    Пользователи с активной подпиской или уже имеющие строку трафика на этом узле;
    LEFT JOIN — нули, если сбора ещё не было (иначе INNER давал пустой график).
    """
    today = utc_today()
    ut_latest = user_server_traffic_latest_subquery().alias("ut_latest")
    ut_prev = user_server_traffic_latest_strictly_before_calendar_day_subquery(today).alias(
        "ut_prev"
    )
    has_traffic_here = (
        select(1)
        .select_from(UserServerTraffic)
        .where(
            UserServerTraffic.user_id == User.id,
            UserServerTraffic.server_id == server_id,
        )
        .correlate(User)
    ).exists()
    stmt = (
        select(
            User,
            ut_latest.c.up_bytes,
            ut_latest.c.down_bytes,
            ut_latest.c.traffic_date,
            ut_prev.c.up_bytes,
            ut_prev.c.down_bytes,
        )
        .select_from(User)
        .outerjoin(
            ut_latest,
            and_(
                User.id == ut_latest.c.user_id,
                ut_latest.c.server_id == server_id,
            ),
        )
        .outerjoin(
            ut_prev,
            and_(
                User.id == ut_prev.c.user_id,
                ut_prev.c.server_id == server_id,
            ),
        )
        .where(
            or_(
                User.subscription_until.is_(None),
                User.subscription_until >= utc_today(),
                has_traffic_here,
            ),
        )
        .order_by(User.id.asc())
    )
    rows = session.execute(stmt).all()
    out: list[ServerUserTrafficRow] = []
    for user, up_raw, down_raw, latest_day, prev_up_raw, prev_down_raw in rows:
        up_b = int(up_raw or 0)
        down_b = int(down_raw or 0)
        p_up = int(prev_up_raw or 0)
        p_down = int(prev_down_raw or 0)
        latest_d = as_calendar_date(latest_day)
        if latest_d is None or latest_d != today:
            d_total = 0
        else:
            d_total = max(0, (up_b + down_b) - (p_up + p_down))
        out.append(
            ServerUserTrafficRow(
                user_id=user.id,
                telegram_id=user.telegram_id,
                up_bytes=up_b,
                down_bytes=down_b,
                total_bytes=up_b + down_b,
                delta_total_bytes=d_total,
            )
        )
    return ServerUserTrafficBundle(
        server_id=server_id,
        collected_at=collected_at,
        collect_error=collect_error,
        collect_detail=collect_detail,
        users=out,
    )
