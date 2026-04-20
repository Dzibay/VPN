#!/usr/bin/env python3
"""
Объективный стресс Xray через SOCKS: поэтапный рост «пользователей», лёгкая и средняя нагрузка, метрики.

Важно (интерпретация результатов):
- «Пользователь» здесь — модель поведения (лёгкие частые запросы или средние скачивания), не человек за ПК.
- Один генератор нагрузки (ваш ПК/VPS) может упереться в CPU/сокеты/домашний канал раньше сервера — для потолка сервера лучше гонять с мощной внешней машины.
- Сеть и CDN дают шум; повторите прогон 2–3 раза.
- Смотрите Prometheus (node_exporter) параллельно — коррелируйте с success/latency.

Установка и базовый прогон:
  pip install -r scripts/loadtest/requirements-loadtest.txt
  python scripts/loadtest/xray_load_suite.py --socks 127.0.0.1:1080 sweep

Графический интерфейс (tkinter):
  python scripts/loadtest/xray_load_suite_gui.py

Только средняя нагрузка (скачивания, без light):
  python scripts/loadtest/xray_load_suite.py --socks 127.0.0.1:1080 sweep --phase medium

Рекомендуемая методика:
  1) Грубый потолок (все воркеры крутят запросы без паузы):
     sweep с --ramp-mode mult --start 2 --max 256
  2) «Псевдо-пользователи» (мягче): лёгкая фаза с паузой между запросами:
     --no-light-saturated --light-think-ms 250 …
  3) После coarse ramp уточните W вручную --workers-list 48,56,64,72
  4) Сохраняйте отчёт: --json-out load-report.json

HTTP-коды вне SLA (по умолчанию 429 от CDN): не входят в sr_net и в условие --min-success,
чтобы рамп не останавливался из‑за rate limit. См. --exclude-http-from-sla.

Смешанный профиль (имитация пользователей + сводка потолка):
  python scripts/loadtest/xray_load_suite.py --socks 127.0.0.1:1080 mixed --json-out report.json
  Для честного heavy без CDN 429: свой --heavy-url https://ваш-сервер/static.bin

Зависимости: httpx[socks]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Пустой набор = не исключать ни одного HTTP-кода из sr_net
_SLA_EXCLUDE_NONE: frozenset[int] = frozenset()


DEFAULT_LIGHT_URLS = [
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://1.1.1.1/cdn-cgi/trace",
]
DEFAULT_MEDIUM_URLS = [
    "https://speed.cloudflare.com/__down?bytes=5000000",
    "https://speed.cloudflare.com/__down?bytes=10000000",
]


@dataclass
class StepStats:
    phase: str
    concurrency: int
    duration_sec: float
    saturated: bool
    think_ms: int
    ok: int
    fail: int
    rps_attempts: float
    rps_ok: float
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    mean_latency_ms: float | None
    throughput_mbps: float | None
    success_rate: float
    # Сводка исходов: ok, timeout, connect, proxy, read, write, http_4xx, http_5xx, http_other, other
    buckets: dict[str, int]
    # Для HTTP-ошибок — сколько раз какой статус (только неуспех)
    http_status_hits: dict[str, int]
    fail_p50_ms: float | None
    fail_p95_ms: float | None
    # Ответы CDN «не нашей вины» (по умолчанию 429): не в знаменателе sr_net
    sla_excluded: int
    success_rate_net: float
    rps_evaluated: float
    exclude_http_codes: list[int]
    profile: str = "sweep"
    by_kind: dict[str, Any] = field(default_factory=dict)
    idle_cycles: int = 0
    throughput_mbps_heavy: float | None = None


REPORT_VERSION = 1


def _parse_exclude_http_sla(raw: str) -> frozenset[int]:
    s = (raw or "").strip().lower()
    if not s or s in ("0", "none", "off", "-"):
        return _SLA_EXCLUDE_NONE
    out: set[int] = set()
    for part in s.replace(" ", "").split(","):
        if not part:
            continue
        out.add(int(part, 10))
    return frozenset(out)


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if p <= 0:
        return float(sorted_vals[0])
    if p >= 100:
        return float(sorted_vals[-1])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return float(d0 + d1)


def _classify_attempt(
    response: httpx.Response | None,
    exc: BaseException | None,
    *,
    sla_exclude_http: frozenset[int],
) -> tuple[bool, str, str]:
    """Возвращает (успех по «сырым» ok/fail, bucket для сводки, деталь для отладки)."""
    if exc is not None:
        if isinstance(exc, httpx.TimeoutException):
            return False, "timeout", type(exc).__name__
        if isinstance(exc, httpx.ProxyError):
            return False, "proxy", type(exc).__name__
        if isinstance(exc, httpx.ConnectError):
            return False, "connect", type(exc).__name__
        if isinstance(exc, httpx.ReadError):
            return False, "read", type(exc).__name__
        if isinstance(exc, httpx.WriteError):
            return False, "write", type(exc).__name__
        if isinstance(exc, httpx.RemoteProtocolError):
            return False, "remote_proto", type(exc).__name__
        if isinstance(exc, httpx.RequestError):
            return False, "request_err", type(exc).__name__
        return False, "other", type(exc).__name__[:48]
    if response is None:
        return False, "other", "no_response"
    c = response.status_code
    if sla_exclude_http and c in sla_exclude_http:
        return False, "sla_excluded", str(c)
    if 200 <= c < 400:
        return True, "ok", str(c)
    if 400 <= c < 500:
        return False, "http_4xx", str(c)
    if 500 <= c < 600:
        return False, "http_5xx", str(c)
    return False, "http_other", str(c)


def _stop_requested(stop_event: asyncio.Event | None) -> bool:
    return stop_event is not None and stop_event.is_set()


def _client(proxy: str, timeout_sec: float) -> httpx.AsyncClient:
    limits = httpx.Limits(max_keepalive_connections=32, max_connections=512)
    return httpx.AsyncClient(
        proxy=proxy,
        timeout=httpx.Timeout(timeout_sec),
        limits=limits,
        follow_redirects=True,
        http2=False,
    )


async def _worker_saturated(
    client: httpx.AsyncClient,
    urls: list[str],
    stop_at: float,
    results: list[tuple[bool, float, int, str, str]],
    lock: asyncio.Lock,
    sla_exclude_http: frozenset[int],
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    while time.monotonic() < stop_at and not _stop_requested(stop_event):
        url = random.choice(urls)
        t0 = time.perf_counter()
        r: httpx.Response | None = None
        exc: BaseException | None = None
        nbytes = 0
        try:
            r = await client.get(url)
            nbytes = len(r.content or b"")
        except BaseException as e:
            exc = e
        ok, bucket, detail = _classify_attempt(r, exc, sla_exclude_http=sla_exclude_http)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        async with lock:
            results.append((ok, dt_ms, nbytes, bucket, detail))
        await asyncio.sleep(0)


async def _worker_paced(
    client: httpx.AsyncClient,
    urls: list[str],
    stop_at: float,
    think_ms: int,
    results: list[tuple[bool, float, int, str, str]],
    lock: asyncio.Lock,
    sla_exclude_http: frozenset[int],
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    while time.monotonic() < stop_at and not _stop_requested(stop_event):
        url = random.choice(urls)
        t0 = time.perf_counter()
        r = None
        exc = None
        nbytes = 0
        try:
            r = await client.get(url)
            nbytes = len(r.content or b"")
        except BaseException as e:
            exc = e
        ok, bucket, detail = _classify_attempt(r, exc, sla_exclude_http=sla_exclude_http)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        async with lock:
            results.append((ok, dt_ms, nbytes, bucket, detail))
        if think_ms > 0:
            await asyncio.sleep(think_ms / 1000.0)


def _stats_for_kind_rows(
    rows: list[tuple[bool, float, int, str, str, str]],
    measured_wall: float,
) -> dict[str, Any]:
    """Метрики только по подмножеству HTTP-попыток одного вида (light/heavy)."""
    if not rows:
        return {
            "attempts": 0,
            "ok": 0,
            "fail": 0,
            "sla_excluded": 0,
            "success_rate": 0.0,
            "success_rate_net": 0.0,
            "p50_ms": None,
            "p95_ms": None,
            "mbps": None,
        }
    ok_n = sum(1 for r in rows if r[0])
    n_sla = sum(1 for r in rows if r[3] == "sla_excluded")
    denom_net = len(rows) - n_sla
    sr_net = (ok_n / denom_net) if denom_net > 0 else 0.0
    lat_ok = sorted([r[1] for r in rows if r[0]])
    b_ok = sum(r[2] for r in rows if r[0])
    mbps = (b_ok * 8) / measured_wall / 1_000_000 if measured_wall > 0 and b_ok else None
    return {
        "attempts": len(rows),
        "ok": ok_n,
        "fail": len(rows) - ok_n,
        "sla_excluded": n_sla,
        "success_rate": ok_n / max(1, len(rows)),
        "success_rate_net": sr_net,
        "p50_ms": _percentile(lat_ok, 50),
        "p95_ms": _percentile(lat_ok, 95),
        "mbps": mbps,
    }


async def _worker_mixed(
    client: httpx.AsyncClient,
    light_urls: list[str],
    heavy_urls: list[str],
    stop_at: float,
    results: list[tuple[bool, float, int, str, str, str]],
    lock: asyncio.Lock,
    sla_exclude_http: frozenset[int],
    *,
    weights: tuple[float, float, float],
    think_min_ms: float,
    think_max_ms: float,
    light_timeout: float,
    heavy_timeout: float,
    stop_event: asyncio.Event | None = None,
) -> None:
    w_light, w_heavy, w_idle = weights
    choices = ["light", "heavy", "idle"]

    async def _think() -> None:
        lo = min(think_min_ms, think_max_ms)
        hi = max(think_min_ms, think_max_ms)
        await asyncio.sleep(random.uniform(lo, hi) / 1000.0)

    while time.monotonic() < stop_at and not _stop_requested(stop_event):
        action = random.choices(choices, weights=[w_light, w_heavy, w_idle], k=1)[0]
        if action == "idle":
            t0 = time.perf_counter()
            await _think()
            dt_ms = (time.perf_counter() - t0) * 1000.0
            async with lock:
                results.append((True, dt_ms, 0, "idle", "", "idle"))
            continue

        urls = light_urls if action == "light" else heavy_urls
        url = random.choice(urls)
        to = light_timeout if action == "light" else heavy_timeout
        t0 = time.perf_counter()
        r: httpx.Response | None = None
        exc: BaseException | None = None
        nbytes = 0
        try:
            r = await client.get(url, timeout=httpx.Timeout(to))
            nbytes = len(r.content or b"")
        except BaseException as e:
            exc = e
        ok, bucket, detail = _classify_attempt(r, exc, sla_exclude_http=sla_exclude_http)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        async with lock:
            results.append((ok, dt_ms, nbytes, bucket, detail, action))
        await _think()


async def run_step_mixed(
    *,
    concurrency: int,
    duration_sec: float,
    warmup_sec: float,
    proxy: str,
    sla_exclude_http: frozenset[int],
    light_urls: list[str],
    heavy_urls: list[str],
    weights: tuple[float, float, float],
    think_min_ms: float,
    think_max_ms: float,
    light_timeout: float,
    heavy_timeout: float,
    stop_event: asyncio.Event | None = None,
) -> StepStats:
    lock: asyncio.Lock = asyncio.Lock()
    results: list[tuple[bool, float, int, str, str, str]] = []
    t0 = time.perf_counter()
    warm_end = t0 + warmup_sec
    t_end = t0 + warmup_sec + duration_sec
    client_timeout = max(light_timeout, heavy_timeout, 30.0)

    async def one_worker() -> None:
        async with _client(proxy, client_timeout) as client:
            await asyncio.sleep(max(0.0, warm_end - time.monotonic()))
            if _stop_requested(stop_event):
                return
            await _worker_mixed(
                client,
                light_urls,
                heavy_urls,
                t_end,
                results,
                lock,
                sla_exclude_http,
                weights=weights,
                think_min_ms=think_min_ms,
                think_max_ms=think_max_ms,
                light_timeout=light_timeout,
                heavy_timeout=heavy_timeout,
                stop_event=stop_event,
            )

    tasks = [asyncio.create_task(one_worker()) for _ in range(concurrency)]
    await asyncio.gather(*tasks)

    measured_wall = max(float(duration_sec), 0.001)
    http_rows = [r for r in results if r[5] in ("light", "heavy")]
    idle_cycles = sum(1 for r in results if r[5] == "idle")

    oks = [r for r in http_rows if r[0]]
    fails = [r for r in http_rows if not r[0]]
    ok_n, fail_n = len(oks), len(fails)
    bucket_ctr: Counter[str] = Counter()
    http_status_ctr: Counter[str] = Counter()
    for row in http_rows:
        bucket_ctr[row[3]] += 1
        if row[3] in ("http_4xx", "http_5xx", "http_other", "sla_excluded"):
            http_status_ctr[row[4]] += 1
    n_sla_excl = int(bucket_ctr.get("sla_excluded", 0))
    latencies = [r[1] for r in oks]
    latencies.sort()
    fail_for_latency = [
        r[1] for r in http_rows if not r[0] and r[3] != "sla_excluded"
    ]
    fail_latencies = sorted(fail_for_latency) if sla_exclude_http else sorted(
        [r[1] for r in http_rows if not r[0]]
    )
    fail_p50 = _percentile(fail_latencies, 50)
    fail_p95 = _percentile(fail_latencies, 95)
    total_bytes = sum(r[2] for r in oks)
    heavy_ok_bytes = sum(r[2] for r in http_rows if r[5] == "heavy" and r[0])

    rps_att = (ok_n + fail_n) / measured_wall
    rps_ok = ok_n / measured_wall
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    mean_lat = float(statistics.mean(latencies)) if latencies else None
    thr_mbps = None
    if total_bytes > 0 and measured_wall > 0:
        thr_mbps = (total_bytes * 8) / measured_wall / 1_000_000
    thr_heavy = None
    if heavy_ok_bytes > 0 and measured_wall > 0:
        thr_heavy = (heavy_ok_bytes * 8) / measured_wall / 1_000_000

    sr = ok_n / max(1, ok_n + fail_n)
    denom_net = ok_n + fail_n - n_sla_excl
    sr_net = (ok_n / denom_net) if denom_net > 0 else 0.0
    rps_eval = denom_net / measured_wall

    rows_light = [r for r in http_rows if r[5] == "light"]
    rows_heavy = [r for r in http_rows if r[5] == "heavy"]
    by_kind = {
        "light": _stats_for_kind_rows(rows_light, measured_wall),
        "heavy": _stats_for_kind_rows(rows_heavy, measured_wall),
        "_weights": {
            "light": weights[0],
            "heavy": weights[1],
            "idle": weights[2],
        },
        "_think_ms_range": [think_min_ms, think_max_ms],
    }

    return StepStats(
        phase="mixed",
        concurrency=concurrency,
        duration_sec=duration_sec,
        saturated=True,
        think_ms=int((think_min_ms + think_max_ms) / 2),
        ok=ok_n,
        fail=fail_n,
        rps_attempts=rps_att,
        rps_ok=rps_ok,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        mean_latency_ms=mean_lat,
        throughput_mbps=thr_mbps,
        success_rate=sr,
        buckets=dict(bucket_ctr),
        http_status_hits=dict(http_status_ctr),
        fail_p50_ms=fail_p50,
        fail_p95_ms=fail_p95,
        sla_excluded=n_sla_excl,
        success_rate_net=sr_net,
        rps_evaluated=rps_eval,
        exclude_http_codes=sorted(sla_exclude_http),
        profile="mixed",
        by_kind=by_kind,
        idle_cycles=idle_cycles,
        throughput_mbps_heavy=thr_heavy,
    )


async def run_step_fixed(
    *,
    phase: str,
    urls: list[str],
    concurrency: int,
    duration_sec: float,
    warmup_sec: float,
    saturated: bool,
    think_ms: int,
    proxy: str,
    timeout_sec: float,
    sla_exclude_http: frozenset[int],
    stop_event: asyncio.Event | None = None,
) -> StepStats:
    lock: asyncio.Lock = asyncio.Lock()
    results: list[tuple[bool, float, int, str, str]] = []
    t0 = time.perf_counter()
    warm_end = t0 + warmup_sec
    t_end = t0 + warmup_sec + duration_sec

    async def one_worker() -> None:
        async with _client(proxy, timeout_sec) as client:
            await asyncio.sleep(max(0.0, warm_end - time.monotonic()))
            if _stop_requested(stop_event):
                return
            if saturated:
                await _worker_saturated(
                    client,
                    urls,
                    t_end,
                    results,
                    lock,
                    sla_exclude_http,
                    stop_event=stop_event,
                )
            else:
                await _worker_paced(
                    client,
                    urls,
                    t_end,
                    think_ms,
                    results,
                    lock,
                    sla_exclude_http,
                    stop_event=stop_event,
                )

    tasks = [asyncio.create_task(one_worker()) for _ in range(concurrency)]
    await asyncio.gather(*tasks)

    # Все записи после разогрева; окно замера ≈ duration_sec
    measured_wall = max(float(duration_sec), 0.001)

    oks = [r for r in results if r[0]]
    fails = [r for r in results if not r[0]]
    ok_n, fail_n = len(oks), len(fails)
    bucket_ctr: Counter[str] = Counter()
    http_status_ctr: Counter[str] = Counter()
    for row in results:
        bucket_ctr[row[3]] += 1
        if row[3] in ("http_4xx", "http_5xx", "http_other", "sla_excluded"):
            http_status_ctr[row[4]] += 1
    n_sla_excl = int(bucket_ctr.get("sla_excluded", 0))
    latencies = [r[1] for r in oks]
    latencies.sort()
    fail_for_latency = [
        r[1]
        for r in results
        if not r[0] and r[3] != "sla_excluded"
    ]
    fail_latencies = sorted(fail_for_latency) if sla_exclude_http else sorted(
        [r[1] for r in results if not r[0]]
    )
    fail_p50 = _percentile(fail_latencies, 50)
    fail_p95 = _percentile(fail_latencies, 95)
    total_bytes = sum(r[2] for r in oks)

    rps_att = (ok_n + fail_n) / measured_wall
    rps_ok = ok_n / measured_wall

    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    mean_lat = float(statistics.mean(latencies)) if latencies else None

    # Throughput: только успешные ответы, биты/с по wall измерения
    thr_mbps = None
    if total_bytes > 0 and measured_wall > 0:
        thr_mbps = (total_bytes * 8) / measured_wall / 1_000_000

    sr = ok_n / max(1, ok_n + fail_n)
    denom_net = ok_n + fail_n - n_sla_excl
    sr_net = (ok_n / denom_net) if denom_net > 0 else 0.0
    rps_eval = denom_net / measured_wall

    return StepStats(
        phase=phase,
        concurrency=concurrency,
        duration_sec=duration_sec,
        saturated=saturated,
        think_ms=think_ms,
        ok=ok_n,
        fail=fail_n,
        rps_attempts=rps_att,
        rps_ok=rps_ok,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        mean_latency_ms=mean_lat,
        throughput_mbps=thr_mbps,
        success_rate=sr,
        buckets=dict(bucket_ctr),
        http_status_hits=dict(http_status_ctr),
        fail_p50_ms=fail_p50,
        fail_p95_ms=fail_p95,
        sla_excluded=n_sla_excl,
        success_rate_net=sr_net,
        rps_evaluated=rps_eval,
        exclude_http_codes=sorted(sla_exclude_http),
    )


def _ramp_values(start: int, max_c: int, mode: str, step_add: int, mult: float) -> list[int]:
    out: list[int] = []
    v = start
    seen: set[int] = set()
    while v <= max_c:
        if v not in seen:
            out.append(v)
            seen.add(v)
        if mode == "mult":
            v = max(v + 1, int(round(v * mult)))
        else:
            v += step_add
    if max_c not in seen and max_c > 0:
        out.append(max_c)
    return sorted(set(out))


def _print_row(s: StepStats) -> None:
    thr = f"{s.throughput_mbps:.2f}" if s.throughput_mbps is not None else "—"
    p50 = f"{s.p50_ms:.0f}" if s.p50_ms is not None else "—"
    p95 = f"{s.p95_ms:.0f}" if s.p95_ms is not None else "—"
    p99 = f"{s.p99_ms:.0f}" if s.p99_ms is not None else "—"
    mlat = f"{s.mean_latency_ms:.0f}" if s.mean_latency_ms is not None else "—"
    mode = "насыщение" if s.saturated else f"пacing {s.think_ms}ms"
    net_cols = ""
    if s.exclude_http_codes:
        net_cols = (
            f" | sr_net={s.success_rate_net*100:5.1f}% "
            f"sla_excl={s.sla_excluded} RPS_eval≈{s.rps_evaluated:5.1f}"
        )
    print(
        f"{s.phase:8} | W={s.concurrency:4} | {mode:16} | ok={s.ok:5} fail={s.fail:5} "
        f"sr={s.success_rate*100:5.1f}%{net_cols} | RPS≈{s.rps_attempts:6.1f} (ok {s.rps_ok:6.1f}) | "
        f"p50/p95/p99={p50}/{p95}/{p99} ms | Mbps≈{thr} | mlat={mlat} ms"
    )


def _print_diagnostics(s: StepStats) -> None:
    """Сводка bucket-ов и HTTP-статусов при неуспехе."""
    if not s.buckets:
        return
    order = (
        "ok",
        "sla_excluded",
        "timeout",
        "connect",
        "proxy",
        "read",
        "write",
        "remote_proto",
        "request_err",
        "http_4xx",
        "http_5xx",
        "http_other",
        "other",
    )
    rank = {name: i for i, name in enumerate(order)}
    parts = [
        f"{k}={s.buckets[k]}"
        for k in sorted(s.buckets.keys(), key=lambda x: (rank.get(x, 99), -s.buckets[x]))
    ]
    print(f"   исходы: {' | '.join(parts)}")
    if s.http_status_hits:
        h = ", ".join(
            f"{code}×{n}"
            for code, n in sorted(s.http_status_hits.items(), key=lambda x: -x[1])
        )
        print(f"   HTTP-коды (ошибки + sla_excluded): {h}")
    if s.sla_excluded and s.exclude_http_codes:
        print(
            f"   SLA: коды {s.exclude_http_codes} не входят в sr_net и в порог --min-success "
            f"(сырой sr смотрите в первой колонке)."
        )
    if s.fail and (s.fail_p50_ms is not None or s.fail_p95_ms is not None):
        fp50 = f"{s.fail_p50_ms:.0f}" if s.fail_p50_ms is not None else "—"
        fp95 = f"{s.fail_p95_ms:.0f}" if s.fail_p95_ms is not None else "—"
        print(f"   латентность неуспехов p50/p95: {fp50} / {fp95} ms (часто ≈ таймаут при обрыве)")


def _normalize_weights(a: float, b: float, c: float) -> tuple[float, float, float]:
    s = float(a) + float(b) + float(c)
    if s <= 0:
        raise ValueError("Сумма весов light+heavy+idle должна быть > 0")
    return (float(a) / s, float(b) / s, float(c) / s)


def _print_by_kind(s: StepStats) -> None:
    if s.profile != "mixed":
        return
    bk = s.by_kind or {}
    print("   по видам:")
    for kind in ("light", "heavy"):
        sub = bk.get(kind) or {}
        if not isinstance(sub, dict):
            continue
        p50 = sub.get("p50_ms")
        p95 = sub.get("p95_ms")
        p50s = f"{p50:.0f}" if p50 is not None else "—"
        p95s = f"{p95:.0f}" if p95 is not None else "—"
        mb = sub.get("mbps")
        mbs = f"{mb:.2f}" if mb is not None else "—"
        print(
            f"      {kind:5} attempts={sub.get('attempts', 0)} ok={sub.get('ok', 0)} "
            f"fail={sub.get('fail', 0)} sla_excl={sub.get('sla_excluded', 0)} "
            f"sr_net={sub.get('success_rate_net', 0)*100:5.1f}% "
            f"p50/p95={p50s}/{p95s} ms Mbps≈{mbs}"
        )
    if s.idle_cycles:
        print(f"      idle  циклов={s.idle_cycles} (только пауза, без HTTP)")
    w = bk.get("_weights") or {}
    tr = bk.get("_think_ms_range") or []
    if w and tr:
        print(
            f"      модель: w(light/heavy/idle)={w.get('light'):.2f}/{w.get('heavy'):.2f}/{w.get('idle'):.2f}, "
            f"think_ms∈[{tr[0]:.0f},{tr[1]:.0f}]"
        )


def _print_ceiling_summary(steps: list[StepStats], args: argparse.Namespace) -> None:
    if not steps:
        return
    min_sr = float(args.min_success)
    max_p95 = float(args.max_p95_ms)
    last_good: int | None = None
    peak_mbps_h = -1.0
    peak_w_mbps = 0
    peak_rps = -1.0
    peak_w_rps = 0
    sla_ratios: list[float] = []

    for st in steps:
        sr_stop = st.success_rate_net if st.exclude_http_codes else st.success_rate
        p95_ok = st.p95_ms is not None and st.p95_ms <= max_p95 if max_p95 > 0 else True
        if sr_stop >= min_sr and p95_ok:
            last_good = st.concurrency
        th = st.throughput_mbps_heavy if st.throughput_mbps_heavy is not None else 0.0
        if th > peak_mbps_h:
            peak_mbps_h = th
            peak_w_mbps = st.concurrency
        if st.rps_evaluated > peak_rps:
            peak_rps = st.rps_evaluated
            peak_w_rps = st.concurrency
        tot = st.ok + st.fail
        if tot > 0:
            sla_ratios.append(st.sla_excluded / tot)

    print("\n" + "═" * 72)
    print("Сводка «потолок» (по шагам рампа)")
    print(
        f"  Последнее W с порогами sr≥{min_sr*100:.0f}% "
        f"и p95≤{max_p95:.0f} ms (если p95 выкл — только sr): "
        f"{last_good if last_good is not None else '— (ни один шаг не прошёл)'}"
    )
    if peak_mbps_h >= 0:
        print(
            f"  Пик Mbps (только heavy, успешные): {peak_mbps_h:.2f} при W={peak_w_mbps}"
        )
    if peak_rps >= 0:
        print(f"  Пик RPS_eval (HTTP без sla_excl в знаменателе): {peak_rps:.2f} при W={peak_w_rps}")
    if sla_ratios:
        avg_sla = sum(sla_ratios) / len(sla_ratios)
        if avg_sla > 0.15:
            print(
                f"  Внимание: средняя доля sla_excluded (напр. 429) ≈ {avg_sla*100:.1f}% попыток — "
                "для честного heavy задайте свой --heavy-url на статике вне CDN."
            )
    print("═" * 72)


async def cmd_sweep(args: argparse.Namespace) -> int:
    if getattr(args, "phase", "all") == "medium":
        args.skip_light = True
        args.skip_medium = False
    elif getattr(args, "phase", "all") == "light":
        args.skip_light = False
        args.skip_medium = True

    proxy = f"socks5://{args.socks.strip()}"
    if "://" in args.socks:
        proxy = args.socks.strip()

    light_urls = list(args.light_url) if args.light_url else DEFAULT_LIGHT_URLS
    medium_urls = list(args.medium_url) if args.medium_url else DEFAULT_MEDIUM_URLS

    if args.workers_list:
        ramp = [int(x.strip()) for x in args.workers_list.split(",") if x.strip()]
    else:
        ramp = _ramp_values(args.start, args.max, args.ramp_mode, args.ramp_add, args.ramp_mult)

    report: list[dict[str, Any]] = []

    phases: list[tuple[str, list[str], bool, int, float]] = []
    if not args.skip_light:
        phases.append(
            (
                "light",
                light_urls,
                args.light_saturated,
                args.light_think_ms,
                args.light_timeout,
            )
        )
    if not args.skip_medium:
        phases.append(
            (
                "medium",
                medium_urls,
                args.medium_saturated,
                args.medium_think_ms,
                args.medium_timeout,
            )
        )

    if not phases:
        print("Ошибка: нет фаз для прогона. Проверьте --phase, --skip-light и --skip-medium.")
        return 2

    sla_ex = _parse_exclude_http_sla(args.exclude_http_from_sla)

    print(f"Прокси: {proxy}")
    print(f"Шаги параллелизма: {ramp}")
    print(
        f"Исключить HTTP из SLA (sr_net, стоп): {sorted(sla_ex) if sla_ex else '— (сырой sr)'}"
    )
    print(
        f"Порог остановки: success_rate_net>={args.min_success*100:.0f}% "
        f"(при исключениях), иначе sr; p95 успешных<={args.max_p95_ms} ms (0=выкл)"
    )
    print("—" * 120)

    for phase_name, urls, saturated, think_ms, timeout_sec in phases:
        stop_phase = False
        print(f"\n=== Фаза: {phase_name} ===")
        for w in ramp:
            if stop_phase:
                break
            print(f"… прогон W={w}, {args.duration}s (+warmup {args.warmup}s)", flush=True)
            st = await run_step_fixed(
                phase=phase_name,
                urls=urls,
                concurrency=w,
                duration_sec=float(args.duration),
                warmup_sec=float(args.warmup),
                saturated=saturated,
                think_ms=think_ms,
                proxy=proxy,
                timeout_sec=timeout_sec,
                sla_exclude_http=sla_ex,
            )
            _print_row(st)
            _print_diagnostics(st)
            report.append(asdict(st))
            sr_stop = st.success_rate_net if st.exclude_http_codes else st.success_rate
            if sr_stop < args.min_success:
                print(
                    f"   ! success_rate (для стопа) {sr_stop*100:.1f}% < {args.min_success*100:.0f}% "
                    f"(сырой sr={st.success_rate*100:.1f}%) — дальнейший рост по фазе обычно бессмысленен."
                )
                stop_phase = args.stop_on_degrade
            if args.max_p95_ms > 0 and st.p95_ms is not None and st.p95_ms > args.max_p95_ms:
                print(f"   ! p95 {st.p95_ms:.0f} ms > {args.max_p95_ms} ms")
                stop_phase = args.stop_on_degrade

    if args.json_out:
        p = Path(args.json_out)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON: {p.resolve()}")

    print("\nКак читать: ищите максимальное W, где sr_net (или sr) и p95 ещё в норме; сравните light vs medium.")
    print(
        "sla_excluded / 429: лимит CDN; sr_net отражает «реальные» ошибки цепочки при заданных исключениях."
    )
    print("Пропускная способность на фазе medium — колонка Mbps≈ (агрегат по всем успешным ответам).")
    return 0


async def cmd_mixed(args: argparse.Namespace) -> int:
    proxy = f"socks5://{args.socks.strip()}"
    if "://" in args.socks:
        proxy = args.socks.strip()

    try:
        weights = _normalize_weights(
            args.light_weight, args.heavy_weight, args.idle_weight
        )
    except ValueError as e:
        print(f"Ошибка: {e}")
        return 2

    light_urls = list(args.light_url) if args.light_url else list(DEFAULT_LIGHT_URLS)
    heavy_urls = list(args.heavy_url) if args.heavy_url else list(DEFAULT_MEDIUM_URLS)

    if args.workers_list:
        ramp = [int(x.strip()) for x in args.workers_list.split(",") if x.strip()]
    else:
        ramp = _ramp_values(args.start, args.max, args.ramp_mode, args.ramp_add, args.ramp_mult)

    sla_ex = _parse_exclude_http_sla(args.exclude_http_from_sla)
    steps: list[StepStats] = []

    print(f"Профиль: mixed (имитация пользователей), прокси: {proxy}")
    print(f"Шаги W: {ramp}")
    print(
        f"Веса light/heavy/idle: {weights[0]:.3f} / {weights[1]:.3f} / {weights[2]:.3f} "
        f"| think_ms ∈ [{args.think_min_ms:.0f}, {args.think_max_ms:.0f}]"
    )
    print(f"Исключить HTTP из SLA: {sorted(sla_ex) if sla_ex else '—'}")
    print(
        f"Пороги стопа: sr_net≥{args.min_success*100:.0f}%, p95≤{args.max_p95_ms:.0f} ms"
    )
    print("—" * 120)

    stop_phase = False
    for w in ramp:
        if stop_phase:
            break
        print(f"\n… mixed W={w}, {args.duration}s (+warmup {args.warmup}s)", flush=True)
        st = await run_step_mixed(
            concurrency=w,
            duration_sec=float(args.duration),
            warmup_sec=float(args.warmup),
            proxy=proxy,
            sla_exclude_http=sla_ex,
            light_urls=light_urls,
            heavy_urls=heavy_urls,
            weights=weights,
            think_min_ms=float(args.think_min_ms),
            think_max_ms=float(args.think_max_ms),
            light_timeout=float(args.light_timeout),
            heavy_timeout=float(args.heavy_timeout),
        )
        _print_row(st)
        _print_diagnostics(st)
        _print_by_kind(st)
        steps.append(st)

        sr_stop = st.success_rate_net if st.exclude_http_codes else st.success_rate
        if sr_stop < args.min_success:
            print(
                f"   ! success_rate (для стопа) {sr_stop*100:.1f}% < {args.min_success*100:.0f}% "
                f"(сырой sr={st.success_rate*100:.1f}%)"
            )
            stop_phase = args.stop_on_degrade
        if args.max_p95_ms > 0 and st.p95_ms is not None and st.p95_ms > args.max_p95_ms:
            print(f"   ! p95 успешных {st.p95_ms:.0f} ms > {args.max_p95_ms} ms")
            stop_phase = args.stop_on_degrade

    _print_ceiling_summary(steps, args)

    if args.json_out:
        p = Path(args.json_out)
        payload: dict[str, Any] = {
            "report_version": REPORT_VERSION,
            "profile": "mixed",
            "meta": {
                "proxy": proxy,
                "ramp": ramp,
                "weights": {"light": weights[0], "heavy": weights[1], "idle": weights[2]},
                "think_ms_range": [args.think_min_ms, args.think_max_ms],
                "light_urls": light_urls,
                "heavy_urls": heavy_urls,
                "light_timeout": args.light_timeout,
                "heavy_timeout": args.heavy_timeout,
                "duration_per_step": args.duration,
                "warmup": args.warmup,
                "exclude_http_from_sla": sorted(sla_ex),
                "min_success": args.min_success,
                "max_p95_ms": args.max_p95_ms,
            },
            "steps": [asdict(s) for s in steps],
        }
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON: {p.resolve()}")

    print(
        "\nЧестный heavy: положите файл на свой VPS и укажите --heavy-url, "
        "иначе 429 от публичных CDN искажают сырой sr (sr_net их отфильтровывает)."
    )
    return 0


def _add_sla_and_ramp_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--duration", type=float, default=45.0, help="Длительность каждого шага (сек)")
    ap.add_argument("--warmup", type=float, default=5.0, help="Разогрев перед замером (сек)")
    ap.add_argument("--start", type=int, default=2, help="Начальное W")
    ap.add_argument("--max", type=int, default=128, help="Максимальное W")
    ap.add_argument("--ramp-mode", choices=["mult", "add"], default="mult")
    ap.add_argument("--ramp-mult", type=float, default=2.0)
    ap.add_argument("--ramp-add", type=int, default=8)
    ap.add_argument("--workers-list", default="", help="Список W через запятую")
    ap.add_argument(
        "--exclude-http-from-sla",
        default="429",
        metavar="CODES",
        help="Коды HTTP вне sr_net (none/off — выкл)",
    )
    ap.add_argument("--min-success", type=float, default=0.92)
    ap.add_argument("--max-p95-ms", type=float, default=8000.0)
    ap.add_argument(
        "--stop-on-degrade",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    ap.add_argument("--json-out", default="")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Поэтапная нагрузка Xray через SOCKS (httpx).")
    p.add_argument("--socks", required=True, help="SOCKS5, напр. 127.0.0.1:1080")
    sub = p.add_subparsers(dest="cmd", required=True)

    sw = sub.add_parser("sweep", help="Рост параллелизма + фазы light/medium")
    _add_sla_and_ramp_args(sw)
    sw.add_argument("--light-url", action="append", help="URL лёгкой фазы (можно несколько)")
    sw.add_argument("--medium-url", action="append", help="URL средней фазы")
    sw.add_argument(
        "--light-saturated",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Лёгкая фаза: непрерывные запросы (true) или pacing (--no-light-saturated)",
    )
    sw.add_argument("--light-think-ms", type=int, default=0, help="Пауза между запросами (если не saturated)")
    sw.add_argument("--light-timeout", type=float, default=30.0)
    sw.add_argument(
        "--medium-saturated",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Средняя фаза: непрерывные качающие запросы",
    )
    sw.add_argument("--medium-think-ms", type=int, default=0)
    sw.add_argument("--medium-timeout", type=float, default=120.0)
    sw.add_argument(
        "--phase",
        choices=["all", "light", "medium"],
        default="all",
        help="all — обе фазы; light / medium — только одна (удобно: --phase medium)",
    )
    sw.add_argument("--skip-light", action="store_true", help="Вместо этого можно --phase medium")
    sw.add_argument("--skip-medium", action="store_true", help="Вместо этого можно --phase light")
    sw.set_defaults(func=cmd_sweep)

    mx = sub.add_parser(
        "mixed",
        help="Смешанный профиль (light/heavy/idle) + рамп; сводка потолка; JSON с meta",
    )
    _add_sla_and_ramp_args(mx)
    mx.add_argument(
        "--light-weight",
        type=float,
        default=0.55,
        help="Вероятность лёгкого запроса (до нормализации)",
    )
    mx.add_argument(
        "--heavy-weight",
        type=float,
        default=0.25,
        help="Вероятность тяжёлого скачивания",
    )
    mx.add_argument(
        "--idle-weight",
        type=float,
        default=0.20,
        help="Вероятность только паузы (без HTTP)",
    )
    mx.add_argument(
        "--think-min-ms",
        type=float,
        default=100.0,
        help="Мин. пауза «как пользователь» после действия (мс)",
    )
    mx.add_argument(
        "--think-max-ms",
        type=float,
        default=800.0,
        help="Макс. пауза после действия (мс)",
    )
    mx.add_argument(
        "--light-url",
        action="append",
        help="URL лёгких запросов (несколько раз для списка)",
    )
    mx.add_argument(
        "--heavy-url",
        action="append",
        help="URL тяжёлых загрузок; для честного теста — свой статик на VPS",
    )
    mx.add_argument("--light-timeout", type=float, default=30.0)
    mx.add_argument("--heavy-timeout", type=float, default=120.0)
    mx.set_defaults(func=cmd_mixed)

    return p


async def amain() -> int:
    parser = build_parser()
    args = parser.parse_args()
    fn = getattr(args, "func", None)
    if fn is None:
        parser.print_help()
        return 2
    return await fn(args)


def main() -> None:
    try:
        raise SystemExit(asyncio.run(amain()))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
