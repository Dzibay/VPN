/**
 * Центральный список вкладок админки по роли JWT:
 * — admin_only: только роль «admin»
 * — staff: admin или manager (как canAccessReferralsAdmin)
 */

import { isAdminRole, canAccessReferralsAdmin } from '../auth/permissions.js'

/** @typedef {'admin_only' | 'staff'} AdminNavAccess */

/** @type {Array<{ routeName: string, label: string, path: string, access: AdminNavAccess }>} */
export const ADMIN_NAV_DEFINITION = [
  {
    routeName: 'admin-users',
    label: 'Пользователи',
    path: '/admin/users',
    access: 'admin_only',
  },
  {
    routeName: 'admin-servers',
    label: 'Серверы',
    path: '/admin/servers',
    access: 'admin_only',
  },
  {
    routeName: 'admin-subscription-user-agent-stats',
    label: 'Подключения',
    path: '/admin/users/subscription-user-agent-stats',
    access: 'admin_only',
  },
  {
    routeName: 'admin-users-staff-analytics',
    label: 'Клиенты',
    path: '/admin/users/analytics',
    access: 'staff',
  },
  {
    routeName: 'admin-users-registrations-by-date',
    label: 'Статистика по дням',
    path: '/admin/users/registrations-by-date',
    access: 'staff',
  },
  {
    routeName: 'admin-analytics',
    label: 'Нагрузка',
    path: '/admin/analytics',
    access: 'admin_only',
  },
  {
    routeName: 'admin-funnel',
    label: 'Воронка',
    path: '/admin/funnel',
    access: 'staff',
  },
  {
    routeName: 'admin-http-logs',
    label: 'Логи',
    path: '/admin/logs',
    access: 'staff',
  },
  {
    routeName: 'admin-referrals',
    label: 'Реферальные токены',
    path: '/admin/referrals',
    access: 'staff',
  },
]

/**
 * @param {string | null | undefined} role — из JWT ('admin' | 'manager' | 'user')
 */
export function getAdminNavTabsForRole(role) {
  const adminOk = isAdminRole(role)
  const staffOk = canAccessReferralsAdmin(role)

  return ADMIN_NAV_DEFINITION.filter((item) => {
    if (item.access === 'admin_only') return adminOk
    return staffOk
  })
}

/** Подпись nav для доступности и подсказок. */
export function adminNavAriaLabelForRole(role) {
  return role === 'admin' ? 'Разделы админки' : 'Раздел менеджера'
}
