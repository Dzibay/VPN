/**
 * Локальное хранилище staff-JWT (отдельно от cabinet-JWT публичного фронта).
 * Ключ ``STAFF_JWT`` — не конфликтует с ``vpn_access_token`` публичной части.
 *
 * Bridge с legacy-фронтом: staff-JWT дополнительно копируется в
 * ``vpn_access_token`` + ``vpn_session_role``, чтобы @legacy-views (админские view
 * из основного frontend/) работали без переписывания — их fetchJson читает токен
 * оттуда, а бэкенд теперь принимает staff-JWT в require_roles (см. decode_access_token,
 * маппинг super_admin/admin → 'admin', manager → 'manager').
 */
const KEY = 'STAFF_JWT'
const PROFILE_KEY = 'STAFF_PROFILE'
const PROJECT_KEY = 'STAFF_CURRENT_PROJECT'

// Ключи в legacy-фронте (см. frontend/src/auth/session.js).
const LEGACY_TOKEN_KEY = 'vpn_access_token'
const LEGACY_ROLE_KEY = 'vpn_session_role'

function _syncLegacy(token, role) {
  try {
    if (token) localStorage.setItem(LEGACY_TOKEN_KEY, token)
    else localStorage.removeItem(LEGACY_TOKEN_KEY)
    // super_admin/admin → 'admin' (полный доступ), manager → 'manager'.
    const legacyRole = role === 'manager' ? 'manager' : 'admin'
    localStorage.setItem(LEGACY_ROLE_KEY, legacyRole)
  } catch (_) { /* ignore */ }
}

export function setStaffSession(token, profile) {
  try {
    localStorage.setItem(KEY, token)
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile || null))
  } catch (_) { /* ignore quota */ }
  _syncLegacy(token, profile?.role)
}

export function getStaffToken() {
  try { return localStorage.getItem(KEY) || null } catch (_) { return null }
}

export function hasStaffToken() {
  return !!getStaffToken()
}

export function getStaffProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch (_) { return null }
}

export function clearStaffSession() {
  try {
    localStorage.removeItem(KEY)
    localStorage.removeItem(PROFILE_KEY)
    localStorage.removeItem(PROJECT_KEY)
    // Также чистим legacy-слот, чтобы @legacy-views не думали, что мы «залогинены».
    localStorage.removeItem(LEGACY_TOKEN_KEY)
    localStorage.removeItem(LEGACY_ROLE_KEY)
  } catch (_) { /* ignore */ }
}

/** Восстановление bridge после reload — вызывается один раз в main.js. */
export function rehydrateLegacyBridge() {
  const token = getStaffToken()
  const profile = getStaffProfile()
  if (token) _syncLegacy(token, profile?.role)
}

/**
 * Slug текущего проекта в UI (или строка "__all__" в режиме «Все проекты»).
 * Отправляется в заголовке X-Admin-Project.
 */
export function getCurrentProject() {
  try { return localStorage.getItem(PROJECT_KEY) || null } catch (_) { return null }
}

export function setCurrentProject(slug) {
  try {
    if (!slug) localStorage.removeItem(PROJECT_KEY)
    else localStorage.setItem(PROJECT_KEY, slug)
  } catch (_) { /* ignore */ }
}
