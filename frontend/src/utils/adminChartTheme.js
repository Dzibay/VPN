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
