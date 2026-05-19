"""Определение формата подписки по User-Agent."""

from __future__ import annotations

from starlette.requests import Request


def subscription_user_agent(request: Request | None) -> str:
    if request is None:
        return ""
    return (request.headers.get("user-agent") or "").lower()


def subscription_user_agent_is_happ(request: Request | None) -> bool:
    return "happ" in subscription_user_agent(request)


def subscription_user_agent_is_clash_yaml(request: Request | None) -> bool:
    ua = subscription_user_agent(request)
    return "clash" in ua or "hiddify" in ua
