#!/usr/bin/env python3
"""
Нагрузка на узел Xray (VLESS + REALITY): локальный клиент Xray + SOCKS5 + параллельные HTTP-запросы.

Метрики в вашем Prometheus / админке — это node_exporter (см. backend/app/services/prometheus_node.py):
  - node_cpu_seconds_total, node_load1, node_memory_*, node_network_*_bytes_total,
    node_netstat_Tcp_CurrEstab и т.д.

Скрипт не шлёт метрики в Prometheus; он создаёт нагрузку на xray-core, чтобы графики в UI наполнились.

Примеры:
  python xray_proxy_loadtest.py "vless://UUID@1.2.3.4:443?encryption=none&security=reality&type=tcp&flow=xtls-rprx-vision&sni=www.amazon.com&fp=chrome&pbk=...&sid=..."
  XRAY_BIN=C:\\bin\\xray.exe python xray_proxy_loadtest.py --vless-file subscription_link.txt --duration 120 --workers 32

Уже поднят клиент (SOCKS на 1080)? Тогда:
  python xray_proxy_loadtest.py --socks 127.0.0.1:1080 --duration 60 --workers 16
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


def _parse_vless_uri(raw: str) -> dict:
    u = (raw or "").strip()
    if not u.startswith("vless://"):
        raise ValueError("Ожидается ссылка vless://… (как в подписке).")
    parsed = urlparse(u)
    if parsed.scheme != "vless":
        raise ValueError("Некорректная схема URI.")
    uuid = unquote(parsed.username or "")
    if not uuid:
        raise ValueError("В ссылке нет UUID.")
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("В ссылке нет хоста.")
    port = parsed.port or 443
    q = parse_qs(parsed.query or "", keep_blank_values=True)

    def q1(key: str, default: str = "") -> str:
        vals = q.get(key)
        if not vals:
            return default
        return (vals[0] or default).strip()

    pbk = q1("pbk")
    sid = q1("sid")
    if not pbk:
        raise ValueError("В query нет pbk (REALITY public key).")
    return {
        "uuid": uuid,
        "host": host,
        "port": int(port),
        "flow": q1("flow", "xtls-rprx-vision"),
        "sni": q1("sni"),
        "fp": q1("fp", "chrome"),
        "pbk": pbk,
        "sid": sid,
    }


def _client_config(
    *,
    host: str,
    port: int,
    uuid: str,
    flow: str,
    sni: str,
    fp: str,
    pbk: str,
    sid: str,
    socks_listen: str,
    socks_port: int,
) -> dict:
    if not sni:
        raise ValueError("SNI пуст — в ссылке должен быть параметр sni.")
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": socks_listen,
                "port": socks_port,
                "protocol": "socks",
                "tag": "socks-in",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "tag": "proxy",
                "settings": {
                    "vnext": [
                        {
                            "address": host,
                            "port": port,
                            "users": [
                                {
                                    "id": uuid,
                                    "encryption": "none",
                                    "flow": flow,
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "fingerprint": fp,
                        "serverName": sni,
                        "publicKey": pbk,
                        "shortId": sid,
                        "spiderX": "/",
                    },
                },
            },
            {"protocol": "freedom", "tag": "direct"},
        ],
    }


def _curl_bin() -> str:
    env = (os.environ.get("CURL_BIN") or "").strip()
    if env:
        return env
    return "curl.exe" if sys.platform == "win32" else "curl"


def _one_download(
    curl: str,
    proxy: str,
    url: str,
    timeout_sec: int,
    insecure: bool,
) -> tuple[bool, float]:
    """Один GET через SOCKS5 (remote DNS: socks5h). Возвращает (ok, seconds)."""
    t0 = time.perf_counter()
    cmd = [
        curl,
        "-sS",
        "-x",
        f"socks5h://{proxy}",
        "--connect-timeout",
        str(max(5, min(timeout_sec, 120))),
        "-m",
        str(max(10, min(timeout_sec, 600))),
        "-o",
        os.devnull,
        "-w",
        "%{http_code}",
        url,
    ]
    if insecure:
        cmd.insert(1, "-k")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec + 5,
        )
        elapsed = time.perf_counter() - t0
        code = (r.stdout or "").strip()
        ok = r.returncode == 0 and code.isdigit() and 200 <= int(code) < 400
        return ok, elapsed
    except subprocess.TimeoutExpired:
        return False, time.perf_counter() - t0
    except OSError:
        return False, time.perf_counter() - t0


def _worker(
    *,
    proxy: str,
    urls: list[str],
    until: float,
    timeout_sec: int,
    insecure: bool,
    stats: dict,
    lock: threading.Lock,
) -> None:
    curl = _curl_bin()
    local_ok = local_fail = 0
    while time.monotonic() < until:
        url = random.choice(urls)
        ok, _ = _one_download(curl, proxy, url, timeout_sec, insecure)
        if ok:
            local_ok += 1
        else:
            local_fail += 1
    with lock:
        stats["ok"] += local_ok
        stats["fail"] += local_fail


def _start_xray(bin_path: Path, cfg_path: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [str(bin_path), "run", "-c", str(cfg_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Нагрузочный прогон через Xray VLESS+REALITY → SOCKS → HTTP.")
    ap.add_argument(
        "vless_uri",
        nargs="?",
        default="",
        help="Одна строка vless://… (как из подписки).",
    )
    ap.add_argument("--vless-file", type=Path, help="Файл с одной строкой vless://.")
    ap.add_argument(
        "--socks",
        metavar="HOST:PORT",
        default="",
        help="Не поднимать Xray: использовать готовый SOCKS5 (например 127.0.0.1:1080).",
    )
    ap.add_argument(
        "--xray-bin",
        default=os.environ.get("XRAY_BIN", "").strip() or "",
        help="Путь к xray (или переменная окружения XRAY_BIN). По умолчанию: xray в PATH.",
    )
    ap.add_argument("--socks-listen", default="127.0.0.1", help="Listen для inbound SOCKS (режим с Xray).")
    ap.add_argument("--socks-port", type=int, default=0, help="Порт SOCKS (0 = свободный порт).")
    ap.add_argument("--duration", type=int, default=60, help="Длительность секунд.")
    ap.add_argument("--workers", type=int, default=16, help="Число параллельных потоков запросов.")
    ap.add_argument(
        "--target-url",
        action="append",
        dest="target_urls",
        help="URL для скачивания (можно несколько). По умолчанию — несколько крупных статик CDN.",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="Таймаут одного запроса (сек), curl -m / connect-timeout.",
    )
    ap.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="curl -k (если целевой HTTPS с самоподписанным сертификатом).",
    )
    args = ap.parse_args()

    default_urls = [
        "https://speed.cloudflare.com/__down?bytes=10000000",
        "https://speed.cloudflare.com/__down?bytes=25000000",
        "https://cachefly.cachefly.net/100mb.test",
    ]
    urls = list(args.target_urls) if args.target_urls else default_urls

    socks_addr: str
    xray_proc: subprocess.Popen | None = None
    tmp_cfg: Path | None = None

    try:
        if args.socks.strip():
            socks_addr = args.socks.strip()
            if ":" not in socks_addr:
                ap.error("--socks должен быть HOST:PORT")
        else:
            text = (args.vless_uri or "").strip()
            if args.vless_file:
                text = args.vless_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0].strip()
            if not text:
                ap.error("Нужна ссылка vless:// (аргумент или --vless-file) либо --socks.")
            params = _parse_vless_uri(text)

            xray_path = Path(args.xray_bin) if args.xray_bin else Path(shutil.which("xray") or "")
            if not xray_path or not xray_path.is_file():
                ap.error(
                    "Не найден бинарник xray. Укажите --xray-bin или положите xray в PATH, "
                    "либо используйте --socks с уже запущенным клиентом."
                )

            if args.socks_port:
                port = int(args.socks_port)
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind((args.socks_listen, 0))
                port = s.getsockname()[1]
                s.close()

            cfg = _client_config(
                host=params["host"],
                port=params["port"],
                uuid=params["uuid"],
                flow=params["flow"],
                sni=params["sni"],
                fp=params["fp"],
                pbk=params["pbk"],
                sid=params["sid"],
                socks_listen=args.socks_listen,
                socks_port=port,
            )
            tmp = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                delete=False,
                encoding="utf-8",
            )
            tmp_cfg = Path(tmp.name)
            json.dump(cfg, tmp, indent=2)
            tmp.close()

            xray_proc = _start_xray(xray_path, tmp_cfg)
            time.sleep(1.2)
            if xray_proc.poll() is not None:
                ap.error(
                    "Xray завершился сразу после старта — проверьте ссылку, версию xray и что порт SOCKS свободен."
                )

            socks_addr = f"{args.socks_listen}:{port}"
            print(f"[loadtest] Xray client PID {xray_proc.pid}, SOCKS {socks_addr} → {params['host']}:{params['port']}")

        print(
            f"[loadtest] duration={args.duration}s workers={args.workers} urls={len(urls)} "
            f"proxy=socks5h://{socks_addr}"
        )
        print(
            "[loadtest] Смотрите Prometheus / аналитику узла: CPU, net_rx/net_tx Mbps, "
            "tcp_established, load1 (instance = node_exporter)."
        )

        until = time.monotonic() + max(1, args.duration)
        stats: dict = defaultdict(int)
        lock = threading.Lock()
        threads = [
            threading.Thread(
                target=_worker,
                kwargs={
                    "proxy": socks_addr,
                    "urls": urls,
                    "until": until,
                    "timeout_sec": args.timeout,
                    "insecure": args.insecure,
                    "stats": stats,
                    "lock": lock,
                },
            )
            for _ in range(max(1, args.workers))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ok = stats["ok"]
        fail = stats["fail"]
        total = ok + fail
        rate = total / max(1, args.duration)
        print(
            f"[loadtest] готово: ok={ok} fail={fail} total={total} (~{rate:.1f} req/s суммарно)"
        )
        return 0 if fail == 0 else 2

    finally:
        if xray_proc and xray_proc.poll() is None:
            if sys.platform == "win32":
                xray_proc.terminate()
            else:
                xray_proc.send_signal(signal.SIGTERM)
            try:
                xray_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xray_proc.kill()
        if tmp_cfg and tmp_cfg.is_file():
            try:
                tmp_cfg.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
