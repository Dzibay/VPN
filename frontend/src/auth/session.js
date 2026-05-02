const TOKEN_KEY = 'vpn_access_token'
const ROLE_KEY = 'vpn_session_role'

function publicApiUrl(path) {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  const p = path.startsWith('/') ? path : `/${path}`
  return base ? `${base}${p}` : p
}
/** Кэш: нужен ли Bearer для админ-API (проба GET /api/users/count без заголовка → 401). */
let adminJwtRequiredCache = null

export function invalidateAdminJwtProbe() {
  adminJwtRequiredCache = null
}

/**
 * Нужен ли Bearer JWT для админ-API (проба GET /api/users/count без заголовка → 401).
 */
export async function isAdminJwtRequired() {
  if (adminJwtRequiredCache !== null) return adminJwtRequiredCache
  try {
    const res = await fetch(publicApiUrl('/api/users/count'), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    adminJwtRequiredCache = res.status === 401
    return adminJwtRequiredCache
  } catch {
    adminJwtRequiredCache = true
    return true
  }
}

export function getAccessToken() {
  if (typeof localStorage === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getSessionRole() {
  if (typeof localStorage === 'undefined') return null
  const r = localStorage.getItem(ROLE_KEY)
  if (r === 'admin' || r === 'user' || r === 'manager') return r
  return null
}

export function setSession(token, role) {
  localStorage.setItem(TOKEN_KEY, token)
  if (role === 'admin' || role === 'user' || role === 'manager') {
    localStorage.setItem(ROLE_KEY, role)
  }
  invalidateAdminJwtProbe()
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
  invalidateAdminJwtProbe()
}

/** Payload JWT без проверки подписи (только для извлечения role/exp после выдачи API). */
function parseJwtPayloadUnsafe(token) {
  const parts = String(token).split('.')
  if (parts.length !== 3) return null
  let base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
  const pad = base64.length % 4
  if (pad) base64 += '='.repeat(4 - pad)
  try {
    const json = atob(base64)
    return JSON.parse(json)
  } catch {
    return null
  }
}

/**
 * Переход из Telegram с URL вида /cabinet#tg_sso_token=<JWT>: сохранить сессию и убрать фрагмент из истории.
 * @returns {boolean} true если фрагмент обработан
 */
export function consumeCabinetSsoFragment(routeName) {
  if (routeName !== 'cabinet' || typeof window === 'undefined') return false
  const hash = window.location.hash || ''
  if (!hash.startsWith('#tg_sso_token=')) return false
  const jwt = hash.slice('#tg_sso_token='.length).trim()
  const clean = `${window.location.pathname}${window.location.search}`
  if (!jwt) {
    window.history.replaceState(window.history.state, '', clean)
    return false
  }
  const payload = parseJwtPayloadUnsafe(jwt)
  const role = payload?.role
  const invalid =
    !payload ||
    (role !== 'user' && role !== 'manager' && role !== 'admin') ||
    (payload.exp != null &&
      typeof payload.exp === 'number' &&
      payload.exp * 1000 < Date.now())
  if (invalid) {
    window.history.replaceState(window.history.state, '', clean)
    return false
  }
  setSession(jwt, role)
  window.history.replaceState(window.history.state, '', clean)
  return true
}
