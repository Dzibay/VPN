from fastapi import APIRouter

from app.api.endpoints import auth, health, prometheus_sd, server_metrics, servers, status, telegram, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(telegram.router)
api_router.include_router(status.router)
api_router.include_router(users.router)
api_router.include_router(servers.router)
api_router.include_router(server_metrics.router)
api_router.include_router(prometheus_sd.router)
