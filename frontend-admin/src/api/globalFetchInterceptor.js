/**
 * Глобальный fetch-interceptor для frontend-admin.
 *
 * Задача: legacy-views (из ../frontend/src/views/*.vue) переиспользуются в админ-панели
 * через vite alias. Их fetchJson читает JWT из localStorage — с bridge staff→legacy это
 * работает. Но им нужно ещё передавать X-Admin-Project, чтобы backend фильтровал данные
 * per-project (см. ProjectContextMiddleware, приоритет header). Переписывать legacy
 * client.js нельзя (общий с публичным фронтом). Вместо этого патчим window.fetch:
 * для всех запросов на /api/* добавляем заголовок X-Admin-Project.
 */
import { getCurrentProject } from '../auth/staffSession.js'

let installed = false

export function installGlobalFetchInterceptor() {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true

  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input, init = {}) => {
    let url = ''
    if (typeof input === 'string') url = input
    else if (input && typeof input.url === 'string') url = input.url

    // Только для /api/* — не трогаем внешние fetch.
    const isApiCall = url.startsWith('/api/') || url.includes('/api/')
    if (!isApiCall) {
      return originalFetch(input, init)
    }

    const slug = getCurrentProject()
    if (!slug) {
      return originalFetch(input, init)
    }

    // Не перезаписываем, если пользователь явно указал заголовок.
    const headers = new Headers(init.headers || {})
    if (!headers.has('X-Admin-Project')) {
      headers.set('X-Admin-Project', slug)
    }
    return originalFetch(input, { ...init, headers })
  }
}
