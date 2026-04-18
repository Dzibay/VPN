const STORAGE_KEY = 'vpn_admin_token'

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
