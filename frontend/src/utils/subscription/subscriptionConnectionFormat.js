/** x-device-os для списка подключений — без обрезки. */
export function formatSubscriptionConnectionOs(raw) {
  if (raw == null || String(raw).trim() === '') return '—'
  return String(raw).trim()
}

/** User-Agent: часть до первого «/» (напр. Happ из Happ/2.9.1/…). */
export function formatSubscriptionConnectionUserAgent(raw) {
  if (raw == null || String(raw).trim() === '') return '—'
  const s = String(raw).trim()
  const i = s.indexOf('/')
  const head = i === -1 ? s : s.slice(0, i).trim()
  return head || '—'
}
