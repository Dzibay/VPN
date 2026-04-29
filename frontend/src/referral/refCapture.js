/**
 * Реферал с сайта: ?ref= в URL → localStorage до регистрации + один учёт клика на бэкенде.
 */
import { fetchJson } from '../api/client.js'

const PENDING_KEY = 'vpn_pending_referral_token'
const CLICK_SENT_PREFIX = 'vpn_ref_click_sent_'

/**
 * Вызывать из router.afterEach: сохранить токен и отправить POST /api/referral/track-click один раз на браузер.
 */
export function captureReferralFromRoute(route) {
  if (typeof window === 'undefined') return
  const raw = route.query?.ref
  const ref =
    typeof raw === 'string'
      ? raw.trim()
      : Array.isArray(raw)
        ? String(raw[0] ?? '').trim()
        : ''
  if (!ref) return

  try {
    window.localStorage.setItem(PENDING_KEY, ref)
  } catch {
    /* ignore quota */
  }

  const dedupe = CLICK_SENT_PREFIX + ref
  try {
    if (window.localStorage.getItem(dedupe)) return
    window.localStorage.setItem(dedupe, '1')
  } catch {
    /* если dedupe не удалось — всё равно пробуем учёт клика раз */
  }

  void fetchJson('/api/referral/track-click', {
    method: 'POST',
    body: JSON.stringify({ token: ref }),
  }).catch(() => {})
}

export function peekPendingReferralToken() {
  if (typeof window === 'undefined') return null
  try {
    const v = window.localStorage.getItem(PENDING_KEY)
    return v?.trim() || null
  } catch {
    return null
  }
}

export function clearPendingReferralToken() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(PENDING_KEY)
  } catch {
    /* ignore */
  }
}
