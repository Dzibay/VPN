import { clearSession, getAccessToken } from '../auth/session.js'

function tokenForApiPath(path) {
  if (!path.startsWith('/api/')) return null
  if (
    path === '/api/auth/login' ||
    path === '/api/auth/register' ||
    path.startsWith('/api/auth/telegram/site-link/preview') ||
    path === '/api/auth/telegram/site-link/complete'
  ) {
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

/**
 * Публичный URL сайта (SPA). Для ссылок в ЛК, которые должны открывать Vue, а не только API.
 * Приоритет: VITE_PUBLIC_SITE_URL → window.location.origin.
 */
export function sitePublicUrl() {
  const base = import.meta.env.VITE_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? ''
  if (base) return base
  if (typeof window !== 'undefined') return window.location.origin
  return ''
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
 * URL подписки для VPN-клиента: GET возвращает text/plain Base64 или text/yaml,
 * если User-Agent содержит подстроку «clash» (без учёта регистра).
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

/** @deprecated То же, что {@link subscriptionPublicUrl}: YAML отдаётся по User-Agent с «clash». */
export function subscriptionClashPublicUrl(token) {
  return subscriptionPublicUrl(token)
}

/** @typedef {'windows'|'android'|'ios'|'macos'|'linux'} StorePlatform */

const STORE_PLATFORM_SET = new Set([
  'windows',
  'android',
  'ios',
  'macos',
  'linux',
])

/**
 * Платформа для ссылок «Скачать» (как на бэке pick() для store links).
 * @returns {StorePlatform}
 */
export function detectStorePlatform() {
  if (typeof navigator === 'undefined') return 'windows'
  const u = navigator.userAgent || ''
  if (/android/i.test(u)) return 'android'
  if (/iPhone|iPad|iPod/i.test(u)) return 'ios'
  if (/Win64|Windows NT|Win32|Windows Phone/i.test(u)) return 'windows'
  if (/Macintosh|Mac OS X/i.test(u) && !/iPhone|iPad|iPod/i.test(u)) return 'macos'
  if (/Linux|X11/i.test(u)) return 'linux'
  return 'windows'
}

/**
 * Путь страницы «открыть в клиенте»: /sub/{token}/open/{client} (данные: …/data).
 */
export function subscriptionOpenPath(token, clientCode, platform) {
  const t = encodeURIComponent(token)
  const s = encodeURIComponent(clientCode)
  let path = `/sub/${t}/open/${s}`
  if (platform && STORE_PLATFORM_SET.has(platform)) {
    path += `?platform=${encodeURIComponent(platform)}`
  }
  return path
}

/**
 * Путь страницы скачивания клиента /apps/{clientCode}
 * @param {string} clientCode
 * @param {Record<string, string | undefined | null>} [query]
 */
export function clientAppDownloadPath(clientCode, query) {
  const s = encodeURIComponent(clientCode)
  let path = `/apps/${s}`
  if (query && typeof query === 'object') {
    const pairs = []
    for (const [k, v] of Object.entries(query)) {
      if (v != null && v !== '') {
        pairs.push(
          `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`,
        )
      }
    }
    if (pairs.length) path += `?${pairs.join('&')}`
  }
  return path
}

/**
 * Ссылка для пользователя. Если задан VITE_PUBLIC_SITE_URL — он; иначе тот же хост, что и у подписки (как subscriptionPublicUrl).
 */
export function subscriptionOpenClientUrl(token, clientCode, platform) {
  const site =
    sitePublicUrl() ||
    import.meta.env.VITE_SUBSCRIPTION_BASE_URL?.replace(/\/$/, '') ||
    (typeof window !== 'undefined' ? window.location.origin : '')
  const rel = subscriptionOpenPath(token, clientCode, platform)
  return site ? `${site}${rel}` : rel
}
