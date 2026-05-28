/** Логотип клиента: `frontend/public/client-logos/{client_code}.png`. */

export function openClientLogoUrl(clientCode) {
  const code = String(clientCode ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '')
  if (!code) return ''
  const base = import.meta.env.BASE_URL || '/'
  const prefix = base.endsWith('/') ? base : `${base}/`
  return `${prefix}client-logos/${encodeURIComponent(code)}.png`
}

/** Скрыть контейнер логотипа, если PNG для client_code нет. */
export function hideClientLogoOnError(ev) {
  const el = ev.target
  if (!(el instanceof HTMLImageElement)) return
  const wrap = el.closest('.app-dl-logo, .client-app-tile__logo')
  if (wrap instanceof HTMLElement) wrap.style.display = 'none'
  else el.style.display = 'none'
}
