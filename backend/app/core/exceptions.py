"""Исключения прикладного слоя → однозначно маппятся на HTTP в ``error_handlers``."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Базовая ошибка API: обрабатывается централизованно (как HTTPException по телу ответа)."""

    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = "Ошибка запроса" if detail is None else detail
        self.headers = headers
        super().__init__(self.detail)


class BadRequestError(AppError):
    def __init__(self, detail: str = "Некорректный запрос", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(400, detail, headers=headers)


class UnauthorizedError(AppError):
    def __init__(self, detail: str = "Требуется авторизация", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(401, detail, headers=headers)


class ForbiddenError(AppError):
    def __init__(self, detail: str = "Недостаточно прав", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(403, detail, headers=headers)


class NotFoundError(AppError):
    def __init__(self, detail: str = "Не найдено", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(404, detail, headers=headers)


class ConflictError(AppError):
    def __init__(self, detail: str = "Конфликт данных", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(409, detail, headers=headers)


class ServiceUnavailableError(AppError):
    def __init__(self, detail: str = "Сервис временно недоступен", *, headers: dict[str, str] | None = None) -> None:
        super().__init__(503, detail, headers=headers)
