/**
 * Открытие внешних ссылок (t.me и т.п.) — разная логика для телефона и ПК.
 */

/**
 * Телефон: переход в том же окне (после await window.open блокируется).
 * @param {string} url
 */
export function openDeepLinkMobile(url) {
  const u = String(url).trim()
  if (!u) return
  try {
    window.location.replace(u)
    return
  } catch {
    /* ignore */
  }
  try {
    const a = document.createElement('a')
    a.href = u
    a.rel = 'noopener noreferrer'
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } catch {
    /* ignore */
  }
}

/**
 * ПК: новая вкладка (после await на десктопе обычно не блокируется).
 * @param {string} url
 */
export function openDeepLinkDesktop(url) {
  const u = String(url).trim()
  if (!u) return
  try {
    window.open(u, '_blank', 'noopener,noreferrer')
  } catch {
    /* ignore */
  }
}
