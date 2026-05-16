/**
 * Телефон / планшет (шире, чем isMobileAppStoreDevice — только магазины).
 * @returns {boolean}
 */
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
  // iPadOS 13+: в UA часто «Macintosh»
  if (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) {
    return true
  }
  return false
}
