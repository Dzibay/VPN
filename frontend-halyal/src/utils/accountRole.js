/** Значение роли для title и классов */
export function normalizeAccountRole(role) {
  if (role === 'manager' || role === 'admin') return role
  return 'client'
}

export function accountRoleLabel(role) {
  const r = normalizeAccountRole(role)
  if (r === 'admin') return 'Админ'
  if (r === 'manager') return 'Менеджер'
  return 'Клиент'
}
