"""Списочные ответы админки: платежи и задачи (JWT admin или manager)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


StaffCreatableTaskType = Literal[
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
]


class StaffPaymentItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int | None = None
    amount: Decimal
    months: int
    provider: str
    #: ``subscription`` (Tribute) | ``one_time`` (Tribute цифровой товар).
    payment_kind: str
    tribute_webhook: dict[str, Any] | None = None
    created_at: datetime


class StaffPaymentsListResponse(BaseModel):
    items: list[StaffPaymentItem] = Field(description="Строки payments, новые первыми")
    total: int = Field(ge=0, description="Число строк в таблице payments")
    limit: int
    offset: int


class StaffPaymentsBulkDeleteBody(BaseModel):
    ids: list[int] = Field(
        min_length=1,
        description="ID платежей для удаления",
    )


class StaffPaymentsBulkDeleteResponse(BaseModel):
    deleted_count: int


class StaffCreateTributePaymentBody(BaseModel):
    """Ручное начисление оплаты — тот же commit, что после webhook Tribute."""

    user_id: int = Field(ge=1, description="users.id")
    months: int = Field(ge=1, le=120, description="Срок подписки в месяцах (× 31 день)")
    amount_rub: Decimal = Field(gt=0, description="Сумма в рублях")
    payment_kind: Literal["subscription", "one_time"] = Field(
        default="one_time",
        description="subscription — рекуррент; one_time — разовая покупка",
    )
    created_at: datetime | None = Field(
        default=None,
        description="Дата и время платежа (UTC); по умолчанию — сейчас. Также в notify_payment.",
    )


class StaffCreateTributePaymentResponse(BaseModel):
    payment: StaffPaymentItem | None = Field(
        default=None,
        description="Новая строка payments; null при duplicate",
    )
    ok: bool = True
    event: str | None = None
    duplicate: bool = False


class StaffPaymentsFinanceBuckets(BaseModel):
    """Суммы по месяцам (ось ``months``) для subscription и one_time."""

    subscription: list[str] = Field(
        default_factory=list,
        description="Строки decimal, по порядку ``months``",
    )
    one_time: list[str] = Field(default_factory=list)


class StaffPaymentsFinanceSummaryResponse(BaseModel):
    """Ответ ``rpc_staff_payments_finance_summary()`` — cash и spread по месяцам UTC."""

    months: list[str] = Field(
        description="Объединение месяцев YYYY-MM, где есть данные в cash или spread",
    )
    cash: StaffPaymentsFinanceBuckets = Field(
        description="Вся сумма платежа в месяце created_at (UTC)",
    )
    spread: StaffPaymentsFinanceBuckets = Field(
        description="amount/months на каждый из months календарных месяцев вперёд от created_at (UTC)",
    )
    grand_total: str = Field(description="Сумма amount по всем платежам (без деления)")
    payment_count: int = Field(ge=0, description="Число строк payments")


class StaffTaskItem(BaseModel):
    id: int
    type: str = Field(description="Значение колонки tasks.type")
    user_id: int
    referee_id: int | None = None
    bonus_days: int | None = None
    paid_months: int | None = None
    status: str
    created_at: datetime
    done_at: datetime | None = None


class StaffCreateTaskBody(BaseModel):
    """Создание строки ``tasks`` (типы и поля — как в схеме БД / планировщике)."""

    user_id: int = Field(ge=1, description="Основной пользователь задачи: users.id")
    task_type: StaffCreatableTaskType = Field(description="Значение колонки tasks.type")
    referee_id: int | None = Field(
        default=None,
        ge=1,
        description="Опционально: users.id реферала (notify_ref_*, часть сценариев).",
    )
    bonus_days: int | None = Field(
        default=None,
        ge=0,
        description="Опционально: бонусные дни (notify_ref_pay, часть notify_payment).",
    )
    paid_months: int | None = Field(
        default=None,
        ge=1,
        description="Опционально: для notify_payment — число оплаченных месяцев.",
    )


StaffTaskStatus = Literal["pending", "completed", "failed"]


class StaffPatchTaskBody(BaseModel):
    """Частичное обновление ``tasks`` (в запросе — только меняемые поля)."""

    task_type: StaffCreatableTaskType | None = None
    user_id: int | None = Field(default=None, ge=1)
    referee_id: int | None = Field(
        default=None,
        ge=1,
        description="null в JSON — сбросить referee_id.",
    )
    bonus_days: int | None = Field(default=None, ge=0)
    paid_months: int | None = Field(default=None, ge=1)
    status: StaffTaskStatus | None = None
    done_at: datetime | None = Field(
        default=None,
        description="null — очистить done_at; иначе ISO8601 с часовым поясом.",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> StaffPatchTaskBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class StaffTasksListResponse(BaseModel):
    items: list[StaffTaskItem] = Field(description="Строки tasks, новые первыми")
    total: int = Field(ge=0, description="Число строк в таблице tasks")
    limit: int
    offset: int
