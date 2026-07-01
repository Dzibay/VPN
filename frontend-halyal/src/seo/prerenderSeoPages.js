import fs from 'node:fs'
import path from 'node:path'

import { SEO_LANDING_PATHS } from '../content/seo/catalog.js'
import { getSeoPageContent } from '../content/seo/getSeoPageContent.js'
import { applyMetaToHtml, buildPageMeta } from './documentMeta.js'

const NODE_ENV = globalThis.process?.env ?? {}

/**
 * Генерирует index.html с meta-тегами для каждой SEO-страницы (nginx: try_files $uri $uri/).
 *
 * @param {{ distDir: string, siteUrl: string, indexHtml: string }} options
 * @returns {string[]} записанные пути
 */
export function prerenderSeoPages({ distDir, siteUrl, indexHtml }) {
  if (NODE_ENV.VITE_DISABLE_SEO_PAGES === 'true') {
    return []
  }
  const written = []

  for (const seoPath of SEO_LANDING_PATHS) {
    const content = getSeoPageContent(seoPath)
    if (!content?.meta) continue

    const meta = buildPageMeta(siteUrl, seoPath, content)
    const html = applyMetaToHtml(indexHtml, meta)
    const segments = seoPath.split('/').filter(Boolean)
    const outDir = path.join(distDir, ...segments)
    fs.mkdirSync(outDir, { recursive: true })
    fs.writeFileSync(path.join(outDir, 'index.html'), html, 'utf8')
    written.push(seoPath)
  }

  return written
}
