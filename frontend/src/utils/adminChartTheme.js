/** Тема линейных графиков админки из CSS-переменных (:root). */

export function rgbTupleFromCssColor(css) {
  const m = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(String(css).trim())
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])]
  const hx = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(String(css).trim())
  if (hx) {
    return [
      parseInt(hx[1], 16),
      parseInt(hx[2], 16),
      parseInt(hx[3], 16),
    ]
  }
  return [88, 214, 141]
}

export function rgbTupleFromVar(name, fallbackHex) {
  if (typeof document === 'undefined') {
    return rgbTupleFromCssColor(fallbackHex)
  }
  const probe = document.createElement('span')
  probe.style.cssText =
    'position:absolute;left:-9999px;top:0;color:var(' +
    name +
    ',' +
    fallbackHex +
    ')'
  document.body.appendChild(probe)
  const rgb = rgbTupleFromCssColor(getComputedStyle(probe).color)
  probe.remove()
  return rgb
}

export function rootToken(name, fallback) {
  if (typeof document === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

export function rgba(rgb, a) {
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`
}

export function adminChartTheme(extraRgb) {
  const accent = rgbTupleFromVar('--accent', '#58d68d')
  const trafficOrange = extraRgb?.trafficOrange ?? [251, 146, 60]
  const cardBorder = rootToken('--accent-border', 'rgba(88, 214, 141, 0.42)')
  const surface = rootToken('--card-bg', 'rgba(12, 16, 14, 0.94)')
  return {
    accent,
    trafficOrange,
    accentBorder: cardBorder,
    tooltipBg: surface,
    textH: rootToken('--text-h', '#e8f4ec'),
    muted: rootToken('--muted', '#6d8578'),
    grid: rootToken('--accent-chart-grid', 'rgba(88, 214, 141, 0.12)'),
    surfaceBg: rootToken('--surface', '#0c100e'),
  }
}

/** Тики/сетка как у графика «Финансы» (столбцы). */
export function financeBarTickColor() {
  if (typeof window === 'undefined') return 'rgba(45, 85, 65, 0.45)'
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'rgba(200, 228, 210, 0.55)'
    : 'rgba(45, 85, 65, 0.45)'
}

export function financeBarGridColor() {
  return 'rgba(88, 214, 141, 0.12)'
}

/** @param {string} css */
function parseRgbChannels(css) {
  const s = String(css).trim()
  const m = /rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i.exec(s)
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])]
  const hx = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(s)
  if (hx) {
    return [
      parseInt(hx[1], 16),
      parseInt(hx[2], 16),
      parseInt(hx[3], 16),
    ]
  }
  return null
}

/**
 * Снимает var(...) в реальный rgb/rgba (для фона тултипа Chart.js на canvas).
 * @param {string} value
 * @param {string} fallback
 */
export function resolveBackgroundCss(value, fallback) {
  if (typeof document === 'undefined') return fallback
  const v = String(value || '').trim()
  if (!v) return fallback
  if (!v.includes('var(') && parseRgbChannels(v)) return v
  const el = document.createElement('div')
  el.style.cssText = `position:absolute;left:-9999px;top:0;background:${v}`
  document.body.appendChild(el)
  const out = getComputedStyle(el).backgroundColor
  el.remove()
  return parseRgbChannels(out) ? out : fallback
}

/**
 * Цвета подписей тултипа Chart.js под фон (тёмный фон → светлый текст).
 * @param {string} backgroundResolved — rgb/rgba после resolveBackgroundCss
 * @param {ReturnType<typeof adminChartTheme>} theme
 */
export function chartTooltipColors(backgroundResolved, theme) {
  const ch = parseRgbChannels(backgroundResolved)
  if (!ch) {
    return {
      titleColor: theme.textH,
      bodyColor: theme.textH,
      footerColor: theme.textH,
      borderColor: theme.accentBorder,
    }
  }
  const [r, g, b] = ch
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  if (lum < 0.45) {
    return {
      titleColor: '#f4fdf8',
      bodyColor: '#e6f2eb',
      footerColor: '#cfe8db',
      borderColor: 'rgba(120, 200, 160, 0.45)',
    }
  }
  return {
    titleColor: theme.textH,
    bodyColor: theme.textH,
    footerColor: theme.textH,
    borderColor: theme.accentBorder,
  }
}
