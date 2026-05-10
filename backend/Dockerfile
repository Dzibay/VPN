# VPN API + RQ worker (один образ, разные command/CMD в docker-compose).
#
# Запуск под непривилегированным пользователем app (UID/GID 10001) — стандартная защита
# от повышения привилегий через уязвимости Python/системных пакетов. Worker'у с
# bind-mount ``./secrets/ssh:/ssh:ro`` ключи должны быть доступны на чтение этому UID
# (на Linux-хосте: ``sudo chown -R 10001:10001 ./secrets/ssh && chmod 0700 …`` или
# переопределите ``user:`` в compose).
FROM python:3.12-slim-bookworm

# Системные зависимости:
#   curl           — HEALTHCHECK + сетевые проверки
#   openssh-client — провижининг узлов (worker запускает ssh)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/configurations ./configurations
COPY backend/worker ./worker
COPY database/init.sql ./database/init.sql
COPY database/migrate.sql ./database/migrate.sql
COPY database/rpc ./database/rpc

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --system --gid ${APP_GID} app \
    && useradd --system --uid ${APP_UID} --gid ${APP_GID} \
        --home-dir /app --shell /sbin/nologin app \
    && chown -R ${APP_UID}:${APP_GID} /app

USER ${APP_UID}:${APP_GID}

EXPOSE 8000

# /api/health — без обращения к БД и Redis, безопасно для частых проверок.
# В compose та же команда переопределяется на сервисном уровне с тонкой настройкой
# интервалов; этот HEALTHCHECK нужен для запусков `docker run` без compose.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
