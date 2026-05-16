import { isMobileAppStoreDevice } from './subscriptionOpenStores.js'

/**
 * Пустая вкладка в цепочке клика — иначе после await Safari/Chrome блокируют window.open.
 * На телефоне не нужна: открываем ссылку через location.assign.
 * @returns {Window | null}
 */
export function openDeepLinkPopupPlaceholder() {
  if (isMobileAppStoreDevice()) return null
  try {
    return window.open('about:blank', '_blank', 'noopener,noreferrer')
  } catch {
    return null
  }
}

/**
 * @param {string} url
 * @param {{ popup?: Window | null }} [options]
 */
export function navigateDeepLink(url, { popup } = {}) {
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
  if (popup && !popup.closed) {
    try {
      popup.location.href = u
      return
    } catch {
      /* ignore */
    }
  }
  try {
    window.open(u, '_blank', 'noopener,noreferrer')
  } catch {
    /* ignore */
  }
}

/**
 * @param {Window | null | undefined} popup
 */
export function closeDeepLinkPopup(popup) {
  if (!popup || popup.closed) return
  try {
    popup.close()
  } catch {
    /* ignore */
  }
}
