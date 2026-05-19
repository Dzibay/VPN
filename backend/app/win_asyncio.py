"""Event loop для uvicorn на Windows (psycopg async не работает с ProactorEventLoop)."""

from __future__ import annotations

import asyncio

# Кастомный --loop: uvicorn импортирует символ и вызывает его как loop_factory(),
# поэтому нужен класс loop'а, а не функция-обёртка (иначе loop_factory() вернёт класс, не экземпляр).
selector_loop_factory = asyncio.SelectorEventLoop
