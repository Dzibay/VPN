import { vpnDlyaYoutubePage } from './pages/vpn-dlya-youtube.js'
import { vpnDlyaYoutubeAndroidPage } from './pages/vpn-dlya-youtube-android.js'
import { vpnDlyaYoutubePcPage } from './pages/vpn-dlya-youtube-pc.js'
import { vpnDlyaGeminiPage } from './pages/vpn-dlya-gemini.js'
import { vpnDlyaTelegramPage } from './pages/vpn-dlya-telegram.js'
import { vpnDlyaIphonePage } from './pages/vpn-dlya-iphone.js'
import { vpnDlyaAndroidPage } from './pages/vpn-dlya-android.js'

/** @type {Record<string, object>} */
const SEO_PAGE_CONTENT = {
  '/vpn-dlya-youtube': vpnDlyaYoutubePage,
  '/vpn-dlya-youtube/android': vpnDlyaYoutubeAndroidPage,
  '/vpn-dlya-youtube/pc': vpnDlyaYoutubePcPage,
  '/vpn-dlya-gemini': vpnDlyaGeminiPage,
  '/vpn-dlya-telegram': vpnDlyaTelegramPage,
  '/vpn-dlya-iphone': vpnDlyaIphonePage,
  '/vpn-dlya-android': vpnDlyaAndroidPage,
}
/** @param {string | undefined | null} path */
export function getSeoPageContent(path) {
  const raw = String(path || '').trim() || '/'
  const normalized = raw.length > 1 && raw.endsWith('/') ? raw.slice(0, -1) : raw
  return SEO_PAGE_CONTENT[normalized] ?? null
}
