/** Непустое текстовое поле подключения подписки (os, user_agent) для отображения в UI. */
export function formatSubscriptionConnectionField(raw) {
  if (raw == null || String(raw).trim() === '') return '—'
  return String(raw).trim()
}
