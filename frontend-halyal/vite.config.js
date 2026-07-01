import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { buildSeoAssets } from './src/seo/buildSeoAssets.js'
import { prerenderSeoPages } from './src/seo/prerenderSeoPages.js'

// Прокси на API: порт должен совпадать с локальным uvicorn (по умолчанию 5000).
const NODE_ENV = globalThis.process?.env ?? {}
const API_TARGET = NODE_ENV.VITE_DEV_API_TARGET || 'http://127.0.0.1:5000'

/**
 * @param {Record<string, string>} env result of loadEnv
 * Приоритет: VITE_PUBLIC_SITE_URL (полный URL) → SITE_ADDRESS (домен без схемы, как в deploy/.env) → плейсхолдер.
 * SITE_ADDRESS в Docker передаётся в nginx-build через ARG/ENV.
 */
function siteUrlFromEnv(env) {
  const explicit = (
    env.VITE_PUBLIC_SITE_URL ||
    NODE_ENV.VITE_PUBLIC_SITE_URL ||
    ''
  )
    .trim()
    .replace(/\/$/, '')
  if (explicit) return explicit

  const host = (env.SITE_ADDRESS || NODE_ENV.SITE_ADDRESS || '').trim()
  if (host) {
    if (/^https?:\/\//i.test(host)) return host.replace(/\/$/, '')
    return `https://${host.replace(/\/$/, '')}`
  }
  return 'https://example.com'
}

function brandMetaFromEnv() {
  return {
    siteName: 'Halyal VPN',
    title: 'Halyal VPN — быстрый и надёжный VPN для ежедневного доступа',
    description:
      'Halyal VPN открывает нужные зарубежные сервисы через защищённый канал, а российские банки и Госуслуги работают без постоянного переключения.',
    keywords:
      'VPN, Halyal VPN, VPN для YouTube, VPN для Telegram, VPN для ChatGPT, умная маршрутизация, защищенный VPN',
    schemaDescription:
      'VPN-сервис Halyal VPN с умной маршрутизацией: зарубежные сервисы через защищённый канал, российские приложения — напрямую.',
    ogImagePath: '/icons/halyal-logo.png',
  }
}

/** Halyal: favicon/манifest лежат в public/icons/. */
function brandIconsPlugin() {
  return { name: 'brand-icons-halyal-static' }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const siteUrl = siteUrlFromEnv(env)
  const brandMeta = brandMetaFromEnv()
  const ogImagePath = brandMeta.ogImagePath
  const { robots, sitemap, ogImage, security } = buildSeoAssets(siteUrl, ogImagePath)

  return {
    plugins: [
      vue(),
      brandIconsPlugin(),
      {
        name: 'halyal-seo',
        transformIndexHtml: {
          order: 'pre',
          handler(html) {
            return html
              .replaceAll('__SITE_URL__', siteUrl)
              .replaceAll('__OG_IMAGE__', ogImage)
              .replaceAll(
                'Подорожник VPN — YouTube, Telegram и ChatGPT без выключения VPN',
                brandMeta?.title || 'Подорожник VPN — YouTube, Telegram и ChatGPT без выключения VPN',
              )
              .replaceAll(
                'YouTube, Gemini и ChatGPT через VPN. Российские банки и Госуслуги работают без постоянного переключения. Пробный период 3 дня, до 5 устройств.',
                brandMeta?.description ||
                  'YouTube, Gemini и ChatGPT через VPN. Российские банки и Госуслуги работают без постоянного переключения. Пробный период 3 дня, до 5 устройств.',
              )
              .replaceAll(
                'VPN, VPN для YouTube, VPN для Telegram, VPN для ChatGPT, VPN для Gemini, VPN Россия, умная маршрутизация, VPN без выключения, Подорожник',
                brandMeta?.keywords ||
                  'VPN, VPN для YouTube, VPN для Telegram, VPN для ChatGPT, VPN для Gemini, VPN Россия, умная маршрутизация, VPN без выключения, Подорожник',
              )
              .replaceAll('Подорожник VPN', brandMeta?.siteName || 'Подорожник VPN')
              .replaceAll(
                'VPN-сервис с умной маршрутизацией: зарубежные сервисы через защищённый канал, российские банки и Госуслуги — без постоянного переключения.',
                brandMeta?.schemaDescription ||
                  'VPN-сервис с умной маршрутизацией: зарубежные сервисы через защищённый канал, российские банки и Госуслуги — без постоянного переключения.',
              )
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
        closeBundle() {
          const distDir = path.resolve(process.cwd(), 'dist')
          const indexPath = path.join(distDir, 'index.html')
          if (!fs.existsSync(indexPath)) return

          const indexHtml = fs.readFileSync(indexPath, 'utf8')
          prerenderSeoPages({ distDir, siteUrl, indexHtml })
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
    build: {
      // Ограничиваем собственные чанки до 250 KB, чтобы не получить «всё в одном».
      chunkSizeWarningLimit: 300,
      rollupOptions: {
        output: {
          /**
           * Вендор-чанки: Chart.js тянется только на админ-аналитики,
           * vue + vue-router используются на каждом роуте — один shared chunk.
           * Правки в одной вью не инвалидируют кэш этих vendor-чанков.
           * Rolldown (Vite 8) поддерживает только функциональную форму manualChunks.
           */
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (id.includes('node_modules/chart.js/')) return 'chart-vendor'
            if (
              id.includes('node_modules/vue-router/') ||
              /node_modules\/@vue\//.test(id) ||
              /node_modules\/vue\//.test(id)
            ) {
              return 'vue-vendor'
            }
          },
        },
      },
    },
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
      },
    },
  }
})
