import { vpnDlyaYoutubePage } from './pages/vpn-dlya-youtube.js'
import { vpnDlyaYoutubeAndroidPage } from './pages/vpn-dlya-youtube-android.js'
import { vpnDlyaYoutubePcPage } from './pages/vpn-dlya-youtube-pc.js'
import { vpnDlyaGeminiPage } from './pages/vpn-dlya-gemini.js'
import { vpnDlyaTelegramPage } from './pages/vpn-dlya-telegram.js'

/** @type {Record<string, object>} */
const SEO_PAGE_CONTENT = {
  '/vpn-dlya-youtube': vpnDlyaYoutubePage,
  '/vpn-dlya-youtube/android': vpnDlyaYoutubeAndroidPage,
  '/vpn-dlya-youtube/pc': vpnDlyaYoutubePcPage,
  '/vpn-dlya-gemini': vpnDlyaGeminiPage,
  '/vpn-dlya-telegram': vpnDlyaTelegramPage,
}
/** @param {string | undefined | null} path */
export function getSeoPageContent(path) {
  const raw = String(path || '').trim() || '/'
  const normalized = raw.length > 1 && raw.endsWith('/') ? raw.slice(0, -1) : raw
  return SEO_PAGE_CONTENT[normalized] ?? null
}
