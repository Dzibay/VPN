"""Расширение схемы OpenAPI (Swagger UI): общие securitySchemes."""

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
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "BearerAuth"
        ] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Регистрация: POST /api/auth/register. Вход: POST /api/auth/login. "
                "Профиль: GET /api/auth/me с Bearer. В Authorize — только значение токена."
            ),
        }
        application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = openapi_fn  # type: ignore[method-assign]
