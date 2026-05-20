/** @param {string | number} userId */
export function adminUserAnalyticsPath(userId) {
  const n = Number(userId)
  if (!Number.isFinite(n) || n < 1) return '/admin/users/analytics'
  return `/admin/users/${Math.floor(n)}/analytics`
}

export const ADMIN_HIGHLIGHT_LIST_PRESETS = {
  users: {
    routeKind: 'userAnalytics',
    title: 'Открыть аналитику пользователя',
    ariaLabel: 'Перейти к аналитике пользователя',
  },
  referrals: {
    routeKind: 'highlightList',
    path: '/admin/referrals',
    title: 'Открыть эту запись в списке реферальных ссылок',
    ariaLabel: 'Перейти к реферальной ссылке в таблице токенов',
  },
}

export const ADMIN_HIGHLIGHT_LIST_KEYS = Object.keys(ADMIN_HIGHLIGHT_LIST_PRESETS)
