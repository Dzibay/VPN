import { clearSession, getAccessToken } from '../auth/session.js'

function tokenForApiPath(path) {
  if (!path.startsWith('/api/')) return null
  if (path === '/api/auth/login' || path === '/api/auth/register') {
    return null
  }
  return getAccessToken()
}

function formatErrorDetail(data) {
  if (data == null || typeof data !== 'object') return null
  const d = data.detail
  if (d == null) return null
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((x) =>
        typeof x === 'object' && x != null && typeof x.msg === 'string'
          ? x.msg
          : JSON.stringify(x),
      )
      .join('; ')
  }
  return JSON.stringify(d)
}

/**
 * Базовый URL API. В dev оставьте пустым — запросы идут на тот же хост (прокси Vite).
 * Для продакшена на другом домене: VITE_API_BASE_URL=https://api.example.com
 */
export function apiUrl(path) {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  const p = path.startsWith('/') ? path : `/${path}`
  return base ? `${base}${p}` : p
}

export async function fetchJson(path, options = {}) {
  const headers = {
    Accept: 'application/json',
    ...options.headers,
  }
  const token = tokenForApiPath(path)
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (
    options.body != null &&
    typeof options.body === 'string' &&
    !headers['Content-Type']
  ) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(apiUrl(path), {
    ...options,
    headers,
    cache: options.cache ?? 'no-store',
  })
  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const authSent = headers.Authorization
    if (res.status === 401 && authSent?.startsWith('Bearer ')) {
      const sent = authSent.slice(7).trim()
      const t = getAccessToken()
      if (sent && t && sent === t) clearSession()
    }
    const detailMsg = formatErrorDetail(data)
    const err = new Error(
      detailMsg || res.statusText || `HTTP ${res.status}`,
    )
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

/**
 * URL подписки для VPN-клиента: GET возвращает text/plain — одна строка Base64.
 * JSON с узлами и vless://: …/sub/{token}/json
 * В проде задайте VITE_SUBSCRIPTION_BASE_URL=https://api.yourvpn.com
 */
export function subscriptionPublicUrl(token) {
  const base =
    import.meta.env.VITE_SUBSCRIPTION_BASE_URL?.replace(/\/$/, '') ?? ''
  if (base) {
    return `${base}/sub/${token}`
  }
  if (typeof window !== 'undefined') {
    return `${window.location.origin}/sub/${token}`
  }
  return `/sub/${token}`
}

/**
 * Страница открытия клиента: deeplink + при необходимости установка (тот же базовый хост, что и подписка).
 */
export function subscriptionOpenClientUrl(token, clientSlug) {
  const base =
    import.meta.env.VITE_SUBSCRIPTION_BASE_URL?.replace(/\/$/, '') ?? ''
  if (base) {
    return `${base}/sub/${token}/open/${clientSlug}`
  }
  if (typeof window !== 'undefined') {
    return `${window.location.origin}/sub/${token}/open/${clientSlug}`
  }
  return `/sub/${token}/open/${clientSlug}`
}
