"""Публичная информация о VPN-клиентах для страницы /public/client-apps."""

from app.domain.models.client_app_public import ClientAppPublicResponse
from app.domain.subscription.open_apps import get_subscription_open_app


def build_client_app_public(client_code: str) -> ClientAppPublicResponse | None:
    app = get_subscription_open_app(client_code)
    if app is None:
        return None
    sl = app.store_links
    links = sl.to_public_json_dict() if sl.any() else {}
    return ClientAppPublicResponse(
        client_code=client_code,
        display_name=app.display_name,
        store_links=links,
    )
