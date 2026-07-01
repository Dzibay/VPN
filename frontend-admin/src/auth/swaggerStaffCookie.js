/** Имя cookie совпадает с ``SWAGGER_STAFF_JWT_COOKIE`` в ``app/core/dependencies.py``. */
export const SWAGGER_STAFF_JWT_COOKIE = 'SwaggerStaffJwt'

const MAX_AGE_SECONDS = 900

function cookieSecureTail() {
  return typeof window !== 'undefined' && window.location.protocol === 'https:' ? '; Secure' : ''
}

export function clearStaffSwaggerCookie() {
  if (typeof document === 'undefined') return
  document.cookie = `${SWAGGER_STAFF_JWT_COOKIE}=; Path=/swagger; SameSite=Lax; Max-Age=0${cookieSecureTail()}`
}

/** Cookie Path=/swagger и переход; вызывать из админки перед открытием Swagger UI. */
export function startStaffSwaggerWithToken(token) {
  if (typeof document === 'undefined' || typeof window === 'undefined' || !token) return
  document.cookie = `${SWAGGER_STAFF_JWT_COOKIE}=${encodeURIComponent(token)}; Path=/swagger; SameSite=Lax; Max-Age=${MAX_AGE_SECONDS}${cookieSecureTail()}`
  window.open('/swagger', '_blank', 'noopener,noreferrer')
}
