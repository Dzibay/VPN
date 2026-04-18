from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints.subscription import router as subscription_router
from app.api.router import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.middleware.request_context import RequestContextMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # startup
    yield
    # shutdown


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    application.include_router(subscription_router)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": settings.app_name}

    return application


# логирование при импорте модуля (до первого запроса под uvicorn)
setup_logging(settings.log_level)
app = create_app()
