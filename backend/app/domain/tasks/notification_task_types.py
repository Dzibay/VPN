"""Единый реестр типов задач оповещения для Telegram-бота и админки."""

from __future__ import annotations

from typing import Literal

NOTIFY_REF_REG = "notify_ref_reg"
NOTIFY_REF_PAY = "notify_ref_pay"
NOTIFY_PAYMENT = "notify_payment"

NOTIFY_SUB_EXPIRE_3D = "notify_sub_expire_3d"
NOTIFY_SUB_EXPIRE_1D = "notify_sub_expire_1d"
NOTIFY_SUB_EXPIRE_0D = "notify_sub_expire_0d"
NOTIFY_SUB_EXPIRE = "notify_sub_expire"
NOTIFY_SUB_EXPIRED_7D = "notify_sub_expired_7d"

NOTIFY_REG_1H_HAS_TRAFFIC = "notify_reg_1h_has_traffic"
NOTIFY_REG_1H_NO_TRAFFIC = "notify_reg_1h_no_traffic"

NOTIFY_TRAFFIC_LOW = "notify_traffic_low"
NOTIFY_TRAFFIC_OVER = "notify_traffic_over"

NOTIFICATION_TASK_TYPES: tuple[str, ...] = (
    NOTIFY_REF_REG,
    NOTIFY_REF_PAY,
    NOTIFY_PAYMENT,
    NOTIFY_SUB_EXPIRE_3D,
    NOTIFY_SUB_EXPIRE_1D,
    NOTIFY_SUB_EXPIRE_0D,
    NOTIFY_SUB_EXPIRE,
    NOTIFY_SUB_EXPIRED_7D,
    NOTIFY_REG_1H_HAS_TRAFFIC,
    NOTIFY_REG_1H_NO_TRAFFIC,
    NOTIFY_TRAFFIC_LOW,
    NOTIFY_TRAFFIC_OVER,
)

NotificationTaskType = Literal[
    "notify_ref_reg",
    "notify_ref_pay",
    "notify_payment",
    "notify_sub_expire_3d",
    "notify_sub_expire_1d",
    "notify_sub_expire_0d",
    "notify_sub_expire",
    "notify_sub_expired_7d",
    "notify_reg_1h_has_traffic",
    "notify_reg_1h_no_traffic",
    "notify_traffic_low",
    "notify_traffic_over",
]

# Типы, которые staff может создать вручную в админке (тот же набор, что у бота).
StaffCreatableTaskType = NotificationTaskType


def _assert_notification_types_aligned() -> None:
    from typing import get_args

    literal_set = set(get_args(NotificationTaskType))
    tuple_set = set(NOTIFICATION_TASK_TYPES)
    if literal_set != tuple_set:
        raise RuntimeError(
            "NotificationTaskType и NOTIFICATION_TASK_TYPES разошлись: "
            f"only_in_literal={literal_set - tuple_set!r}, only_in_tuple={tuple_set - literal_set!r}",
        )


_assert_notification_types_aligned()

SUBSCRIPTION_EXPIRY_NOTIFY_TYPES: tuple[str, ...] = (
    NOTIFY_SUB_EXPIRE_3D,
    NOTIFY_SUB_EXPIRE_1D,
    NOTIFY_SUB_EXPIRE_0D,
)

POST_REGISTRATION_NOTIFY_TYPES: tuple[str, ...] = (
    NOTIFY_REG_1H_HAS_TRAFFIC,
    NOTIFY_REG_1H_NO_TRAFFIC,
)
