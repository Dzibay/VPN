import { fetchJson } from '../api/client.js'

let checked = false
let blocked = false

/** Один запрос за сессию вкладки: нужен роутеру для редиректа на /blocked. */
export async function ensureIpBlockStatus() {
  if (checked) return blocked
  try {
    const data = await fetchJson('/api/public/ip-blocked')
    blocked = Boolean(data?.blocked)
  } catch {
    blocked = false
  }
  checked = true
  return blocked
}
