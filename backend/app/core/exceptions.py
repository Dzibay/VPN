"""Единая иерархия исключений приложения с HTTP-семантикой.

Каждое исключение этой иерархии однозначно маппится в JSON-ответ ``{detail}`` с заданным
``status_code`` через :func:`app.core.error_handlers.register_exception_handlers`. Доменный
код использует именованные подклассы (``NotFoundError``, ``ConflictError`` и т.п.); код,
которому действительно нужен произвольный ``status_code``, может выбросить ``AppError(N, …)``
напрямую.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Базовая ошибка приложения с HTTP-кодом и опциональными заголовками ответа."""

    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = int(status_code)
        self.detail = "Ошибка запроса" if detail is None else detail
        self.headers = headers
        super().__init__(self.detail)


class BadRequestError(AppError):
    """HTTP 400: запрос принципиально некорректен (валидация, формат, бизнес-правило)."""

    def __init__(self, detail: str = "Некорректный запрос", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(400, detail, headers=headers)


class UnauthorizedError(AppError):
    """HTTP 401: токен отсутствует, недействителен или истёк (передавайте ``WWW-Authenticate``)."""

    def __init__(self, detail: str = "Требуется авторизация", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(401, detail, headers=headers)


class ForbiddenError(AppError):
    """HTTP 403: пользователь аутентифицирован, но операция запрещена для его роли/состояния."""

    def __init__(self, detail: str = "Недостаточно прав", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(403, detail, headers=headers)


class NotFoundError(AppError):
    """HTTP 404: запрашиваемая запись не найдена в БД (или её область видимости пуста)."""

    def __init__(self, detail: str = "Не найдено", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(404, detail, headers=headers)


class ConflictError(AppError):
    """HTTP 409: запрос корректен, но текущее состояние БД делает его невозможным."""

    def __init__(self, detail: str = "Конфликт данных", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(409, detail, headers=headers)


class UnprocessableEntityError(AppError):
    """HTTP 422: тело прошло формальную валидацию, но не удовлетворяет бизнес-правилам."""

    def __init__(self, detail: str = "Невозможно обработать запрос", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(422, detail, headers=headers)


class InternalServerError(AppError):
    """HTTP 500: внутренняя несогласованность, замеченная сервисом (для непредвиденных ошибок — uncaught)."""

    def __init__(self, detail: str = "Внутренняя ошибка сервера", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(500, detail, headers=headers)


class BadGatewayError(AppError):
    """HTTP 502: ошибка обращения к внешнему компоненту (Prometheus, узел по SSH, и т.п.)."""

    def __init__(self, detail: str = "Внешний сервис вернул ошибку", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(502, detail, headers=headers)


class ServiceUnavailableError(AppError):
    """HTTP 503: ресурс временно недоступен (Redis, очередь RQ, отсутствующая конфигурация)."""

    def __init__(self, detail: str = "Сервис временно недоступен", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(503, detail, headers=headers)
