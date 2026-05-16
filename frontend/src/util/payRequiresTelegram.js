/**
 * Нужна ли привязка Telegram перед оплатой (страница /cabinet/pay).
 * Webhook Tribute идентифицирует пользователя по telegram_id — это имеет смысл
 * только когда на API настроен бот (TELEGRAM_BOT_USERNAME → telegram_bot_page_url в GET /api/me).
 */
export function payRequiresTelegramBinding(me) {
  if (!me || me.telegram_id != null) return false
  const botUrl = me.telegram_bot_page_url
  return typeof botUrl === 'string' && botUrl.trim() !== ''
}
