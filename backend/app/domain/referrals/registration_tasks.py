"""Задачи (таблица ``tasks``), связанные с регистрацией по реферальным ссылкам."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tasks.dedupe import referee_ids_with_notify_ref_reg_for_owner
from app.domain.tasks.eligibility import async_user_has_telegram_id
from app.domain.tasks.notification_task_types import NOTIFY_REF_REG
from app.infrastructure.persistence.models.referral_link import ReferralLink
from app.infrastructure.persistence.models.task import Task


async def create_notify_ref_reg_task_if_applicable(
    session: AsyncSession,
    *,
    referral_link: ReferralLink,
    referee_user_id: int,
) -> None:
    """Если ссылка принадлежит пользователю — ставим в очередь уведомление владельцу о регистрации.

    ``tasks.user_id`` — владелец ссылки (кому отправить уведомление позже),
    ``tasks.referee_id`` — зарегистрировавшийся по ссылке пользователь.
    Для кампаний (``owner_kind != 'user'``) задачу не создаём: нет целевого user_id владельца.
    """
    if referral_link.owner_kind != "user" or referral_link.owner_user_id is None:
        return
    owner_id = int(referral_link.owner_user_id)
    ref_id = int(referee_user_id)
    if owner_id == ref_id:
        return
    if not await async_user_has_telegram_id(session, owner_id):
        return
    already = await referee_ids_with_notify_ref_reg_for_owner(session, owner_id, [ref_id])
    if ref_id in already:
        return
    session.add(
        Task(
            task_type=NOTIFY_REF_REG,
            user_id=owner_id,
            referee_id=ref_id,
            bonus_days=None,
        ),
    )
