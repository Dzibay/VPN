"""Проверки безопасности конфигурации при старте API.

Выполняются один раз на этапе bootstrap (см. :mod:`app.main`). Любая ошибка =
``RuntimeError`` с понятным сообщением: пусть Docker/systemd зафиксируют отказ старта,
вместо того чтобы процесс молча работал с открытыми защищёнными эндпоинтами.
"""

from __future__ import annotations

import logging

from app.config import Settings

log = logging.getLogger("app.startup_checks")

MIN_JWT_SECRET_LEN = 32


def validate_production_secrets(settings: Settings) -> None:
    """Жёсткие проверки боевого окружения; в ``DEBUG=true`` правила пропускаются.

    Если ``debug=False`` и ``JWT_SECRET`` пуст — это критическая уязвимость: гейтер
    :func:`app.core.dependencies.jwt_gate_active` отключает все ``require_roles``-зависимости,
    и админ-API становится открытым. Стартовать в таком режиме недопустимо.
    """
    if settings.debug:
        log.warning(
            "DEBUG=true: JWT_SECRET может быть пустым (используется небезопасный "
            "локальный fallback). Не используйте этот режим в продакшене.",
        )
        return

    issues: list[str] = []

    jwt_secret = (settings.jwt_secret or "").strip()
    if not jwt_secret:
        issues.append(
            "JWT_SECRET не задан. Без него защищённые эндпоинты становятся "
            "открытыми (jwt_gate_active отключает require_roles). "
            "Сгенерируйте секрет: `openssl rand -hex 32`.",
        )
    elif len(jwt_secret) < MIN_JWT_SECRET_LEN:
        issues.append(
            f"JWT_SECRET длиной {len(jwt_secret)} < {MIN_JWT_SECRET_LEN}: слишком короткий. "
            "Сгенерируйте сильный секрет: `openssl rand -hex 32`.",
        )

    if issues:
        bullets = "\n  - ".join(issues)
        raise RuntimeError(
            "Небезопасная конфигурация боевого окружения (DEBUG=false):\n  - "
            f"{bullets}",
        )
