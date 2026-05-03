"""Регистрация расширений приложения (OpenAPI и др.). Сейчас — реэкспорт из ``app.core.openapi``."""

from app.core.openapi import attach_openapi

__all__ = ["attach_openapi"]
