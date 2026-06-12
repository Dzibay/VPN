/**
 * Каталог SEO-страниц (без Vue/router). path/title/sortOrder должны совпадать с backend/app/domain/seo_pages/catalog.py
 * @typedef {{ path: string, title: string, sortOrder: number, name: string }} SeoPageDef
 */

/** @type {SeoPageDef[]} */
export const SEO_PAGES = [
  {
    path: '/',
    title: 'Главная',
    sortOrder: 1,
    name: 'seo-home',
  },
  {
    path: '/vpn-dlya-youtube',
    title: 'VPN для YouTube',
    sortOrder: 10,
    name: 'seo-vpn-dlya-youtube',
  },
  {
    path: '/vpn-dlya-youtube/android',
    title: 'VPN для YouTube на Android',
    sortOrder: 11,
    name: 'seo-vpn-dlya-youtube-android',
  },
  {
    path: '/vpn-dlya-youtube/pc',
    title: 'VPN для YouTube на ПК',
    sortOrder: 12,
    name: 'seo-vpn-dlya-youtube-pc',
  },
  {
    path: '/vpn-dlya-gemini',
    title: 'VPN для Gemini',
    sortOrder: 20,
    name: 'seo-vpn-dlya-gemini',
  },
  {
    path: '/vpn-dlya-telegram',
    title: 'VPN для Telegram',
    sortOrder: 30,
    name: 'seo-vpn-dlya-telegram',
  },
  {
    path: '/vpn-dlya-iphone',
    title: 'VPN для iPhone',
    sortOrder: 40,
    name: 'seo-vpn-dlya-iphone',
  },
]

/** @type {string[]} */
export const SEO_PAGE_PATHS = SEO_PAGES.map((page) => page.path)

/** Пути SEO-лендингов (без главной) — sitemap, prerender. */
export const SEO_LANDING_PATHS = SEO_PAGES.filter((page) => page.path !== '/').map(
  (page) => page.path,
)

const byPath = new Map(SEO_PAGES.map((page) => [page.path, page]))

/** @param {string | undefined | null} path */
export function getSeoPageByPath(path) {
  const raw = String(path || '/').trim() || '/'
  const normalized = raw.length > 1 && raw.endsWith('/') ? raw.slice(0, -1) : raw
  return byPath.get(normalized) ?? byPath.get(normalized.startsWith('/') ? normalized : `/${normalized}`)
}
