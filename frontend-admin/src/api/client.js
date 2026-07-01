/**
 * Простой fetch-обёртка: staff-JWT + X-Admin-Project.
 * `unauthenticated_ok` — не редиректить на login (нужно для самой страницы login).
 */
import {
  clearStaffSession,
  getCurrentProject,
  getStaffToken,
} from '../auth/staffSession.js'

async function parseBody(res) {
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    try { return await res.json() } catch (_) { return null }
  }
  return await res.text().catch(() => null)
}

export async function apiFetch(path, options = {}) {
  const {
    method = 'GET',
    body,
    headers = {},
    unauthenticatedOk = false,
    withProject = true,
  } = options

  const token = getStaffToken()
  const finalHeaders = { Accept: 'application/json', ...headers }
  if (token) finalHeaders.Authorization = `Bearer ${token}`
  if (withProject) {
    const slug = getCurrentProject()
    if (slug) finalHeaders['X-Admin-Project'] = slug
  }

  let payload = body
  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const res = await fetch(path, { method, headers: finalHeaders, body: payload })
  const data = await parseBody(res)
  if (!res.ok) {
    if (res.status === 401 && !unauthenticatedOk) {
      clearStaffSession()
      if (typeof window !== 'undefined') {
        const path = window.location.pathname
        if (path !== '/login') window.location.replace('/login')
      }
    }
    const detail = (data && (data.detail || data.message)) || res.statusText || 'Ошибка'
    const err = new Error(String(detail))
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}
