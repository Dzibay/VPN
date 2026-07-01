/**
 * Единый источник правил доступа для frontend-admin.
 *
 * Роли staff (в profile.role, приходит с /api/staff/auth/login):
 *   - super_admin — полный доступ ко всем проектам + управление проектами/персоналом.
 *   - admin       — все разделы админки в рамках доступных проектов; НЕТ управления
 *                    projects/staff-users/blocked-ips.
 *   - manager     — read-heavy подмножество: дашборд, аналитика клиентов, реферальные
 *                    токены, воронка, задачи, поддержка, SEO, платежи/финансы (view),
 *                    UA-стата, регистрации, логи. НЕТ серверов, доступности, нагрузки,
 *                    трафика, блокировки IP.
 *
 * Значения meta.access у роутов:
 *   - 'staff'            — super_admin | admin | manager
 *   - 'admin'            — super_admin | admin (то, что раньше было admin_only в legacy)
 *   - 'super_admin_only' — только super_admin (управление проектами/персоналом)
 */

/** @typedef {'super_admin' | 'admin' | 'manager'} StaffRole */
/** @typedef {'staff' | 'admin' | 'super_admin_only'} RouteAccess */

/**
 * @param {StaffRole | null | undefined} role
 * @param {RouteAccess} access
 * @returns {boolean}
 */
export function canAccessRoute(role, access) {
  if (!role) return false
  if (access === 'super_admin_only') return role === 'super_admin'
  if (access === 'admin') return role === 'super_admin' || role === 'admin'
  return role === 'super_admin' || role === 'admin' || role === 'manager'
}

/** Куда идти после логина по умолчанию. */
export function defaultRouteForRole(role) {
  return '/dashboard'
}
