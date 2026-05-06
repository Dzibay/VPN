"""Расширение схемы OpenAPI: описание для схемы ``BearerAuth`` (см. ``app.api.security_bearer``)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def attach_openapi(application: FastAPI) -> None:
    def openapi_fn() -> dict:
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
            tags=application.openapi_tags,
        )
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        bearer = schemes.get("BearerAuth")
        if isinstance(bearer, dict):
            bearer["description"] = (
                "Выпуск JWT: POST /api/auth/login, POST /api/auth/register или POST /api/auth/telegram "
                "(для последнего требуется заголовок с секретом бота). Профиль: GET /api/me. "
                "В форме Authorize укажите только значение токена access_token; префикс «Bearer » подставляется автоматически."
            )
        application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = openapi_fn  # type: ignore[method-assign]
