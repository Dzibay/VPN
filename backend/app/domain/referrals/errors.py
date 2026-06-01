"""Типизированные ошибки домена реферальных ссылок.

Раньше repository/tokens бросали безымянный ``ValueError`` с русским текстом, а сервис и
эндпоинты восстанавливали HTTP-код сравнением строк (``"уже занят" in detail`` и т.п.) — это
хрупко: переформулировал сообщение и маппинг молча сломался. Теперь домен бросает подклассы
:class:`app.core.exceptions.AppError`, и:

* HTTP-код выставляется самим типом (глобальный обработчик уже умеет маппить ``AppError``);
* retry-логика в :func:`get_or_create_user_owned_referral_link` ловит ошибку по типу, а не по тексту.
"""

from __future__ import annotations

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnprocessableEntityError,
)


class ReferralUserNotFoundError(NotFoundError):
    """owner_user_id указывает на несуществующего пользователя (HTTP 404)."""

    def __init__(self, detail: str = "Пользователь не найден") -> None:
        super().__init__(detail)


class ReferralLinkNotFoundError(NotFoundError):
    """Запись referral_links не найдена по id (HTTP 404)."""

    def __init__(self, detail: str = "Запись не найдена") -> None:
        super().__init__(detail)


class ReferralTokenTakenError(ConflictError):
    """Запрошенный токен уже занят другой записью (HTTP 409)."""

    def __init__(self, detail: str = "Токен уже занят") -> None:
        super().__init__(detail)


class PersonalReferralLinkExistsError(ConflictError):
    """У пользователя уже есть персональная ссылка — uq_referral_links_one_user_owner (HTTP 409)."""

    def __init__(
        self,
        detail: str = "У этого пользователя уже есть персональная реферальная ссылка (не более одной)",
    ) -> None:
        super().__init__(detail)


class ReferralOwnerArgsError(UnprocessableEntityError):
    """Несогласованные owner_kind / owner_user_id (HTTP 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ReferralTokenShapeError(UnprocessableEntityError):
    """Токен не соответствует формату Telegram ``start`` (HTTP 422)."""

    def __init__(
        self,
        detail: str = "token: допустимы латиница, цифры и подчёркивание, длина 4–64 (формат Telegram start)",
    ) -> None:
        super().__init__(detail)
