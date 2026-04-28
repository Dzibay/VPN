/** Логика выбора ссылок магазина (как на бывшей серверной open-странице). */

function has(R) {
  return R && (R.site || R.download)
}

function refFor(links, key) {
  const R = links && links[key]
  return has(R) ? R : null
}

function firstAvailableRef(...args) {
  for (let i = 0; i < args.length; i += 1) {
    const x = args[i]
    if (has(x)) return x
  }
  return null
}

/**
 * @param {Record<string, { site?: string | null, download?: string | null }> | null | undefined} links
 * @param {string} platform — windows | android | ios | macos | linux
 */
export function forcedStoreRefs(links, platform) {
  if (!links || !platform) return null
  let R = refFor(links, platform)
  if (has(R)) return R
  if (platform === 'macos')
    return firstAvailableRef(links.macos, links.windows, links.linux)
  if (platform === 'linux')
    return firstAvailableRef(links.linux, links.windows, links.macos)
  return null
}

/**
 * @param {Record<string, { site?: string | null, download?: string | null }> | null | undefined} links
 */
export function pickStoreRefsAuto(links) {
  if (!links) return null
  const u = typeof navigator !== 'undefined' ? navigator.userAgent || '' : ''
  if (/android/i.test(u)) return refFor(links, 'android')
  if (/iPhone|iPad|iPod/i.test(u)) return refFor(links, 'ios')
  if (/Win64|Windows NT|Win32|Windows Phone/i.test(u)) return refFor(links, 'windows')
  if (/Macintosh|Mac OS X/i.test(u) && !/iPhone|iPad|iPod/i.test(u)) {
    return firstAvailableRef(links.macos, links.windows, links.linux)
  }
  if (/Linux|X11/i.test(u) && !/Android/i.test(u)) {
    return firstAvailableRef(links.linux, links.windows)
  }
  return firstAvailableRef(
    links.windows,
    links.macos,
    links.linux,
    links.android,
    links.ios,
  )
}

/**
 * Телефон/планшет с Google Play или App Store (Android или iOS).
 * @returns {boolean}
 */
export function isMobileAppStoreDevice() {
  if (typeof navigator === 'undefined') return false
  const u = navigator.userAgent || ''
  return /android/i.test(u) || /iPhone|iPad|iPod/i.test(u)
}

/**
 * URL страницы магазина или прямой загрузки для текущего мобильного устройства
 * (та же логика, что выбор ссылок на /apps/:client). Для десктопа — null.
 *
 * @param {Record<string, { site?: string | null, download?: string | null }> | null | undefined} links
 * @param {string | null | undefined} platformFromQuery — как ?platform= на open-странице
 * @returns {string | null}
 */
export function getMobileStoreRedirectUrl(links, platformFromQuery) {
  if (!links || typeof links !== 'object') return null
  if (!isMobileAppStoreDevice()) return null
  const fp =
    platformFromQuery &&
    typeof platformFromQuery === 'string' &&
    ['windows', 'android', 'ios', 'macos', 'linux'].includes(
      platformFromQuery.toLowerCase(),
    )
      ? platformFromQuery.toLowerCase()
      : null
  const R = fp ? forcedStoreRefs(links, fp) : pickStoreRefsAuto(links)
  if (!R) return null
  const url = R.site || R.download
  return typeof url === 'string' && url ? url : null
}
