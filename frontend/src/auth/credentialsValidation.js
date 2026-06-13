export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 72

export const CREDENTIALS_ERRORS = {
  passwordsMismatch: 'Пароли не совпадают',
  passwordTooShort: `Пароль должен содержать не менее ${PASSWORD_MIN_LENGTH} символов`,
  legalRequired:
    'Необходимо принять условия и дать согласие на обработку данных',
  emailRequired: 'Укажите email',
}

export function normalizeEmailInput(value) {
  return typeof value === 'string' ? value.trim() : ''
}

export function validateEmailInput(value) {
  const email = normalizeEmailInput(value)
  if (!email) return CREDENTIALS_ERRORS.emailRequired
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
