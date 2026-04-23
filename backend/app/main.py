from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints.subscription import router as subscription_router
from app.api.router import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.openapi import attach_openapi
from app.middleware.request_context import RequestContextMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.database.schema import ensure_schema

    ensure_schema()
    yield


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
    )
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


# логирование при импорте модуля (до первого запроса под uvicorn)
setup_logging(settings.log_level)
app = create_app()
