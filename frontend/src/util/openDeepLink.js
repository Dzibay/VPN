import { isMobileAppStoreDevice } from './subscriptionOpenStores.js'

/**
 * t.me и прочие внешние ссылки.
 * Телефон: location.assign (window.open после await блокирует Safari).
 * ПК: window.open после ответа API (на десктопе обычно не блокируется).
 *
 * @param {string} url
 */
export function navigateDeepLink(url) {
  const u = String(url).trim()
  if (!u) return
  if (isMobileAppStoreDevice()) {
    try {
      window.location.assign(u)
    } catch {
      /* ignore */
    }
    return
  }
  try {
    window.open(u, '_blank', 'noopener,noreferrer')
  } catch {
    /* ignore */
  }
}
