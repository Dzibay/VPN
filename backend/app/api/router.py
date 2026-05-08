from fastapi import APIRouter, Depends

from app.core.dependencies import apply_request_subject_from_bearer_optional

from app.api.endpoints import (
    auth,
    client_app_public,
    me as me_endpoints,
    health,
    http_audit_staff,
    payments,
    prometheus_sd,
    referral_links,
    server_metrics,
    servers,
    staff_chart_events,
    status,
    subscription_device_stats,
    telegram,
    users,
)

api_router = APIRouter(dependencies=[Depends(apply_request_subject_from_bearer_optional)])
api_router.include_router(health.router)
api_router.include_router(client_app_public.router)
api_router.include_router(referral_links.public_router)
api_router.include_router(referral_links.me_router)
api_router.include_router(me_endpoints.router)
api_router.include_router(auth.router)
api_router.include_router(payments.router)
api_router.include_router(telegram.router)
api_router.include_router(status.router)
api_router.include_router(users.router)
api_router.include_router(staff_chart_events.router)
api_router.include_router(http_audit_staff.router)
api_router.include_router(referral_links.staff_router)
api_router.include_router(servers.router)
api_router.include_router(server_metrics.router)
api_router.include_router(subscription_device_stats.router)
api_router.include_router(prometheus_sd.router)
