"""Схемы бухгалтерии (P&L): расходы, повторяющиеся шаблоны, категории, налоговые настройки и сводка."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TaxMode = Literal["npd", "usn_income", "usn_profit", "none", "custom"]
TaxBase = Literal["gross", "net", "profit"]
CashAccountKind = Literal["bank", "psp", "cash", "person", "other"]
ExpensePaymentSource = Literal["company", "person", "unpaid"]
PayableStatus = Literal["open", "partial", "paid", "cancelled"]
RefundStatus = Literal["pending", "succeeded", "failed", "cancelled"]
ProfitWithdrawalStatus = Literal["planned", "succeeded", "cancelled"]


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
    payment_source: ExpensePaymentSource = "company"
    paid_by_name: str | None = None
    cash_account_id: int | None = None
    paid_on: date | None = None
    created_at: datetime


class ExpenseCreateBody(BaseModel):
    incurred_on: date = Field(description="Дата расхода (YYYY-MM-DD)")
    amount: Decimal = Field(gt=0, description="Сумма в валюте учёта")
    category_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    payment_source: ExpensePaymentSource = Field(
        default="company",
        description="company — оплатили со счета; person — оплатил человек, создается долг; unpaid — начислено, но не оплачено",
    )
    paid_by_name: str | None = Field(default=None, max_length=200)
    cash_account_id: int | None = Field(default=None, ge=1)
    paid_on: date | None = None


class ExpensePatchBody(BaseModel):
    incurred_on: date | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    payment_source: ExpensePaymentSource | None = None
    paid_by_name: str | None = Field(default=None, max_length=200)
    cash_account_id: int | None = Field(default=None, ge=1)
    paid_on: date | None = None

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
# Управленческий cash/liability ledger
# --------------------------------------------------------------------------- #
class CashAccountItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    kind: CashAccountKind
    currency: str
    opening_balance: Decimal
    opened_on: date
    active: bool
    is_default: bool
    created_at: datetime


class CashAccountCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: CashAccountKind = "bank"
    currency: str = Field(default="RUB", max_length=8)
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)
    opened_on: date
    active: bool = True
    is_default: bool = False


class CashAccountPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    kind: CashAccountKind | None = None
    currency: str | None = Field(default=None, max_length=8)
    opening_balance: Decimal | None = Field(default=None, ge=0)
    opened_on: date | None = None
    active: bool | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> CashAccountPatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class CashAccountsListResponse(BaseModel):
    items: list[CashAccountItem]


class CashTransactionItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    account_id: int
    occurred_on: date
    amount: Decimal
    kind: Literal["adjustment", "transfer_in", "transfer_out"]
    title: str
    note: str | None = None
    created_at: datetime


class CashTransactionCreateBody(BaseModel):
    account_id: int = Field(ge=1)
    occurred_on: date
    amount: Decimal = Field(description="Плюс — поступление/корректировка вверх, минус — списание/корректировка вниз")
    kind: Literal["adjustment", "transfer_in", "transfer_out"] = "adjustment"
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class CashTransactionsListResponse(BaseModel):
    items: list[CashTransactionItem]
    total: int = Field(ge=0)
    limit: int
    offset: int


class PayableItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    counterparty_name: str
    title: str
    amount: Decimal
    paid_amount: Decimal
    status: PayableStatus
    source_type: Literal["manual", "expense", "referral", "salary", "other"]
    expense_id: int | None = None
    incurred_on: date
    due_on: date | None = None
    note: str | None = None
    created_at: datetime


class PayableCreateBody(BaseModel):
    counterparty_name: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)
    source_type: Literal["manual", "expense", "referral", "salary", "other"] = "manual"
    expense_id: int | None = Field(default=None, ge=1)
    incurred_on: date
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class PayablePatchBody(BaseModel):
    counterparty_name: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0)
    status: PayableStatus | None = None
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> PayablePatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class PayablePaymentBody(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date
    account_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=2000)


class PayablesListResponse(BaseModel):
    items: list[PayableItem]
    total: int = Field(ge=0)
    limit: int
    offset: int


class RefundItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    payment_id: int | None = None
    user_id: int | None = None
    account_id: int | None = None
    refunded_on: date
    amount: Decimal
    net_amount: Decimal
    status: RefundStatus
    reason: str | None = None
    note: str | None = None
    created_at: datetime


class RefundCreateBody(BaseModel):
    payment_id: int | None = Field(default=None, ge=1)
    user_id: int | None = Field(default=None, ge=1)
    account_id: int | None = Field(default=None, ge=1)
    refunded_on: date
    amount: Decimal = Field(gt=0)
    net_amount: Decimal | None = Field(default=None, gt=0)
    status: RefundStatus = "succeeded"
    reason: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)


class RefundPatchBody(BaseModel):
    status: RefundStatus | None = None
    reason: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> RefundPatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class RefundsListResponse(BaseModel):
    items: list[RefundItem]
    total: int = Field(ge=0)
    limit: int
    offset: int


class ProfitWithdrawalItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    account_id: int | None = None
    withdrawn_on: date
    amount: Decimal
    recipient_name: str
    status: ProfitWithdrawalStatus
    note: str | None = None
    created_at: datetime


class ProfitWithdrawalCreateBody(BaseModel):
    account_id: int | None = Field(default=None, ge=1)
    withdrawn_on: date
    amount: Decimal = Field(gt=0)
    recipient_name: str = Field(min_length=1, max_length=200)
    status: ProfitWithdrawalStatus = "succeeded"
    note: str | None = Field(default=None, max_length=2000)


class ProfitWithdrawalPatchBody(BaseModel):
    status: ProfitWithdrawalStatus | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> ProfitWithdrawalPatchBody:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для обновления")
        return self


class ProfitWithdrawalsListResponse(BaseModel):
    items: list[ProfitWithdrawalItem]
    total: int = Field(ge=0)
    limit: int
    offset: int


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
    #: Помесячное признание выручки: первый месяц — в день оплаты (выдача ключа), далее по годовщинам.
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
    #: Неисполненные обязательства перед клиентами (предоплата за неисполненные месяцы подписки).
    deferred_net: str
    deferred_gross: str
    active_obligations: int = Field(
        ge=0,
        description=(
            "Пользователи с subscription_until >= as_of (как снимок на графике), "
            "у которых была хотя бы одна оплата подписки (months > 0)"
        ),
    )


class FinanceUnlockSchedule(BaseModel):
    """График разблокировки: суммы по датам начала каждого месяца подписки (первый — день оплаты)."""

    days: list[str] = Field(default_factory=list, description="Даты разблокировки YYYY-MM-DD")
    amounts_net: list[str] = Field(default_factory=list, description="Сумма за день, net")
    months: list[str] = Field(default_factory=list, description="Месяцы YYYY-MM")
    amounts_net_monthly: list[str] = Field(default_factory=list, description="Сумма за месяц, net")


class FinanceCategoryTotal(BaseModel):
    slug: str
    title: str
    color: str
    total: str


class FinanceTotals(BaseModel):
    revenue_gross: str
    revenue_net: str
    psp_commission: str
    refunds_total: str = "0.00"
    revenue_net_after_refunds: str = "0.00"
    expenses_total: str
    tax: str
    profit_net: str
    profit_withdrawn: str = "0.00"
    margin_percent: str = Field(description="Маржа = чистая прибыль / валовая выручка, в процентах")
    payment_count: int = Field(ge=0)


class FinanceCashPosition(BaseModel):
    """Управленческий снимок: cash, заморозка, долги и доступность вывода."""

    as_of: date
    cash_balance: str
    cash_accounts_total: str
    cash_adjustments: str
    received_net: str
    earned_net: str
    deferred_net: str
    payables_open: str
    unpaid_expenses: str
    refunds_succeeded: str
    profit_withdrawn: str
    tax_reserved: str
    withdrawable_profit: str
    reserve_total: str


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
    cash_position: FinanceCashPosition
    unlock: FinanceUnlockSchedule = Field(default_factory=FinanceUnlockSchedule)
