/**
 * Форматирование объёма трафика для UI.
 *
 * В API и БД (`traffic_*_bytes`, `user_server_traffic`) хранятся **байты** (8 бит),
 * как в ответе Xray statsquery — не путать с битами.
 *
 * Шкала: байты → килобайты → мегабайты → гигабайты (десятичные КБ/МБ/ГБ, множитель 1000).
 *
 * @param {unknown} byteCount
 * @returns {string}
 */
export function formatTrafficBytes(byteCount) {
  const x = Number(byteCount)
  if (!Number.isFinite(x) || x < 0) return '—'
  const n = Math.floor(x)

  const K = 1000
  const M = K * K
  const G = K * K * K

  if (n < K) return `${n} Б`
  if (n < M) return `${(n / K).toFixed(1)} КБ`
  if (n < G) return `${(n / M).toFixed(2)} МБ`
  return `${(n / G).toFixed(2)} ГБ`
}
