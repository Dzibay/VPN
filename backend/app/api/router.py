from fastapi import APIRouter, Depends

from app.core.dependencies import apply_request_subject_from_bearer_optional

from app.api.endpoints import (
    accounting,
    admin_summary,
    auth,
    client_app_public,
    health,
    site_public,
    http_audit_staff,
    me as me_endpoints,
    payments,
    prometheus_sd,
    referral_links,
    seo_pages,
    server_metrics,
    servers,
    staff_blocked_ips,
    staff_chart_events,
    staff_ledger,
    staff_support_messages,
    subscription_device_stats,
    telegram,
    users,
)

api_router = APIRouter(dependencies=[Depends(apply_request_subject_from_bearer_optional)])
api_router.include_router(health.router)
api_router.include_router(client_app_public.router)
api_router.include_router(site_public.router)
api_router.include_router(referral_links.external_router)
api_router.include_router(referral_links.public_router)
api_router.include_router(seo_pages.public_router)
api_router.include_router(referral_links.me_router)
api_router.include_router(me_endpoints.router)
api_router.include_router(auth.router)
api_router.include_router(payments.router)
api_router.include_router(telegram.router)
api_router.include_router(users.router)
api_router.include_router(staff_blocked_ips.router)
api_router.include_router(staff_chart_events.router)
api_router.include_router(staff_support_messages.router)
api_router.include_router(http_audit_staff.router)
api_router.include_router(referral_links.staff_router)
api_router.include_router(seo_pages.staff_router)
api_router.include_router(servers.router)
api_router.include_router(server_metrics.router)
api_router.include_router(subscription_device_stats.router)
api_router.include_router(staff_ledger.payments_staff_router)
api_router.include_router(staff_ledger.tasks_staff_router)
api_router.include_router(accounting.accounting_router)
api_router.include_router(admin_summary.admin_summary_router)
api_router.include_router(prometheus_sd.router)
