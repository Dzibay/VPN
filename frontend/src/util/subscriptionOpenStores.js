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

/** Только телефоны с каталогами App Store / Google Play (не ПК, не планшеты как отдельный кейс). */
export function mobileIosOrAndroidPlatform() {
  if (typeof navigator === 'undefined') return null
  const u = navigator.userAgent || ''
  if (/android/i.test(u)) return 'android'
  if (/iPhone|iPad|iPod/i.test(u)) return 'ios'
  return null
}

/**
 * Прямая ссылка для установки: магазин (download), иначе сайт (site).
 * @param {Record<string, { site?: string | null, download?: string | null }> | null | undefined} links
 * @param {'android' | 'ios'} platform
 */
export function storeInstallHref(links, platform) {
  const refs = forcedStoreRefs(links, platform)
  if (!refs) return null
  const d = refs.download && String(refs.download).trim()
  if (d) return d
  const s = refs.site && String(refs.site).trim()
  return s || null
}
