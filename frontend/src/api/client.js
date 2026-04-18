import { clearAdminToken, getAdminToken } from '../auth/session.js'

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
  const token = getAdminToken()
  if (
    token &&
    path.startsWith('/api/') &&
    path !== '/api/auth/login' &&
    path !== '/api/auth/status'
  ) {
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
    if (
      res.status === 401 &&
      token &&
      path.startsWith('/api/') &&
      path !== '/api/auth/login'
    ) {
      clearAdminToken()
    }
    const err = new Error(
      typeof data === 'object' && data?.detail != null
        ? JSON.stringify(data.detail)
        : res.statusText || `HTTP ${res.status}`,
    )
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

/**
 * Полный URL подписки для клиента (ссылка вида …/sub/{token}).
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
