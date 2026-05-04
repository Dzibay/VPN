import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// Прокси на API: порт должен совпадать с локальным uvicorn (по умолчанию 5000).
const API_TARGET = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:5000'

/**
 * @param {Record<string, string>} env result of loadEnv
 * Приоритет: VITE_PUBLIC_SITE_URL (полный URL) → SITE_ADDRESS (домен без схемы, как в deploy/.env) → плейсхолдер.
 * SITE_ADDRESS в Docker передаётся в nginx-build через ARG/ENV.
 */
function siteUrlFromEnv(env) {
  const explicit = (
    env.VITE_PUBLIC_SITE_URL ||
    process.env.VITE_PUBLIC_SITE_URL ||
    ''
  )
    .trim()
    .replace(/\/$/, '')
  if (explicit) return explicit

  const host = (env.SITE_ADDRESS || process.env.SITE_ADDRESS || '').trim()
  if (host) {
    if (/^https?:\/\//i.test(host)) return host.replace(/\/$/, '')
    return `https://${host.replace(/\/$/, '')}`
  }
  return 'https://example.com'
}

function buildSeoStrings(siteUrl) {
  const ogImage = `${siteUrl}/icons/podorozhnik-logo.png`
  const robots = `User-agent: *
Allow: /

# Закрытые разделы SPA
Disallow: /cabinet
Disallow: /admin

Sitemap: ${siteUrl}/sitemap.xml
`

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${siteUrl}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>${siteUrl}/login</loc>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
  <url>
    <loc>${siteUrl}/register</loc>
    <changefreq>monthly</changefreq>
    <priority>0.4</priority>
  </url>
</urlset>
`

  const security = `# security.txt (RFC 9116) — укажите рабочий mailto
Contact: mailto:security@example.com
Preferred-Languages: ru, en
Canonical: ${siteUrl}/.well-known/security.txt
`

  return { robots, sitemap, ogImage, security }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const siteUrl = siteUrlFromEnv(env)
  const { robots, sitemap, ogImage, security } = buildSeoStrings(siteUrl)

  return {
    plugins: [
      vue(),
      {
        name: 'podorozhnik-seo',
        transformIndexHtml: {
          order: 'pre',
          handler(html) {
            return html
              .replaceAll('__SITE_URL__', siteUrl)
              .replaceAll('__OG_IMAGE__', ogImage)
          },
        },
        generateBundle() {
          this.emitFile({ type: 'asset', fileName: 'robots.txt', source: robots })
          this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: sitemap })
          this.emitFile({
            type: 'asset',
            fileName: '.well-known/security.txt',
            source: security,
          })
        },
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            const p = (req.url || '').split('?')[0] || ''
            if (p === '/robots.txt') {
              res.setHeader('Content-Type', 'text/plain; charset=utf-8')
              res.end(robots)
              return
            }
            if (p === '/sitemap.xml') {
              res.setHeader('Content-Type', 'application/xml; charset=utf-8')
              res.end(sitemap)
              return
            }
            if (p === '/.well-known/security.txt') {
              res.setHeader('Content-Type', 'text/plain; charset=utf-8')
              res.end(security)
              return
            }
            next()
          })
        },
      },
    ],
    server: {
      host: true,
      proxy: {
        '/api': {
          target: API_TARGET,
          changeOrigin: true,
        },
        '/sub': {
          target: API_TARGET,
          changeOrigin: true,
          /** Страница открытия клиента — Vue; остальное /sub/* — API. */
          bypass(req) {
            if (req.method !== 'GET') return
            const path = (req.url || '').split('?')[0] || ''
            if (path.endsWith('/data')) return
            if (/^\/sub\/[^/]+\/open\/[^/]+$/.test(path)) return '/index.html'
          },
        },
        '/swagger': {
          target: API_TARGET,
          changeOrigin: true,
        },
        '/redoc': {
          target: API_TARGET,
          changeOrigin: true,
        },
        '/openapi.json': {
          target: API_TARGET,
          changeOrigin: true,
        },
      },
    },
  }
})
