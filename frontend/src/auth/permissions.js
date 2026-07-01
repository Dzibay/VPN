/** Роли из JWT / localStorage (совпадают с ответом POST /api/auth/login). */

export function isAdminRole(role) {
  return role === 'admin'
}

export function canAccessReferralsAdmin(role) {
  return role === 'admin' || role === 'manager'
}

/** Оплата, поддержка, персональная реферальная ссылка в личном кабинете (только клиенты). */
export function canUseCabinetUserFeatures(role) {
  return role === 'user'
}

/**
 * Куда вести после входа по умолчанию (без учёта query.redirect).
 * Внимание: админ-панель теперь на отдельном домене ADMIN_SITE_ADDRESS.
 * Пользователю с ролью admin/manager, зашедшему на публичный сайт, показывается
 * плашка «Админка переехала» в UserLoginView; здесь возвращаем корень.
 */
export function defaultPathAfterLogin(role) {
  if (role === 'admin' || role === 'manager') return '/'
  return '/cabinet'
}
