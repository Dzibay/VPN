import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints.subscription import router as subscription_router
from app.api.router import api_router
from app.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.middleware.request_context import RequestContextMiddleware
from app.core.openapi import attach_openapi
from app.core.startup_checks import validate_production_secrets

log = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.infrastructure.database.schema import ensure_schema

    ensure_schema()
    bg_tasks: list[asyncio.Task[None]] = []
    if settings.xray_traffic_collect_schedule_enabled:
        from app.infrastructure.xray.xray_traffic_scheduler import periodic_xray_traffic_collect_loop

        bg_tasks.append(asyncio.create_task(periodic_xray_traffic_collect_loop()))
    if settings.subscription_daily_xray_clients_sync_enabled:
        from app.domain.subscription.scheduler import subscription_daily_xray_sync_loop

        bg_tasks.append(asyncio.create_task(subscription_daily_xray_sync_loop()))
    if settings.server_load_prometheus_sync_schedule_enabled and (
        settings.prometheus_base_url or ""
    ).strip():
        from app.infrastructure.prometheus.server_load_scheduler import periodic_server_load_from_prometheus_loop

        bg_tasks.append(asyncio.create_task(periodic_server_load_from_prometheus_loop()))
    try:
        yield
    finally:
        for sched_task in bg_tasks:
            sched_task.cancel()
            try:
                await sched_task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/swagger",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={"persistAuthorization": True},
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
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    application.include_router(subscription_router)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "swagger": "/swagger",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        }

    return application


# Логирование и обязательные проверки конфига выполняются на этапе импорта модуля
# (uvicorn делает это до первого запроса; неправильный конфиг = падение процесса).
setup_logging(settings.log_level)
validate_production_secrets(settings)
app = create_app()
