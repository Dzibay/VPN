"""Схемы бухгалтерии (P&L): расходы, повторяющиеся шаблоны, категории, налоговые настройки и сводка."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TaxMode = Literal["npd", "usn_income", "usn_profit", "none", "custom"]
TaxBase = Literal["gross", "net", "profit"]


# --------------------------------------------------------------------------- #
# Настройки (налог, валюта)
# --------------------------------------------------------------------------- #
class FinanceSettings(BaseModel):
    """Налоговые настройки. По умолчанию — НПД 4% с валовой выручки."""

    tax_mode: TaxMode = Field(default="npd", description="Режим (для пресета и подписи)")
    tax_rate: Decimal = Field(default=Decimal("0.04"), ge=0, le=1, description="Ставка долей единицы (0.04 = 4%)")
    tax_base: TaxBase = Field(
        default="gross",
        description="С чего считать: gross — валовая выручка, net — после комиссии, profit — выручка минус расходы",
    )
    currency: str = Field(default="RUB", max_length=8)


class FinanceSettingsPatch(BaseModel):
    tax_mode: TaxMode | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    tax_base: TaxBase | None = None
    currency: str | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def at_least_one_field(self) -> FinanceSettingsPatch:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


# --------------------------------------------------------------------------- #
# Категории расходов
# --------------------------------------------------------------------------- #
class ExpenseCategoryItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    slug: str
    title: str
    color: str
    sort_order: int
    archived: bool


class ExpenseCategoryCreateBody(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#94a3b8", max_length=32)
    sort_order: int = Field(default=0, ge=0, le=100000)


class ExpenseCategoryPatchBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    archived: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> ExpenseCategoryPatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class ExpenseCategoriesListResponse(BaseModel):
    items: list[ExpenseCategoryItem]


# --------------------------------------------------------------------------- #
# Разовые расходы
# --------------------------------------------------------------------------- #
class ExpenseItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    incurred_on: date
    amount: Decimal
    category_id: int | None = None
    title: str
    note: str | None = None
    created_at: datetime


class ExpenseCreateBody(BaseModel):
    incurred_on: date = Field(description="Дата расхода (YYYY-MM-DD)")
    amount: Decimal = Field(gt=0, description="Сумма в валюте учёта")
    category_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class ExpensePatchBody(BaseModel):
    incurred_on: date | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> ExpensePatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class ExpensesListResponse(BaseModel):
    items: list[ExpenseItem]
    total: int = Field(ge=0)
    limit: int
    offset: int


class ExpensesBulkDeleteBody(BaseModel):
    ids: list[int] = Field(min_length=1, description="ID расходов для удаления")


class ExpensesBulkDeleteResponse(BaseModel):
    deleted_count: int


# --------------------------------------------------------------------------- #
# Повторяющиеся расходы (шаблоны)
# --------------------------------------------------------------------------- #
class RecurringExpenseItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    amount: Decimal
    category_id: int | None = None
    note: str | None = None
    day_of_month: int
    start_month: date
    end_month: date | None = None
    active: bool


class RecurringExpenseCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)
    category_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=2000)
    day_of_month: int = Field(default=1, ge=1, le=28)
    start_month: date = Field(description="Первый месяц действия (любая дата месяца)")
    end_month: date | None = Field(default=None, description="Последний месяц включительно; null — бессрочно")
    active: bool = True

    @model_validator(mode="after")
    def end_after_start(self) -> RecurringExpenseCreateBody:
        if self.end_month is not None and self.end_month < self.start_month:
            raise ValueError("end_month не может быть раньше start_month")
        return self


class RecurringExpensePatchBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=2000)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    start_month: date | None = None
    end_month: date | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> RecurringExpensePatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class RecurringExpensesListResponse(BaseModel):
    items: list[RecurringExpenseItem]


# --------------------------------------------------------------------------- #
# Сводка (P&L)
# --------------------------------------------------------------------------- #
class FinanceSeries(BaseModel):
    """Помесячные ряды (строки decimal) по оси ``months``."""

    revenue_gross: list[str] = Field(default_factory=list)
    revenue_net: list[str] = Field(default_factory=list)
    psp_commission: list[str] = Field(default_factory=list)
    revenue_gross_subscription: list[str] = Field(default_factory=list)
    revenue_gross_one_time: list[str] = Field(default_factory=list)
    expenses_total: list[str] = Field(default_factory=list)
    tax: list[str] = Field(default_factory=list)
    profit_net: list[str] = Field(default_factory=list)
    #: День-точное признание выручки (заработано за месяц по факту прошедших дней подписки).
    earned_net: list[str] = Field(default_factory=list)
    earned_gross: list[str] = Field(default_factory=list)
    #: Остаток неисполненных обязательств («замороженные деньги») на конец месяца.
    deferred_net_end: list[str] = Field(default_factory=list)
    deferred_gross_end: list[str] = Field(default_factory=list)


class FinanceDeferredSnapshot(BaseModel):
    """Денежная позиция на момент ``as_of``: поступило / заработано (свободно) / заморожено."""

    as_of: date
    received_net: str
    received_gross: str
    #: Заработано = свободно от обязательств (поступило − заморожено).
    earned_net: str
    earned_gross: str
    #: Неисполненные обязательства перед клиентами (предоплата за непоставленные дни).
    deferred_net: str
    deferred_gross: str
    active_obligations: int = Field(
        ge=0,
        description="Число пользователей с действующей подпиской, оплаченной хотя бы раз",
    )


class FinanceCategoryTotal(BaseModel):
    slug: str
    title: str
    color: str
    total: str


class FinanceTotals(BaseModel):
    revenue_gross: str
    revenue_net: str
    psp_commission: str
    expenses_total: str
    tax: str
    profit_net: str
    margin_percent: str = Field(description="Маржа = чистая прибыль / валовая выручка, в процентах")
    payment_count: int = Field(ge=0)


class FinanceTaxInfo(BaseModel):
    mode: TaxMode
    rate: str
    base: TaxBase


class FinanceAccountingSummaryResponse(BaseModel):
    range_from: date
    range_to: date
    currency: str
    months: list[str]
    series: FinanceSeries
    expenses_by_category: dict[str, list[str]] = Field(default_factory=dict)
    category_totals: list[FinanceCategoryTotal] = Field(default_factory=list)
    totals: FinanceTotals
    tax: FinanceTaxInfo
    deferred: FinanceDeferredSnapshot
