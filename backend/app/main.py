import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints.subscription import router as subscription_router
from app.api.router import api_router
from app.config import settings
from app.core.dependencies import require_swagger_staff_cookie
from app.core.error_handlers import register_exception_handlers
from app.core.staff_swagger_html import staff_swagger_ui_html
from app.core.moscow_api_time import install_moscow_json_encoder
from app.core.logging_config import setup_logging
from app.core.middleware.request_context import RequestContextMiddleware
from app.core.openapi import attach_openapi
from app.core.startup_checks import validate_production_secrets

log = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.infrastructure.database.schema import ensure_schema

    # Сами периодические корутины (Xray-сбор, Prometheus-load, ежедневный sync, TCP-доступность → Redis)
    # переехали в отдельный процесс `python -m app.scheduler.run` — см. backend/app/scheduler/run.py.
    # Здесь остался только ensure_schema (идемпотентно, быстро): запускается синхронно при
    # старте процесса и не зависит от порядка запуска контейнеров.
    ensure_schema()
    yield


def create_app() -> FastAPI:
    install_moscow_json_encoder()
    application = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        openapi_tags=[
            {
                "name": "public",
            },
            {
                "name": "telegram",
            },
            {
                "name": "user",
            },
            {
                "name": "admin",
            }
        ],
    )
    register_exception_handlers(application)
    attach_openapi(application)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins(),
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    application.include_router(subscription_router)

    @application.get(
        "/swagger",
        include_in_schema=False,
        dependencies=[Depends(require_swagger_staff_cookie)],
    )
    async def staff_swagger():
        return staff_swagger_ui_html(
            application=application,
            title=f"{settings.app_name} · Swagger UI",
            swagger_ui_parameters={"persistAuthorization": True},
        )

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "swagger": "/swagger",
        }

    return application


# Логирование и обязательные проверки конфига выполняются на этапе импорта модуля
# (uvicorn делает это до первого запроса; неправильный конфиг = падение процесса).
setup_logging(settings.log_level)
validate_production_secrets(settings)
app = create_app()
