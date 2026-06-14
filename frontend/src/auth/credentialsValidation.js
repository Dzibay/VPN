import {
  isTrustedEmailDomain,
  UNTRUSTED_EMAIL_DOMAIN_ERROR,
} from './trustedEmailDomains.js'

export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 72

export const CREDENTIALS_ERRORS = {
  passwordsMismatch: 'Пароли не совпадают',
  passwordTooShort: `Пароль должен содержать не менее ${PASSWORD_MIN_LENGTH} символов`,
  legalRequired:
    'Необходимо принять условия и дать согласие на обработку данных',
  emailRequired: 'Укажите email',
  emailDomainUntrusted: UNTRUSTED_EMAIL_DOMAIN_ERROR,
}

const GMAIL_DOMAINS = new Set(['gmail.com', 'googlemail.com'])

function canonicalizeGmailLocalPart(local) {
  const plusIdx = local.indexOf('+')
  const base = plusIdx === -1 ? local : local.slice(0, plusIdx)
  return base.replace(/\./g, '')
}

/** trim + lower; для Gmail/Googlemail — без «.» в local part и без +alias. */
export function normalizeEmailInput(value) {
  if (typeof value !== 'string') return ''
  const normalized = value.trim().toLowerCase()
  const at = normalized.lastIndexOf('@')
  if (at <= 0) return normalized
  let local = normalized.slice(0, at)
  let domain = normalized.slice(at + 1)
  if (GMAIL_DOMAINS.has(domain)) {
    local = canonicalizeGmailLocalPart(local)
    domain = 'gmail.com'
  }
  return `${local}@${domain}`
}

export function validateEmailInput(value) {
  const email = normalizeEmailInput(value)
  if (!email) return CREDENTIALS_ERRORS.emailRequired
  return null
}

/** Email для регистрации или привязки нового адреса: обязателен и с доверенного домена. */
export function validateRegistrationEmail(value) {
  const requiredErr = validateEmailInput(value)
  if (requiredErr) return requiredErr
  const email = normalizeEmailInput(value)
  if (!isTrustedEmailDomain(email)) {
    return CREDENTIALS_ERRORS.emailDomainUntrusted
  }
  return null
}

export function validateNewPasswordPair(password, passwordConfirm) {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return CREDENTIALS_ERRORS.passwordTooShort
  }
  if (password !== passwordConfirm) {
    return CREDENTIALS_ERRORS.passwordsMismatch
  }
  return null
}

export function validateLegalConsent(accepted) {
  return accepted ? null : CREDENTIALS_ERRORS.legalRequired
}
