/**
 * Учёт переходов на SEO-страницы: POST /api/public/seo-pages/track
 * один раз на браузер для каждого path (как реферальный track-click).
 */
import { fetchJson } from '../api/client.js'

const VIEW_SENT_PREFIX = 'vpn_seo_view_sent_'

/** @param {string} path */
export function normalizeSeoPath(path) {
  let raw = String(path || '/').trim() || '/'
  if (!raw.startsWith('/')) raw = `/${raw}`
  if (raw.length > 1 && raw.endsWith('/')) raw = raw.slice(0, -1)
  return raw || '/'
}

/**
 * @param {string} path — путь страницы, например /vpn-dlya-youtube
 */
export function trackSeoPageView(path) {
  if (typeof window === 'undefined') return

  const normalized = normalizeSeoPath(path)
  const dedupe = VIEW_SENT_PREFIX + normalized

  try {
    if (window.localStorage.getItem(dedupe)) return
    window.localStorage.setItem(dedupe, '1')
  } catch {
    /* если dedupe не удалось — всё равно пробуем учёт перехода раз */
  }

  void fetchJson('/api/public/seo-pages/track', {
    method: 'POST',
    body: JSON.stringify({ path: normalized }),
  }).catch(() => {})
}

/**
 * Вызывать из router.afterEach для маршрутов с meta.seoPage.
 * @param {import('vue-router').RouteLocationNormalizedLoaded} route
 */
export function trackSeoPageFromRoute(route) {
  if (!route.meta?.seoPage) return
  const path =
    typeof route.meta.seoPath === 'string' && route.meta.seoPath
      ? route.meta.seoPath
      : route.path
  trackSeoPageView(path)
}
