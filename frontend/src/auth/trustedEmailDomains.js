/**
 * Доверенные почтовые домены для регистрации и привязки нового email.
 * Список должен совпадать с backend/app/domain/auth/trusted_email_domains.py.
 */
export const TRUSTED_EMAIL_DOMAINS = new Set([
  // Google
  'gmail.com',
  'googlemail.com',
  // Yandex
  'yandex.ru',
  'yandex.com',
  'yandex.by',
  'yandex.kz',
  'ya.ru',
  // Mail.ru Group
  'mail.ru',
  'inbox.ru',
  'list.ru',
  'bk.ru',
  'internet.ru',
  'xmail.ru',
  // Microsoft
  'outlook.com',
  'hotmail.com',
  'live.com',
  'msn.com',
  // Apple
  'icloud.com',
  'me.com',
  'mac.com',
  // Proton
  'proton.me',
  'protonmail.com',
  'pm.me',
  // Rambler
  'rambler.ru',
  'lenta.ru',
  'ro.ru',
  'autorambler.ru',
  'myrambler.ru',
  // Прочие крупные
  'gmx.com',
  'gmx.net',
  'yahoo.com',
  'tuta.com',
  'tuta.io',
  'tutamail.com',
])

export const UNTRUSTED_EMAIL_DOMAIN_ERROR =
  'Регистрация доступна только с почты доверенных сервисов'

export function emailDomain(email) {
  const normalized = typeof email === 'string' ? email.trim().toLowerCase() : ''
  const at = normalized.lastIndexOf('@')
  if (at < 1 || at === normalized.length - 1) return ''
  return normalized.slice(at + 1)
}

export function isTrustedEmailDomain(email) {
  const domain = emailDomain(email)
  return Boolean(domain) && TRUSTED_EMAIL_DOMAINS.has(domain)
}
