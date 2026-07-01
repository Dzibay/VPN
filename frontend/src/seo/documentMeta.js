/** @typedef {{ title: string, description: string, canonicalUrl: string, ogImage: string }} PageDocumentMeta */

const CLIENT_ENV = import.meta.env || {}
const isHalyalBrand = CLIENT_ENV.VITE_BRAND === 'halyal'

export const DEFAULT_DOCUMENT_META = isHalyalBrand
  ? {
      title: 'Halyal VPN — быстрый и надёжный VPN для ежедневного доступа',
      description:
        'Halyal VPN открывает нужные зарубежные сервисы через защищённый канал, а российские банки и Госуслуги работают без постоянного переключения.',
      ogImagePath: '/icons/podorozhnik-logo.png',
    }
  : {
      title: 'Подорожник VPN — YouTube, Telegram и ChatGPT без выключения VPN',
      description:
        'YouTube, Gemini и ChatGPT через VPN. Российские банки и Госуслуги работают без постоянного переключения. Пробный период 3 дня, до 5 устройств.',
      ogImagePath: '/icons/podorozhnik-logo.png',
    }

/** @returns {string} */
export function resolvePublicSiteUrl() {
  if (typeof window !== 'undefined') {
    const fromEnv = import.meta.env.VITE_PUBLIC_SITE_URL?.replace(/\/$/, '')
    if (fromEnv) return fromEnv
    return window.location.origin
  }
  return ''
}

/**
 * @param {string} siteUrl
 * @param {string} path
 * @param {object | null | undefined} content
 * @returns {PageDocumentMeta}
 */
export function buildPageMeta(siteUrl, path, content) {
  const base = siteUrl.replace(/\/$/, '')
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const canonicalUrl = `${base}${normalizedPath}`
  const title = content?.meta?.title ?? DEFAULT_DOCUMENT_META.title
  const description = content?.meta?.description ?? DEFAULT_DOCUMENT_META.description
  const ogImagePath = content?.hero?.bgImage ?? DEFAULT_DOCUMENT_META.ogImagePath
  const ogImage = ogImagePath.startsWith('http')
    ? ogImagePath
    : `${base}${ogImagePath.startsWith('/') ? ogImagePath : `/${ogImagePath}`}`

  return { title, description, canonicalUrl, ogImage }
}

/** @param {string} value */
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
}

/**
 * @param {string} html
 * @param {PageDocumentMeta} meta
 * @returns {string}
 */
export function applyMetaToHtml(html, meta) {
  const { title, description, canonicalUrl, ogImage } = meta
  let out = html

  out = out.replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(title)}</title>`)

  out = replaceMetaContent(out, 'name', 'description', description)
  out = replaceLinkHref(out, 'canonical', canonicalUrl)

  out = replaceMetaContent(out, 'property', 'og:title', title)
  out = replaceMetaContent(out, 'property', 'og:description', description)
  out = replaceMetaContent(out, 'property', 'og:url', canonicalUrl)
  out = replaceMetaContent(out, 'property', 'og:image', ogImage)

  out = replaceMetaContent(out, 'name', 'twitter:title', title)
  out = replaceMetaContent(out, 'name', 'twitter:description', description)
  out = replaceMetaContent(out, 'name', 'twitter:image', ogImage)

  return out
}

/**
 * @param {string} html
 * @param {'name' | 'property'} attrKind
 * @param {string} key
 * @param {string} content
 */
function replaceMetaContent(html, attrKind, key, content) {
  const escaped = escapeHtml(content)
  const re = new RegExp(
    `(<meta\\s+${attrKind}="${key}"\\s+content=")[^"]*(")`,
    'i',
  )
  if (re.test(html)) {
    return html.replace(re, `$1${escaped}$2`)
  }
  return html.replace(
    '</head>',
    `    <meta ${attrKind}="${key}" content="${escaped}" />\n  </head>`,
  )
}

/**
 * @param {string} html
 * @param {string} rel
 * @param {string} href
 */
function replaceLinkHref(html, rel, href) {
  const re = new RegExp(`(<link\\s+rel="${rel}"\\s+href=")[^"]*(")`, 'i')
  if (re.test(html)) {
    return html.replace(re, `$1${href}$2`)
  }
  return html.replace(
    '</head>',
    `    <link rel="${rel}" href="${href}" />\n  </head>`,
  )
}

/** @param {PageDocumentMeta} meta */
export function applyDocumentMeta(meta) {
  if (typeof document === 'undefined') return

  document.title = meta.title
  setMetaByName('description', meta.description)
  setLinkRel('canonical', meta.canonicalUrl)

  setMetaByProperty('og:title', meta.title)
  setMetaByProperty('og:description', meta.description)
  setMetaByProperty('og:url', meta.canonicalUrl)
  setMetaByProperty('og:image', meta.ogImage)

  setMetaByName('twitter:title', meta.title)
  setMetaByName('twitter:description', meta.description)
  setMetaByName('twitter:image', meta.ogImage)
}

/** @param {import('vue-router').RouteLocationNormalized} route */
export function routeShouldNoindex(route) {
  if (route.meta?.noindex) return true
  const path = route.path
  if (path.startsWith('/cabinet')) return true
  if (path.startsWith('/admin')) return true
  if (path.startsWith('/sub/')) return true
  if (path === '/blocked') return true
  return false
}

/** @param {boolean} noindex */
export function applyRobotsMeta(noindex) {
  if (typeof document === 'undefined') return

  const el = document.querySelector('meta[name="robots"]')
  if (noindex) {
    setMetaByName('robots', 'noindex, follow')
    return
  }
  el?.remove()
}

/** @param {string} siteUrl */
export function applyDefaultDocumentMeta(siteUrl) {
  const base = (siteUrl || resolvePublicSiteUrl()).replace(/\/$/, '')
  applyDocumentMeta({
    title: DEFAULT_DOCUMENT_META.title,
    description: DEFAULT_DOCUMENT_META.description,
    canonicalUrl: `${base}/`,
    ogImage: `${base}${DEFAULT_DOCUMENT_META.ogImagePath}`,
  })
}

/** @param {string} name @param {string} content */
function setMetaByName(name, content) {
  let el = document.querySelector(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

/** @param {string} property @param {string} content */
function setMetaByProperty(property, content) {
  let el = document.querySelector(`meta[property="${property}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('property', property)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

/** @param {string} rel @param {string} href */
function setLinkRel(rel, href) {
  let el = document.querySelector(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}
