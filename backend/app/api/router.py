from fastapi import APIRouter

from app.api.endpoints import (
    auth,
    client_app_public,
    me as me_endpoints,
    health,
    prometheus_sd,
    referral_links,
    server_metrics,
    servers,
    status,
    telegram,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(client_app_public.router)
api_router.include_router(referral_links.public_router)
api_router.include_router(referral_links.me_router)
api_router.include_router(me_endpoints.router)
api_router.include_router(auth.router)
api_router.include_router(telegram.router)
api_router.include_router(status.router)
api_router.include_router(users.router)
api_router.include_router(referral_links.staff_router)
api_router.include_router(servers.router)
api_router.include_router(server_metrics.router)
api_router.include_router(prometheus_sd.router)
