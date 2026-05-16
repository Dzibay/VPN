/**
 * Открытие внешних deep link (t.me и т.п.).
 * Телефон: переход в том же окне (window.open после await блокируется в Safari).
 * ПК: новая вкладка.
 */

/** @returns {boolean} */
export function isMobileDevice() {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent || ''
  if (
    /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile/i.test(
      ua,
    )
  ) {
    return true
  }
  if (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) {
    return true
  }
  return false
}

/**
 * @param {string} url
 * @param {{ mobile?: boolean }} [options] — mobile по умолчанию из UA
 */
export function openTelegramDeepLink(url, { mobile = isMobileDevice() } = {}) {
  const u = String(url).trim()
  if (!u) return
  if (mobile) {
    try {
      window.location.replace(u)
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
