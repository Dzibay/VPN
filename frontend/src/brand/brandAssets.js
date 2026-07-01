/** Пути брендовых ассетов (зависят от VITE_BRAND при сборке). */

function resolveFrontendBrand() {
  if (typeof import.meta !== 'undefined' && import.meta.env) {
    return String(import.meta.env.VITE_BRAND || '').trim().toLowerCase()
  }
  return String(globalThis.process?.env?.VITE_BRAND || '').trim().toLowerCase()
}

const FRONTEND_BRAND = resolveFrontendBrand()

export const isHalyalBrand = FRONTEND_BRAND === 'halyal'

export const brandName = isHalyalBrand ? 'Halyal VPN' : 'Подорожник VPN'

/** Круглый логотип в шапке и og:image. */
export const brandLogoPath = isHalyalBrand
  ? '/icons/halyal-logo.png'
  : '/icons/podorozhnik-logo.png'
