const STORAGE_KEY = 'vpn_admin_token'
const USER_STORAGE_KEY = 'vpn_user_token'

let authRequiredCache = null

export function getAdminToken() {
  if (typeof localStorage === 'undefined') return null
  return localStorage.getItem(STORAGE_KEY)
}

export function setAdminToken(token) {
  localStorage.setItem(STORAGE_KEY, token)
  authRequiredCache = null
}

export function clearAdminToken() {
  localStorage.removeItem(STORAGE_KEY)
  authRequiredCache = null
}

export function getUserToken() {
  if (typeof localStorage === 'undefined') return null
  return localStorage.getItem(USER_STORAGE_KEY)
}

export function setUserToken(token) {
  localStorage.setItem(USER_STORAGE_KEY, token)
}

export function clearUserToken() {
  localStorage.removeItem(USER_STORAGE_KEY)
}

/** Сброс кэша (например после смены настроек на сервере). */
export function invalidateAuthStatusCache() {
  authRequiredCache = null
}

/**
 * @param {() => Promise<{ admin_auth_required: boolean }>} fetchStatus
 */
export async function isAdminAuthRequired(fetchStatus) {
  if (authRequiredCache !== null) return authRequiredCache
  try {
    const data = await fetchStatus()
    authRequiredCache = Boolean(data?.admin_auth_required)
    return authRequiredCache
  } catch {
    authRequiredCache = true
    return true
  }
}
