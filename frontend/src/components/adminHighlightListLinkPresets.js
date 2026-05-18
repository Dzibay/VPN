export const ADMIN_HIGHLIGHT_LIST_PRESETS = {
  users: {
    path: '/admin/users/analytics',
    title: 'Открыть этого пользователя в списке клиентов',
    ariaLabel: 'Перейти к пользователю в таблице клиентов',
  },
  referrals: {
    path: '/admin/referrals',
    title: 'Открыть эту запись в списке реферальных ссылок',
    ariaLabel: 'Перейти к реферальной ссылке в таблице токенов',
  },
}

export const ADMIN_HIGHLIGHT_LIST_KEYS = Object.keys(ADMIN_HIGHLIGHT_LIST_PRESETS)
