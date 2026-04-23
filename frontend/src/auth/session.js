const TOKEN_KEY = 'vpn_access_token'
const ROLE_KEY = 'vpn_session_role'

function publicApiUrl(path) {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  const p = path.startsWith('/') ? path : `/${path}`
  return base ? `${base}${p}` : p
}

/** Кэш: защищены ли админ-эндпоинты (проверка GET /api/users/count без Bearer → 401). */
let adminJwtRequiredCache = null

export function invalidateAdminJwtProbe() {
  adminJwtRequiredCache = null
}

/**
 * Нужен ли JWT для доступа к /api/users и др. (заданы ADMIN_EMAIL + ADMIN_PASSWORD).
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
  if (r === 'admin' || r === 'user') return r
  return null
}

export function setSession(token, role) {
  localStorage.setItem(TOKEN_KEY, token)
  if (role === 'admin' || role === 'user') {
    localStorage.setItem(ROLE_KEY, role)
  }
  invalidateAdminJwtProbe()
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
  invalidateAdminJwtProbe()
}
