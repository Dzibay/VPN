"""HTTP Bearer (JWT) для OpenAPI: одна схема `BearerAuth` и одна зависимость для маршрутов."""

from __future__ import annotations

from fastapi.security import HTTPBearer

# auto_error=False: отдаём 401 с единообразным телом, а не 403 стандартного HTTPBearer.
# scheme_name: совпадает с дополнением в attach_openapi (описание в components).
bearer_jwt = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    bearerFormat="JWT",
)
