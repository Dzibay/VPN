import { ref } from 'vue'
import { fetchJson } from '../api/client.js'
import { getAccessToken, getSessionRole } from '../auth/session.js'
import { canUseCabinetUserFeatures } from '../auth/permissions.js'

const unreadCount = ref(0)
/** @type {ReturnType<typeof setInterval> | null} */
let pollTimer = null
let subscriberCount = 0

function isClientSession() {
  return Boolean(getAccessToken()) && canUseCabinetUserFeatures(getSessionRole())
}

export async function refreshClientSupportUnread() {
  if (!isClientSession()) {
    unreadCount.value = 0
    return 0
  }
  try {
    const data = await fetchJson('/api/me/support-messages/unread-count')
    const n = Number(data?.unread_count) || 0
    unreadCount.value = n
    return n
  } catch {
    unreadCount.value = 0
    return 0
  }
}

export function startClientSupportUnreadPolling(intervalMs = 30000) {
  subscriberCount += 1
  if (pollTimer) return
  void refreshClientSupportUnread()
  pollTimer = setInterval(() => {
    void refreshClientSupportUnread()
  }, intervalMs)
}

export function stopClientSupportUnreadPolling() {
  subscriberCount = Math.max(0, subscriberCount - 1)
  if (subscriberCount > 0 || !pollTimer) return
  clearInterval(pollTimer)
  pollTimer = null
}

export function useClientSupportUnread() {
  return {
    unreadCount,
    refreshClientSupportUnread,
    startClientSupportUnreadPolling,
    stopClientSupportUnreadPolling,
  }
}
