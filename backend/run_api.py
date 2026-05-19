"""
Локальный запуск API (Windows + psycopg async).

Uvicorn с --loop auto на win32 создаёт ProactorEventLoop, с которым psycopg async
несовместим. Здесь включается SelectorEventLoop через политику и --loop none.

  cd backend
  python run_api.py

Эквивалент через uvicorn CLI (только Windows):

  uvicorn app.main:app --host 0.0.0.0 --port 5000 --loop none
  (перед этим в том же процессе нужна WindowsSelectorEventLoopPolicy — проще run_api.py)

Или явный класс loop:

  uvicorn app.main:app --host 0.0.0.0 --port 5000 --loop app.win_asyncio:selector_loop_factory
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5000,
        loop="none",
    )
