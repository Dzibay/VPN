/** Версия политики: при изменении cookies-баннер покажется снова. */
export const COOKIE_CONSENT_VERSION = '1'

export const COOKIE_CONSENT_STORAGE_KEY = 'vpnCookieConsent'

export function hasCookieConsent() {
  if (typeof localStorage === 'undefined') return true
  try {
    const raw = localStorage.getItem(COOKIE_CONSENT_STORAGE_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    return data?.version === COOKIE_CONSENT_VERSION
  } catch {
    return false
  }
}

export function acceptCookieConsent() {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(
    COOKIE_CONSENT_STORAGE_KEY,
    JSON.stringify({
      version: COOKIE_CONSENT_VERSION,
      acceptedAt: new Date().toISOString(),
    }),
  )
}
