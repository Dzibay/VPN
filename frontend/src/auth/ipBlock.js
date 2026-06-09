let checked = false
let blocked = false

function publicApiUrl(path) {
  const base = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  const p = path.startsWith('/') ? path : `/${path}`
  return base ? `${base}${p}` : p
}

export function isIpBlockedApiResponse(status, data) {
  if (status !== 403) return false
  if (data && typeof data === 'object' && data.code === 'ip_blocked') return true
  const detail = data && typeof data === 'object' ? data.detail : null
  if (typeof detail === 'string') {
    return (
      detail === 'Доступ ограничен' ||
      detail === 'Доступ с этого IP заблокирован'
    )
  }
  return false
}

export function redirectToBlockedPage() {
  if (typeof window === 'undefined') return
  if (window.location.pathname === '/blocked') return
  window.location.replace('/blocked')
}

/** Проверка до монтирования Vue и в роутере (один раз за вкладку). */
export async function ensureIpBlockStatus() {
  if (checked) return blocked
  try {
    const res = await fetch(publicApiUrl('/api/public/ip-blocked'), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    const text = await res.text()
    let data = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        data = text
      }
    }
    if (isIpBlockedApiResponse(res.status, data)) {
      blocked = true
    } else if (res.ok) {
      blocked = Boolean(data?.blocked)
    } else {
      blocked = false
    }
  } catch {
    blocked = false
  }
  checked = true
  return blocked
}
