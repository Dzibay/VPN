/**
 * Форматирование объёма трафика для UI.
 *
 * В API и БД (`traffic_*_bytes`, `user_server_traffic`) хранятся **байты** (8 бит),
 * как в ответе Xray statsquery — не путать с битами.
 *
 * Шкала как у большинства VPN-клиентов: степени **1024** (КиБ / МиБ / ГиБ).
 */

const K = 1024
const M = K * K
const G = K * K * K

/**
 * @param {number} n
 * @param {'decimal' | 'whole'} mode
 */
function formatTrafficScale(n, mode) {
  if (n < K) return `${n} Б`
  if (n < M) {
    return mode === 'whole'
      ? `${Math.round(n / K)} КиБ`
      : `${(n / K).toFixed(1)} КиБ`
  }
  if (n < G) {
    return mode === 'whole'
      ? `${Math.round(n / M)} МиБ`
      : `${(n / M).toFixed(2)} МиБ`
  }
  return mode === 'whole'
    ? `${Math.round(n / G)} ГиБ`
    : `${(n / G).toFixed(2)} ГиБ`
}

/**
 * @param {unknown} byteCount
 * @param {'decimal' | 'whole'} mode
 */
function formatTrafficBytesInternal(byteCount, mode) {
  const x = Number(byteCount)
  if (!Number.isFinite(x) || x < 0) return '—'
  return formatTrafficScale(Math.floor(x), mode)
}

/**
 * @param {unknown} byteCount
 * @returns {string}
 */
export function formatTrafficBytes(byteCount) {
  return formatTrafficBytesInternal(byteCount, 'decimal')
}

/**
 * Тот же масштаб 1024, но без дробной части (для таблиц админки: «0 Б / 20 ГиБ»).
 *
 * @param {unknown} byteCount
 * @returns {string}
 */
export function formatTrafficBytesWhole(byteCount) {
  return formatTrafficBytesInternal(byteCount, 'whole')
}

/**
 * Накопленный трафик и персональный лимит (``traffic_limit_bytes``).
 * Без лимита (null) — только использовано.
 *
 * @param {unknown} usedBytes
 * @param {unknown} limitBytes
 * @returns {string}
 */
export function formatTrafficWithLimit(usedBytes, limitBytes) {
  const used = formatTrafficBytesWhole(usedBytes)
  if (limitBytes == null || limitBytes === '') return used
  const limitNum = Number(limitBytes)
  if (!Number.isFinite(limitNum) || limitNum < 0) return used
  return `${used} / ${formatTrafficBytesWhole(limitNum)}`
}

/**
 * @param {{ total_traffic_bytes?: unknown; traffic_limit_bytes?: unknown | null }} user
 * @returns {boolean}
 */
export function isTrafficOverLimit(user) {
  const limit = user?.traffic_limit_bytes
  if (limit == null || limit === '') return false
  const limitNum = Number(limit)
  const used = Number(user?.total_traffic_bytes) || 0
  return Number.isFinite(limitNum) && limitNum >= 0 && used >= limitNum
}
