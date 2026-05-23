/**
 * Раньше оплата на сайте шла через Tribute по telegram_id.
 * С ЮKassa зачисление идёт по user_id из JWT — привязка Telegram для /cabinet/pay не обязательна.
 */
export function payRequiresTelegramBinding(_me) {
  return false
}
