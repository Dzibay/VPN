"""
Комплексная проверка узла: TCP с хоста API, сверка с БД, каскад, node_exporter.
"""

from __future__ import annotations

import socket
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.infrastructure.persistence.models.server import Server
from app.domain.models.servers import HealthCheckItemRead, ServerPingRead


def _tcp_connect_probe(host: str, port: int, timeout: float) -> tuple[bool, float | None, str]:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as e:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        msg = str(e).strip() or type(e).__name__
        return False, elapsed_ms, msg
    elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
    return True, elapsed_ms, ""


def _pbk_ok(p: str | None) -> bool:
    s = (p or "").strip()
    return bool(s) and "(" not in s


def run_tcp_probes(
    host: str,
    vpn_port: int,
    *,
    ne_port: int | None,
    exit_host: str | None,
    exit_port: int | None,
    timeout_sec: float,
) -> dict:
    """
    Все TCP-пробы в одной функции (удобно вызывать из threadpool).
    ne_port None — пропустить; exit — опционально для каскада.
    """
    out: dict = {}
    t = max(0.5, float(timeout_sec))
    out["vpn"] = _tcp_connect_probe(host, int(vpn_port), t)
    if ne_port is not None and ne_port > 0:
        out["ne"] = _tcp_connect_probe(host, int(ne_port), min(3.0, t))
    if exit_host and exit_port and exit_port > 0:
        eh = (exit_host or "").strip()
        if eh:
            out["exit"] = _tcp_connect_probe(eh, int(exit_port), t)
    return out


async def build_server_health_read(
    session: AsyncSession,
    server: Server,
    settings: Settings,
    *,
    timeout_sec: float,
    tcp: dict,
) -> ServerPingRead:
    """Собрать ServerPingRead из БД + результатов `run_tcp_probes`."""
    host = (server.host or "").strip()
    port = int(server.port)
    checks: list[HealthCheckItemRead] = []

    v_ok, v_ms, v_err = tcp.get("vpn", (False, None, "no probe"))
    ne_ok_for_hint = "ne" in tcp and bool(tcp["ne"][0])
    ne_p = int(settings.provision_node_exporter_port)
    if v_ok:
        vpn_detail: str = "Слушатель отвечает"
    else:
        vpn_detail = f"недоступен: {v_err}"
        if ne_ok_for_hint:
            vpn_detail += (
                f" — на этом же IP порт {ne_p} (node_exporter) отвечает: машина online, "
                f"а на {port} нет слушающего Xray. Часто: `systemctl status xray`, "
                f"`ss -tlnp | grep {port}` и что inbound в config.json = порт {port}."
            )
    checks.append(
        HealthCheckItemRead(
            id="tcp_vless_inbound",
            label="TCP к порту Xray (VLESS/REALITY на узле)",
            ok=v_ok,
            detail=vpn_detail,
            severity="critical",
            latency_ms=v_ms,
        )
    )

    pr = bool(server.provision_ready)
    ps = (server.provision_status or "idle").strip()
    pe = (server.provision_error or "").strip()
    p_detail = f"в БД: provision_ready={pr}, статус «{ps}»"
    if pr:
        p_detail = f"в БД отмечен готовым (provision_ready), статус «{ps}»"
    else:
        if pe:
            p_detail += f". Последняя ошибка: {pe[:300]}{'…' if len(pe) > 300 else ''}"
        elif ps in ("queued", "running"):
            p_detail += " — воркер ещё выполняет или ждёт очереди."
        else:
            p_detail += " — сначала дождитесь успешного провижининга (Xray / полная установка)."
    checks.append(
        HealthCheckItemRead(
            id="db_provision",
            label="Провижнинг",
            ok=pr,
            detail=p_detail,
            severity="critical",
        )
    )

    is_act = bool(server.is_active)
    checks.append(
        HealthCheckItemRead(
            id="db_active",
            label="Сервер активен (подписка)",
            ok=is_act,
            detail="Участвует в выдаче подписки" if is_act else "Отключён (is_active=false) — в списке клиента не появится",
            severity="info" if is_act else "warning",
        )
    )

    pk = _pbk_ok(server.reality_public_key)
    sid = (server.reality_short_id or "").strip()
    k_ok = pk and bool(sid)
    checks.append(
        HealthCheckItemRead(
            id="xray_reality_keys",
            label="Ключи REALITY в БД (публичный, shortId)",
            ok=k_ok,
            detail="Ключи заданы" if k_ok else "Нет reality_public_key или пустой reality_short_id (после провижининга обновите список)",
            severity="critical",
        )
    )

    if "ne" in tcp:
        n_ok, n_ms, n_err = tcp["ne"]
        checks.append(
            HealthCheckItemRead(
                id="tcp_node_exporter",
                label=f"TCP к node_exporter (порт {ne_p}, метрики)",
                ok=n_ok,
                detail="OK" if n_ok else f"нет ответа: {n_err} (если не ставили exporter — нормально)",
                severity="info",
                latency_ms=n_ms,
            )
        )

    if server.is_cascade_ru_entry and server.cascade_next_server_id is not None:
        eid = int(server.cascade_next_server_id)
        ex = await session.get(Server, eid)
        cu = (server.cascade_egress_client_uuid or "").strip()
        c_ok = bool(cu) and ex is not None
        c_detail: str
        if not cu:
            c_detail = "Нет cascade_egress_client_uuid — пересохраните пару каскада в админке"
        elif ex is None:
            c_detail = f"Внешний сервер id={eid} не найден в БД"
        else:
            c_detail = f"Связь с exit id={eid}, UUID каскада на входе задан"
            if not _pbk_ok(ex.reality_public_key):
                c_ok = False
                c_detail += f"; на exit (id={eid}) нет reality_public_key"
        checks.append(
            HealthCheckItemRead(
                id="cascade_ru_config",
                label="Каскад (РФ-вход): настройка в БД",
                ok=c_ok,
                detail=c_detail,
                severity="critical",
            )
        )
        if ex is not None and "exit" in tcp:
            eh = (ex.host or "").strip() or "127.0.0.1"
            eport = int(ex.port)
            ex_ok, ex_ms, ex_err = tcp["exit"]
            checks.append(
                HealthCheckItemRead(
                    id="tcp_cascade_exit",
                    label=f"TCP к внешнему exit (Xray) {eh}:{eport}",
                    ok=ex_ok,
                    detail="Exit отвечает на TCP" if ex_ok else f"недоступен: {ex_err}",
                    severity="critical",
                    latency_ms=ex_ms,
                )
            )
    elif server.is_cascade_ru_entry and server.cascade_next_server_id is None:
        checks.append(
            HealthCheckItemRead(
                id="cascade_incomplete",
                label="Каскад: привязка exit",
                ok=False,
                detail="Вход (РФ) без внешнего сервера (cascade_next пуст) — настройте пару в админке",
                severity="critical",
            )
        )

    crit_ok = all(c.ok for c in checks if c.severity == "critical")
    overall_ok = crit_ok
    bad = [c for c in checks if c.severity == "critical" and not c.ok]
    if not bad and overall_ok:
        summary = (
            f"Узел {host}:{port} в порядке: TCP Xray OK"
            f"{f', {v_ms} мс' if v_ms is not None else ''}. "
            f"Провижнинг и ключи в БД согласованы. "
        )
        if "ne" in tcp:
            n_ok = tcp["ne"][0]
            summary += f"Node exporter: {'OK' if n_ok else 'без ответа (см. пункт ниже)'}. "
        if server.is_cascade_ru_entry and server.cascade_next_server_id:
            summary += "Пара каскада проверена. "
    else:
        parts: list[str] = [f"Есть критичные замечания по узлу {host}:{port}."]
        for c in bad:
            parts.append(f"{c.label}: {c.detail}")
        if not v_ok:
            head = f"Порт {port} (Xray) не принимает соединения: {v_err or 'ошибка'}."
            if ne_ok_for_hint:
                head += (
                    f" При этом {ne_p} (метрики) на том же IP отвечает — на {port} "
                    f"Xray, скорее всего, не запущен или слушает другой порт."
                )
            else:
                head += " Проверьте файрвол, что процесс Xray на узле listening на этом порту."
            parts.insert(0, head)
        summary = " ".join(parts)[:2000]

    return ServerPingRead(
        server_id=int(server.id),
        host=host,
        port=port,
        reachable=v_ok,
        latency_ms=v_ms,
        detail=summary[:500] if len(summary) > 500 else summary,
        check="health_multi",
        overall_ok=overall_ok,
        summary=summary,
        checks=checks,
    )
