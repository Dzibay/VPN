"""Централизованная регистрация обработчиков исключений FastAPI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.core.exceptions import AppError


def register_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": jsonable_encoder(exc.detail)},
            headers=exc.headers,
        )
