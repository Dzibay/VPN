#!/usr/bin/env python3
"""
Графический интерфейс для нагрузочного теста Xray через SOCKS (обёртка над xray_load_suite).

Запуск:
  python scripts/loadtest/xray_load_suite_gui.py

Требуется: pip install -r scripts/loadtest/requirements-loadtest.txt
"""

from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

LOADTEST_DIR = Path(__file__).resolve().parent
if str(LOADTEST_DIR) not in sys.path:
    sys.path.insert(0, str(LOADTEST_DIR))

import xray_load_suite as xls  # noqa: E402

# Доп. URL для профиля «высокая» (тяжёлые скачивания)
HIGH_MEDIUM_URLS = list(xls.DEFAULT_MEDIUM_URLS) + [
    "https://speed.cloudflare.com/__down?bytes=25000000",
]

# Дефолтные доли mixed (в процентах, сумма не обязана быть 100 — нормализуем)
MIXED_PCT_DEFAULT = (55, 25, 20)

_METRICS_HELP = """Расшифровка столбца «Значение»:

• Успех (сырой) — доля успешных HTTP-ответов среди всех попыток (включая ответы с кодами вроде 429 от CDN, если они не исключены).

• sr_net — доля успеха «для оценки цепочки»: ответы с кодами из поля «HTTP вне SLA» не считаются ни успехом, ни ошибкой в этом показателе.

• p50 / p95 / p99 — задержки только по успешным ответам (мс): медиана и перцентили времени от запроса до полного ответа.

• Поток — суммарная скорость по успешным ответам за время замера (все воркеры вместе), Мбит/с.

• RPS (eval) — оценка запросов в секунду; при sr_net в знаменателе не учитываются исключённые HTTP-коды.

• Нагрузка — эвристика 0…100 по задержке, потоку и ошибкам (не загрузка CPU сервера)."""


def _proxy_from_sock_field(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "socks5://127.0.0.1:1080"
    if "://" in s:
        return s
    return f"socks5://{s}"


def _stress_index(stats: xls.StepStats, workers: int, mbps_scale: float) -> float:
    """0 = «легко», 100 = «упорно» — эвристика для шкалы, не абсолют."""
    thr = stats.throughput_mbps or 0.0
    p95 = stats.p95_ms or 0.0
    sr = stats.success_rate_net if stats.exclude_http_codes else stats.success_rate
    sr = max(0.0, min(1.0, sr))
    if mbps_scale <= 0:
        mbps_scale = 150.0
    t = min(1.0, thr / mbps_scale)
    lat = min(1.0, p95 / 8000.0) if p95 > 0 else 0.0
    err = 1.0 - sr
    w = min(1.0, workers / 128.0)
    return max(0.0, min(100.0, 100.0 * (0.35 * t + 0.28 * lat + 0.27 * err + 0.10 * w)))


class ProxyLoadTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Нагрузочный тест прокси (Xray / SOCKS)")
        self.geometry("960x860")
        self.minsize(820, 720)

        self._thread: threading.Thread | None = None
        self._thread_loop: asyncio.AbstractEventLoop | None = None
        self._async_stop: asyncio.Event | None = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._running = False
        self._last_stats: xls.StepStats | None = None
        self._last_workers: int = 8
        self._progress_active = False
        self._tick_after_id: str | None = None
        self._progress_t0 = 0.0
        self._progress_total = 1.0
        self._progress_warm = 0.0
        self._progress_dur = 0.0

        self._build_ui()
        self.after(120, self._poll_queue)

    def _scroll_wrap(self, parent: tk.Widget) -> ttk.Frame:
        """Вертикальный скролл: возвращает внутренний фрейм для контента."""
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner_win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner(_e: Any = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_inner)

        def _on_canvas_cfg(e: Any) -> None:
            canvas.itemconfigure(inner_win, width=max(int(e.width) - 4, 1))

        canvas.bind("<Configure>", _on_canvas_cfg)
        canvas.configure(yscrollcommand=sb.set)

        def _on_wheel(e: Any) -> None:
            d = getattr(e, "delta", 0)
            if d:
                canvas.yview_scroll(int(-1 * (d / 120)), "units")

        canvas.bind("<MouseWheel>", _on_wheel)
        canvas.bind("<Button-4>", lambda _e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda _e: canvas.yview_scroll(1, "units"))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        outer.pack(fill=tk.BOTH, expand=True)
        return inner

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tab1 = ttk.Frame(self.notebook)
        self.notebook.add(tab1, text="Параметры и замер")
        inner1 = self._scroll_wrap(tab1)

        ttk.Label(
            inner1,
            text="Локальный SOCKS5 должен быть подключён к вашему Xray (как у клиента).",
            font=tkfont.Font(size=9),
        ).pack(anchor=tk.W)

        row1 = ttk.Frame(inner1)
        row1.pack(fill=tk.X, **pad)
        ttk.Label(row1, text="SOCKS (хост:порт или URL):").pack(side=tk.LEFT)
        self.var_socks = tk.StringVar(value="127.0.0.1:1080")
        ttk.Entry(row1, textvariable=self.var_socks, width=42).pack(
            side=tk.LEFT, padx=6, fill=tk.X, expand=True
        )

        row2 = ttk.Frame(inner1)
        row2.pack(fill=tk.X, **pad)
        ttk.Label(row2, text="Профиль нагрузки:").pack(side=tk.LEFT)
        self.var_profile = tk.StringVar(value="medium")
        profiles = ttk.Combobox(
            row2,
            textvariable=self.var_profile,
            width=28,
            state="readonly",
            values=("light", "medium", "high", "mixed"),
        )
        profiles.pack(side=tk.LEFT, padx=6)
        profiles.bind("<<ComboboxSelected>>", lambda _e: self._sync_profile_ui())
        ttk.Label(
            row2,
            text="light=мелкие запросы · medium · high=крупнее объём · mixed=смесь (настройки ниже)",
            font=tkfont.Font(size=8),
        ).pack(side=tk.LEFT)

        row3 = ttk.Frame(inner1)
        row3.pack(fill=tk.X, **pad)
        ttk.Label(row3, text="Пользователей (W):").pack(side=tk.LEFT)
        self.var_workers = tk.IntVar(value=8)
        ttk.Spinbox(row3, from_=1, to=256, textvariable=self.var_workers, width=5).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(row3, text="Длительность (с):").pack(side=tk.LEFT, padx=(16, 0))
        self.var_duration = tk.DoubleVar(value=45.0)
        ttk.Spinbox(row3, from_=5, to=600, increment=5, textvariable=self.var_duration, width=6).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(row3, text="Разогрев (с):").pack(side=tk.LEFT, padx=(16, 0))
        self.var_warmup = tk.DoubleVar(value=5.0)
        ttk.Spinbox(row3, from_=0, to=120, increment=1, textvariable=self.var_warmup, width=5).pack(
            side=tk.LEFT, padx=4
        )

        self._row4 = ttk.LabelFrame(inner1, text="Дополнительно (опционально)", padding=6)
        self._row4.pack(fill=tk.X, **pad)
        self._lbl_custom_url = ttk.Label(
            self._row4,
            text="URL для замены (профили light / medium / high, через запятую):",
        )
        self._lbl_custom_url.pack(anchor=tk.W)
        self.var_custom_urls = tk.StringVar(value="")
        self._entry_custom_urls = ttk.Entry(self._row4, textvariable=self.var_custom_urls)
        self._entry_custom_urls.pack(fill=tk.X, pady=2)
        row4b = ttk.Frame(self._row4)
        row4b.pack(fill=tk.X)
        ttk.Label(row4b, text="HTTP вне SLA (sr_net), напр. 429:").pack(side=tk.LEFT)
        self.var_exclude_sla = tk.StringVar(value="429")
        ttk.Entry(row4b, textvariable=self.var_exclude_sla, width=12).pack(side=tk.LEFT, padx=6)
        ttk.Label(row4b, text="Макс. Mbps для шкалы графика:").pack(side=tk.LEFT, padx=(16, 0))
        self.var_mbps_scale = tk.DoubleVar(value=200.0)
        ttk.Spinbox(row4b, from_=10, to=2000, increment=10, textvariable=self.var_mbps_scale, width=5).pack(
            side=tk.LEFT, padx=4
        )

        self.frame_mixed = ttk.LabelFrame(
            inner1,
            text="Профиль mixed — модель «как пользователь»",
            padding=8,
        )
        ttk.Label(
            self.frame_mixed,
            text=(
                "На каждом шаге воркер случайно выбирает: лёгкий HTTP, тяжёлое скачивание или паузу (idle). "
                "Доли задаются весами; пауза между действиями — think. Пустые URL — встроенные списки по умолчанию."
            ),
            font=tkfont.Font(size=8),
            wraplength=880,
        ).pack(anchor=tk.W, pady=(0, 6))

        wrow = ttk.Frame(self.frame_mixed)
        wrow.pack(fill=tk.X, pady=2)
        ttk.Label(wrow, text="Вес light %:").pack(side=tk.LEFT)
        self.var_mixed_w_light = tk.IntVar(value=MIXED_PCT_DEFAULT[0])
        ttk.Spinbox(wrow, from_=0, to=100, textvariable=self.var_mixed_w_light, width=4).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(wrow, text="heavy %:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_mixed_w_heavy = tk.IntVar(value=MIXED_PCT_DEFAULT[1])
        ttk.Spinbox(wrow, from_=0, to=100, textvariable=self.var_mixed_w_heavy, width=4).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(wrow, text="idle %:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_mixed_w_idle = tk.IntVar(value=MIXED_PCT_DEFAULT[2])
        ttk.Spinbox(wrow, from_=0, to=100, textvariable=self.var_mixed_w_idle, width=4).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(wrow, text="(сумма произвольная — перед запуском нормализуется к 1)").pack(
            side=tk.LEFT, padx=(8, 0)
        )

        trow = ttk.Frame(self.frame_mixed)
        trow.pack(fill=tk.X, pady=2)
        ttk.Label(trow, text="Пауза после действия think (мс), от:").pack(side=tk.LEFT)
        self.var_mixed_think_min = tk.DoubleVar(value=100.0)
        ttk.Spinbox(
            trow, from_=0, to=10000, increment=50, textvariable=self.var_mixed_think_min, width=7
        ).pack(side=tk.LEFT, padx=4)
        ttk.Label(trow, text="до:").pack(side=tk.LEFT, padx=(8, 0))
        self.var_mixed_think_max = tk.DoubleVar(value=800.0)
        ttk.Spinbox(
            trow, from_=0, to=30000, increment=50, textvariable=self.var_mixed_think_max, width=7
        ).pack(side=tk.LEFT, padx=4)

        torow = ttk.Frame(self.frame_mixed)
        torow.pack(fill=tk.X, pady=2)
        ttk.Label(torow, text="Таймаут light (с):").pack(side=tk.LEFT)
        self.var_mixed_to_light = tk.DoubleVar(value=30.0)
        ttk.Spinbox(torow, from_=5, to=600, increment=5, textvariable=self.var_mixed_to_light, width=6).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(torow, text="heavy (с):").pack(side=tk.LEFT, padx=(12, 0))
        self.var_mixed_to_heavy = tk.DoubleVar(value=120.0)
        ttk.Spinbox(torow, from_=10, to=900, increment=10, textvariable=self.var_mixed_to_heavy, width=6).pack(
            side=tk.LEFT, padx=4
        )

        ttk.Label(self.frame_mixed, text="URL для light (через запятую):").pack(anchor=tk.W, pady=(6, 0))
        self.var_mixed_light_urls = tk.StringVar(value="")
        ttk.Entry(self.frame_mixed, textvariable=self.var_mixed_light_urls).pack(fill=tk.X, pady=2)
        ttk.Label(self.frame_mixed, text="URL для heavy (через запятую):").pack(anchor=tk.W)
        self.var_mixed_heavy_urls = tk.StringVar(value="")
        ttk.Entry(self.frame_mixed, textvariable=self.var_mixed_heavy_urls).pack(fill=tk.X, pady=2)

        row5 = ttk.Frame(inner1)
        row5.pack(fill=tk.X, **pad)
        self.btn_start = ttk.Button(row5, text="Старт", command=self._on_start)
        self.btn_start.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(row5, text="Стоп", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=8)
        self.var_status = tk.StringVar(value="Готов.")
        ttk.Label(row5, textvariable=self.var_status).pack(side=tk.LEFT, padx=12)

        prog_fr = ttk.Frame(inner1)
        prog_fr.pack(fill=tk.X, **pad)
        self.progress = ttk.Progressbar(
            prog_fr,
            mode="determinate",
            maximum=100,
            length=400,
        )
        self.progress.pack(fill=tk.X)
        self.var_progress_detail = tk.StringVar(value="")
        ttk.Label(prog_fr, textvariable=self.var_progress_detail, font=tkfont.Font(size=9)).pack(
            anchor=tk.W, pady=(4, 0)
        )

        metrics = ttk.LabelFrame(inner1, text="Показатели (после шага)", padding=8)
        metrics.pack(fill=tk.X, **pad)
        help_box = tk.Text(
            metrics,
            height=11,
            wrap=tk.WORD,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=4,
            pady=4,
        )
        help_box.insert("1.0", _METRICS_HELP)
        help_box.config(state=tk.DISABLED, cursor="arrow")
        help_box.pack(fill=tk.X, pady=(0, 8))

        self.var_sr = tk.StringVar(value="—")
        self.var_sr_net = tk.StringVar(value="—")
        self.var_p50 = tk.StringVar(value="—")
        self.var_p95 = tk.StringVar(value="—")
        self.var_p99 = tk.StringVar(value="—")
        self.var_mbps = tk.StringVar(value="—")
        self.var_rps = tk.StringVar(value="—")
        self.var_stress = tk.StringVar(value="—")
        grid = ttk.Frame(metrics)
        grid.pack(fill=tk.X)
        for i, (a, b) in enumerate(
            [
                ("Успех (сырой):", self.var_sr),
                ("sr_net:", self.var_sr_net),
                ("Задержка p50 (мс):", self.var_p50),
                ("Задержка p95 (мс):", self.var_p95),
                ("Задержка p99 (мс):", self.var_p99),
                ("Поток (Мбит/с):", self.var_mbps),
                ("RPS (eval):", self.var_rps),
                ("Нагрузка 0…100:", self.var_stress),
            ]
        ):
            ttk.Label(grid, text=a).grid(row=i, column=0, sticky=tk.W, pady=1)
            ttk.Label(grid, textvariable=b, width=24, anchor=tk.W).grid(
                row=i, column=1, sticky=tk.W, pady=1
            )

        tab2 = ttk.Frame(self.notebook)
        self.notebook.add(tab2, text="Диаграммы")
        inner2 = self._scroll_wrap(tab2)
        canvas_frame = ttk.LabelFrame(inner2, text="Диаграммы", padding=8)
        canvas_frame.pack(fill=tk.X, **pad)
        diag_hint = ttk.Label(
            canvas_frame,
            text=(
                "Зелёная — sr_net; оранжевая — насколько велика p95 относительно 8 с; "
                "голубая — поток относительно «Макс. Mbps» выше; розовая — сводная эвристика нагрузки."
            ),
            font=tkfont.Font(size=8),
            wraplength=860,
        )
        diag_hint.pack(anchor=tk.W, pady=(0, 4))
        self.canvas = tk.Canvas(canvas_frame, height=280, bg="#1e1e2e", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        tab3 = ttk.Frame(self.notebook)
        self.notebook.add(tab3, text="Лог")
        log_toolbar = ttk.Frame(tab3)
        log_toolbar.pack(fill=tk.X, **pad)
        ttk.Button(
            log_toolbar,
            text="Копировать JSON в буфер обмена",
            command=self._copy_log_json,
        ).pack(side=tk.LEFT)
        ttk.Label(
            log_toolbar,
            text="(можно также выделить текст мышью и Ctrl+C)",
            font=tkfont.Font(size=8),
        ).pack(side=tk.LEFT, padx=(12, 0))
        log_outer = ttk.Frame(tab3)
        log_outer.pack(fill=tk.BOTH, expand=True, **pad)
        log_sb = ttk.Scrollbar(log_outer)
        self.txt_log = tk.Text(
            log_outer,
            height=18,
            wrap=tk.WORD,
            font=("Consolas", 9),
            yscrollcommand=log_sb.set,
        )
        log_sb.config(command=self.txt_log.yview)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._pad_outer = pad
        self._sync_profile_ui()

    def _copy_log_json(self) -> None:
        text = self.txt_log.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("Копирование", "Лог пуст — сначала выполните замер.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError:
            messagebox.showerror("Копирование", "Не удалось записать в буфер обмена.")
            return
        self.var_status.set("JSON скопирован в буфер обмена.")

    def _sync_profile_ui(self) -> None:
        p = (self.var_profile.get() or "medium").strip().lower()
        pad = self._pad_outer
        if p == "mixed":
            self._lbl_custom_url.config(
                text="Общий URL (для light/medium/high). В mixed отключён — используйте поля в блоке «Профиль mixed» ниже:",
            )
            self._entry_custom_urls.config(state=tk.DISABLED)
            self.frame_mixed.pack(fill=tk.X, **pad, after=self._row4)
        else:
            self.frame_mixed.pack_forget()
            self._lbl_custom_url.config(
                text="URL для замены (профили light / medium / high, через запятую):",
            )
            self._entry_custom_urls.config(state=tk.NORMAL)

    def _on_canvas_configure(self, _event: Any = None) -> None:
        if self._last_stats is not None:
            self._draw_bars(self._last_stats, self._last_workers)

    def _draw_bars(self, stats: xls.StepStats, workers: int) -> None:
        self.canvas.delete("all")
        w = float(self.canvas.winfo_width() or 880)
        margin = 24
        bar_h = 28
        gap = 16
        mbps_scale = float(self.var_mbps_scale.get() or 200.0)

        sr = stats.success_rate_net if stats.exclude_http_codes else stats.success_rate
        sr = max(0.0, min(1.0, sr))
        p95 = stats.p95_ms or 0.0
        thr = stats.throughput_mbps or 0.0
        stress = _stress_index(stats, workers, mbps_scale)

        bars: list[tuple[str, float, str]] = [
            ("Качество (sr_net)", sr * 100.0, "#4ade80"),
            ("Задержка p95 (норм. к 8 с)", min(100.0, (p95 / 8000.0) * 100.0) if p95 else 0.0, "#fbbf24"),
            ("Поток Mbps (к шкале)", min(100.0, (thr / mbps_scale) * 100.0), "#38bdf8"),
            ("Сводная нагрузка", stress, "#f472b6"),
        ]

        y = margin
        for name, pct, color in bars:
            pct = max(0.0, min(100.0, pct))
            self.canvas.create_text(
                margin, y + bar_h / 2, text=name, anchor=tk.W, fill="#cdd6f4", font=("Segoe UI", 10)
            )
            x0 = margin + 180
            x1 = x0 + (w - margin * 2 - 180) * (pct / 100.0)
            self.canvas.create_rectangle(x0, y, x0 + (w - margin * 2 - 180), y + bar_h, outline="#45475a", width=1)
            self.canvas.create_rectangle(x0, y, x1, y + bar_h, fill=color, outline="")
            self.canvas.create_text(
                x0 + (w - margin * 2 - 180) + 8,
                y + bar_h / 2,
                text=f"{pct:.0f}%",
                anchor=tk.W,
                fill="#cdd6f4",
                font=("Segoe UI", 10)
            )
            y += bar_h + gap

        bottom = y + margin
        self.canvas.configure(scrollregion=(0, 0, max(w, 1.0), float(bottom)))
        need_h = max(260, min(440, int(bottom + 8)))
        self.canvas.configure(height=need_h)

    def _parse_csv_urls(self, raw: str) -> list[str] | None:
        s = (raw or "").strip()
        if not s:
            return None
        return [u.strip() for u in s.split(",") if u.strip()]

    def _cancel_progress_tick(self) -> None:
        self._progress_active = False
        if self._tick_after_id is not None:
            try:
                self.after_cancel(self._tick_after_id)
            except (tk.TclError, ValueError):
                pass
            self._tick_after_id = None

    def _tick_progress(self) -> None:
        if not self._progress_active or not self._running:
            return
        now = time.monotonic()
        elapsed = now - self._progress_t0
        total = self._progress_total
        w = self._progress_warm
        d = self._progress_dur

        if total <= 0:
            pct = 0.0
        elif elapsed >= total:
            pct = 100.0
            self.var_progress_detail.set(
                f"Прошло {elapsed:.1f} с (план {total:.1f} с). Ожидаем завершение запросов…"
            )
        else:
            pct = 100.0 * elapsed / total
            if w > 0 and elapsed < w:
                left_w = w - elapsed
                self.var_progress_detail.set(
                    f"Разогрев: {elapsed:.1f} / {w:.1f} с  ·  до начала замера ≈ {left_w:.1f} с  "
                    f"·  всего этапов ≈ {total:.1f} с"
                )
            else:
                me = max(0.0, elapsed - w)
                left_m = max(0.0, d - me)
                self.var_progress_detail.set(
                    f"Замер: {me:.1f} / {d:.1f} с  ·  осталось ≈ {left_m:.1f} с  "
                    f"·  прошло {elapsed:.1f} / {total:.1f} с"
                )

        self.progress["value"] = pct
        if self._progress_active and self._running:
            self._tick_after_id = self.after(200, self._tick_progress)

    def _on_start(self) -> None:
        if self._running:
            return
        pro = (self.var_profile.get() or "medium").strip().lower()
        if pro == "mixed":
            ws = (
                self.var_mixed_w_light.get()
                + self.var_mixed_w_heavy.get()
                + self.var_mixed_w_idle.get()
            )
            if ws <= 0:
                messagebox.showerror(
                    "Mixed",
                    "Сумма весов light + heavy + idle должна быть больше 0.",
                )
                return
        self._cancel_progress_tick()
        warm = float(self.var_warmup.get())
        dur = float(self.var_duration.get())
        self._progress_warm = max(0.0, warm)
        self._progress_dur = max(0.0, dur)
        self._progress_total = max(0.001, self._progress_warm + self._progress_dur)
        self._progress_t0 = time.monotonic()
        self.progress["value"] = 0
        self.var_progress_detail.set(
            f"Всего по таймеру ≈ {self._progress_total:.1f} с (разогрев {self._progress_warm:.1f} с + замер {self._progress_dur:.1f} с)"
        )
        self._progress_active = True

        self._running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.var_status.set("Запуск…")
        self.txt_log.delete("1.0", tk.END)
        self._tick_progress()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def _on_stop(self) -> None:
        loop = self._thread_loop
        ev = self._async_stop
        if loop and ev:
            loop.call_soon_threadsafe(ev.set)
        self.var_status.set("Остановка…")

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._thread_loop = loop

        async def runner() -> None:
            stop = asyncio.Event()
            self._async_stop = stop
            try:
                await self._async_run_test(stop)
            except asyncio.CancelledError:
                pass
            finally:
                self._async_stop = None

        try:
            loop.run_until_complete(runner())
        except Exception:
            self._ui_queue.put(("error", traceback.format_exc()))
        finally:
            self._thread_loop = None
            self._ui_queue.put(("done", None))

    async def _async_run_test(self, stop: asyncio.Event) -> None:
        proxy = _proxy_from_sock_field(self.var_socks.get())
        w = int(self.var_workers.get())
        dur = float(self.var_duration.get())
        warm = float(self.var_warmup.get())
        profile = (self.var_profile.get() or "medium").strip().lower()
        sla = xls._parse_exclude_http_sla(self.var_exclude_sla.get())

        custom = self._parse_csv_urls(self.var_custom_urls.get())

        self._ui_queue.put(("status", f"Прокси: {proxy}  |  W={w}  |  профиль={profile}"))

        if profile == "mixed":
            lw = self._parse_csv_urls(self.var_mixed_light_urls.get())
            if not lw:
                lw = list(xls.DEFAULT_LIGHT_URLS)
            hw = self._parse_csv_urls(self.var_mixed_heavy_urls.get())
            if not hw:
                hw = list(xls.DEFAULT_MEDIUM_URLS)
            weights_n = xls._normalize_weights(
                self.var_mixed_w_light.get() / 100.0,
                self.var_mixed_w_heavy.get() / 100.0,
                self.var_mixed_w_idle.get() / 100.0,
            )
            st = await xls.run_step_mixed(
                concurrency=w,
                duration_sec=dur,
                warmup_sec=warm,
                proxy=proxy,
                sla_exclude_http=sla,
                light_urls=lw,
                heavy_urls=hw,
                weights=weights_n,
                think_min_ms=float(self.var_mixed_think_min.get()),
                think_max_ms=float(self.var_mixed_think_max.get()),
                light_timeout=float(self.var_mixed_to_light.get()),
                heavy_timeout=float(self.var_mixed_to_heavy.get()),
                stop_event=stop,
            )
        else:
            if profile == "light":
                phase = "light"
                urls = custom if custom else list(xls.DEFAULT_LIGHT_URLS)
                to = 30.0
                saturated = True
                think = 0
            elif profile == "medium":
                phase = "medium"
                urls = custom if custom else list(xls.DEFAULT_MEDIUM_URLS)
                to = 120.0
                saturated = True
                think = 0
            elif profile == "high":
                phase = "medium"
                urls = custom if custom else HIGH_MEDIUM_URLS
                to = 120.0
                saturated = True
                think = 0
            else:
                phase = "medium"
                urls = list(xls.DEFAULT_MEDIUM_URLS)
                to = 120.0
                saturated = True
                think = 0

            st = await xls.run_step_fixed(
                phase=phase,
                urls=urls,
                concurrency=w,
                duration_sec=dur,
                warmup_sec=warm,
                saturated=saturated,
                think_ms=think,
                proxy=proxy,
                timeout_sec=to,
                sla_exclude_http=sla,
                stop_event=stop,
            )

        self._ui_queue.put(("result", (st, w)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "status":
                    self.var_status.set(str(payload))
                elif kind == "result":
                    st, w = payload
                    self._apply_result(st, w)
                elif kind == "error":
                    self._cancel_progress_tick()
                    self.progress["value"] = 0
                    self.var_progress_detail.set("")
                    messagebox.showerror("Ошибка", payload)
                    self.var_status.set("Ошибка.")
                elif kind == "done":
                    self._cancel_progress_tick()
                    self._running = False
                    self.btn_start.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)
                    wall = time.monotonic() - self._progress_t0
                    self.progress["value"] = 100
                    st_msg = self.var_status.get()
                    if st_msg.startswith("Ошибка"):
                        self.var_progress_detail.set(f"Завершено после ошибки (≈ {wall:.1f} с).")
                    else:
                        self.var_progress_detail.set(
                            f"Итог: ≈ {wall:.1f} с wall-clock "
                            f"(план {self._progress_total:.1f} с: разогрев + замер)."
                        )
                    if st_msg.startswith("Запуск") or st_msg == "Остановка…":
                        self.var_status.set("Готов.")
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _apply_result(self, st: xls.StepStats, workers: int) -> None:
        self._last_stats = st
        self._last_workers = workers
        self.var_sr.set(f"{st.success_rate * 100:.1f}%")
        self.var_sr_net.set(f"{st.success_rate_net * 100:.1f}%")
        self.var_p50.set(f"{st.p50_ms:.0f}" if st.p50_ms is not None else "—")
        self.var_p95.set(f"{st.p95_ms:.0f}" if st.p95_ms is not None else "—")
        self.var_p99.set(f"{st.p99_ms:.0f}" if st.p99_ms is not None else "—")
        self.var_mbps.set(f"{st.throughput_mbps:.2f}" if st.throughput_mbps is not None else "—")
        self.var_rps.set(f"{st.rps_evaluated:.2f}")
        mbps_scale = float(self.var_mbps_scale.get() or 200.0)
        stress = _stress_index(st, workers, mbps_scale)
        self.var_stress.set(f"{stress:.0f} (чем выше, тем тяжелее для канала)")
        self._draw_bars(st, workers)
        payload: dict[str, Any] = {"step": asdict(st)}
        self.txt_log.insert(tk.END, json.dumps(payload, indent=2, ensure_ascii=False))
        self.var_status.set("Замер завершён.")


def main() -> None:
    app = ProxyLoadTestApp()
    app.mainloop()


if __name__ == "__main__":
    main()
