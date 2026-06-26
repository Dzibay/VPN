/** Роли из JWT / localStorage (совпадают с ответом POST /api/auth/login). */

export function isAdminRole(role) {
  return role === 'admin'
}

export function canAccessReferralsAdmin(role) {
  return role === 'admin' || role === 'manager'
}

/** Оплата, поддержка, персональная реферальная ссылка в личном кабинете. */
export function canUseCabinetUserFeatures(role) {
  return role === 'user' || canAccessReferralsAdmin(role)
}

/** Куда вести после входа по умолчанию (без учёта query.redirect). */
export function defaultPathAfterLogin(role) {
  if (role === 'admin') return '/admin/summary'
  if (role === 'manager') return '/admin/referrals'
  return '/cabinet'
}
