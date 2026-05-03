import { computed, ref, toValue } from 'vue'

/**
 * Приведение значений из accessor к виду, удобному для сравнения.
 * @param {unknown} a
 * @param {unknown} b
 */
export function compareSortable(a, b) {
  const na = normalizeNumber(a)
  const nb = normalizeNumber(b)
  if (na != null && nb != null) return na - nb
  const ta = normalizeTime(a)
  const tb = normalizeTime(b)
  if (ta != null && tb != null) return ta - tb
  const sa = normalizeString(a)
  const sb = normalizeString(b)
  return sa.localeCompare(sb, 'ru', { sensitivity: 'base', numeric: true })
}

function normalizeNumber(v) {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

function normalizeTime(v) {
  if (v instanceof Date && Number.isFinite(v.getTime())) return v.getTime()
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v) {
    const t = Date.parse(v)
    if (Number.isFinite(t)) return t
  }
  return null
}

function normalizeString(v) {
  if (v == null) return ''
  return String(v)
}

/**
 * Клиентская сортировка строк таблицы по выбранному столбцу.
 *
 * @template T
 * @param {import('vue').MaybeRefOrGetter<T[]>} sourceRows
 * @param {Record<string, (row: T) => unknown>} accessors
 * @param {string} [defaultKey]
 */
export function useTableSort(sourceRows, accessors, defaultKey = '') {
  const sortKey = ref(
    defaultKey && accessors[defaultKey] ? defaultKey : Object.keys(accessors)[0] || '',
  )
  const sortDir = ref(/** @type {'asc' | 'desc'} */ ('asc'))

  function toggleSort(key) {
    if (!key || !accessors[key]) return
    if (sortKey.value === key) {
      sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDir.value = 'asc'
    }
  }

  const sortedRows = computed(() => {
    const rows = [...(toValue(sourceRows) ?? [])]
    const key = sortKey.value
    const fn = accessors[key]
    if (!fn || rows.length < 2) return rows
    const mult = sortDir.value === 'asc' ? 1 : -1
    return rows.sort((a, b) => mult * compareSortable(fn(a), fn(b)))
  })

  return { sortKey, sortDir, sortedRows, toggleSort }
}
