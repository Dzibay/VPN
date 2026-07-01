/**
 * Каталог SEO-страниц. path/title/sortOrder должны совпадать с backend/app/domain/seo_pages/catalog.py
 * @typedef {import('./catalog.js').SeoPageDef} SeoPageDef
 */

export {
  SEO_PAGES,
  SEO_PAGE_PATHS,
  SEO_LANDING_PATHS,
  getSeoPageByPath,
} from './catalog.js'

import { SEO_PAGES } from './catalog.js'

/** @returns {import('vue-router').RouteRecordRaw[]} */
export function buildSeoPageRoutes() {
  return SEO_PAGES.filter((page) => page.path !== '/').map((page) => ({
    path: page.path,
    name: page.name,
    component: () => import('../../views/SeoPageView.vue'),
    meta: {
      seoPage: true,
      seoPath: page.path,
      seoTitle: page.title,
    },
  }))
}
