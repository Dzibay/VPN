import { computed, ref, watch } from 'vue'
import { chartSeriesRgb, rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { fetchJson } from '../api/client.js'
import {
  addCalendarDayIso,
  formatMskCalendarDayShort,
  formatMskHourAxis,
  subtractCalendarDaysIso,
} from '../utils/mskDate.js'

/** @typedef {'hour' | 'day' | 'week' | 'month'} SummaryChartBucket */

/**
 * @param {string} fromIso
 * @param {string} toIso
 */
export function daysBetweenInclusive(fromIso, toIso) {
  const a = Date.parse(`${String(fromIso).slice(0, 10)}T12:00:00+03:00`)
  const b = Date.parse(`${String(toIso).slice(0, 10)}T12:00:00+03:00`)
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return 1
  return Math.floor((b - a) / 86400000) + 1
}

/**
 * @param {string} fromIso
 * @param {string} toIso
 * @returns {{ bucket: SummaryChartBucket; bucketLabel: string }}
 */
export function resolveSummaryChartBucket(fromIso, toIso) {
  const days = daysBetweenInclusive(fromIso, toIso)
  if (days <= 1) {
    return { bucket: 'hour', bucketLabel: 'по часам' }
  }
  if (days <= 62) {
    return { bucket: 'day', bucketLabel: 'по дням' }
  }
  if (days <= 180) {
    return { bucket: 'week', bucketLabel: 'по неделям' }
  }
  return { bucket: 'month', bucketLabel: 'по месяцам' }
}

/**
 * @param {string} fromIso
 * @param {string} toIso
 */
function iterMskDays(fromIso, toIso) {
  const out = []
  let iso = String(fromIso).slice(0, 10)
  const end = String(toIso).slice(0, 10)
  if (!iso || !end || iso > end) return out
  while (iso <= end) {
    out.push(iso)
    if (iso === end) break
    iso = addCalendarDayIso(iso)
  }
  return out
}

/** Понедельник той же недели (календарь YYYY-MM-DD). */
function mskWeekStart(isoDay) {
  const s = String(isoDay).slice(0, 10)
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return s
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
  const daysSinceMon = (wd + 6) % 7
  return subtractCalendarDaysIso(s, daysSinceMon)
}

/**
 * @param {Array<{ key: string; value: number }>} daily
 * @param {(key: string) => string} labelFn
 */
function aggregateDaily(daily, bucketKeyFn, labelFn) {
  /** @type {Map<string, { key: string; value: number; label: string }>} */
  const map = new Map()
  for (const row of daily) {
    const bk = bucketKeyFn(row.key)
    const prev = map.get(bk)
    if (prev) {
      prev.value += row.value
    } else {
      map.set(bk, { key: bk, value: row.value, label: labelFn(bk, row.key) })
    }
  }
  return [...map.values()].sort((a, b) => a.key.localeCompare(b.key))
}

function formatMonthLabel(ym) {
  const [ys, ms] = String(ym).split('-')
  const y = Number(ys)
  const m = Number(ms)
  if (!y || !m || m < 1 || m > 12) return String(ym)
  const d = new Date(Date.UTC(y, m - 1, 1))
  return d.toLocaleDateString('ru-RU', { month: 'short', year: 'numeric', timeZone: 'UTC' })
}

function formatUtcDayLabel(iso) {
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

function parseAmounts(arr) {
  if (!Array.isArray(arr)) return []
  return arr.map((x) => {
    const n = Number(String(x).replace(',', '.'))
    return Number.isFinite(n) ? n : 0
  })
}

function monthOverlapsRange(ym, fromIso, toIso) {
  const start = `${ym}-01`
  const [y, m] = ym.split('-').map(Number)
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate()
  const end = `${y}-${String(m).padStart(2, '0')}-${String(last).padStart(2, '0')}`
  return end >= fromIso && start <= toIso
}

/**
 * @param {import('vue').Ref<{ from: string; to: string }>} rangeRef
 */
export function useAdminSummaryCharts(rangeRef) {
  const loading = ref(false)
  const error = ref(null)

  /** @type {import('vue').Ref<Array<{ key: string; label: string; value: number }>>} */
  const usersPoints = ref([])
  /** @type {import('vue').Ref<Array<{ key: string; label: string; value: number }>>} */
  const revenuePoints = ref([])
  /** @type {import('vue').Ref<SummaryChartBucket>} */
  const bucket = ref(/** @type {SummaryChartBucket} */ ('day'))
  /** @type {import('vue').Ref<string>} */
  const bucketLabel = ref('по дням')

  async function loadUsersSeries(from, to, mode) {
    if (mode === 'hour') {
      const data = await fetchJson(
        `/api/users/daily-stats?granularity=hour&hour_day=${encodeURIComponent(from)}`,
      )
      const rows = Array.isArray(data?.rows) ? data.rows : []
      const sorted = rows
        .filter((r) => r.period_start_utc)
        .slice()
        .sort((a, b) =>
          String(a.period_start_utc).localeCompare(String(b.period_start_utc)),
        )
      let prev = Number(sorted[0]?.hour_baseline_users_count) || 0
      return sorted.map((r) => {
        const cur = Number(r.users_count) || 0
        const value = Math.max(0, cur - prev)
        prev = cur
        return {
          key: String(r.period_start_utc),
          label: formatMskHourAxis(r.period_start_utc),
          value,
        }
      })
    }

    const data = await fetchJson('/api/users/daily-stats?granularity=day')
    const rows = Array.isArray(data?.rows) ? data.rows : []
    /** @type {Map<string, number>} */
    const byDay = new Map()
    for (const r of rows) {
      const d = r.stats_date == null ? '' : String(r.stats_date).slice(0, 10)
      if (d) byDay.set(d, Number(r.users_count) || 0)
    }

    const daily = iterMskDays(from, to).map((iso) => ({
      key: iso,
      label: formatMskCalendarDayShort(iso),
      value: byDay.get(iso) || 0,
    }))

    if (mode === 'day') return daily

    if (mode === 'week') {
      return aggregateDaily(
        daily,
        (iso) => mskWeekStart(iso),
        (weekStart) => {
          const weekEnd = addCalendarDayIso(weekStart, 6)
          return `${formatMskCalendarDayShort(weekStart)} – ${formatMskCalendarDayShort(weekEnd)}`
        },
      )
    }

    return aggregateDaily(
      daily,
      (iso) => iso.slice(0, 7),
      (ym) => formatMonthLabel(ym),
    )
  }

  async function loadRevenueSeries(from, to, mode) {
    if (mode === 'month') {
      const data = await fetchJson('/api/admin/payments/finance-summary?granularity=month')
      const months = Array.isArray(data?.months) ? data.months : []
      const gross = data?.cash_gross ?? data?.cash
      const sub = parseAmounts(gross?.subscription)
      const one = parseAmounts(gross?.one_time)
      return months
        .map((ym, i) => ({
          key: String(ym),
          label: formatMonthLabel(ym),
          value: (sub[i] || 0) + (one[i] || 0),
        }))
        .filter((row) => monthOverlapsRange(row.key, from, to))
    }

    const data = await fetchJson('/api/admin/payments/finance-summary?granularity=day')
    const days = Array.isArray(data?.days) ? data.days : []
    const gross = data?.cash_gross ?? data?.cash
    const sub = parseAmounts(gross?.subscription)
    const one = parseAmounts(gross?.one_time)

    const daily = days.map((day, i) => ({
      key: String(day).slice(0, 10),
      label: formatUtcDayLabel(day),
      value: (sub[i] || 0) + (one[i] || 0),
    }))

    const filtered = daily.filter((r) => r.key >= from && r.key <= to)

    if (mode === 'day' || mode === 'hour') return filtered

    if (mode === 'week') {
      return aggregateDaily(
        filtered,
        (iso) => {
          const [y, m, d] = iso.split('-').map(Number)
          const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
          const daysSinceMon = (wd + 6) % 7
          const t = Date.parse(`${iso}T00:00:00Z`) - daysSinceMon * 86400000
          return new Date(t).toISOString().slice(0, 10)
        },
        (weekStart) => {
          const end = new Date(
            Date.parse(`${weekStart}T00:00:00Z`) + 6 * 86400000,
          )
            .toISOString()
            .slice(0, 10)
          return `${formatUtcDayLabel(weekStart)} – ${formatUtcDayLabel(end)}`
        },
      )
    }

    return aggregateDaily(
      filtered,
      (iso) => iso.slice(0, 7),
      (ym) => formatMonthLabel(ym),
    )
  }

  async function load() {
    const { from, to } = rangeRef.value
    if (!from || !to) return

    loading.value = true
    error.value = null
    try {
      const resolved = resolveSummaryChartBucket(from, to)
      bucket.value = resolved.bucket
      bucketLabel.value = resolved.bucketLabel

      const [users, revenue] = await Promise.all([
        loadUsersSeries(from, to, resolved.bucket),
        loadRevenueSeries(from, to, resolved.bucket),
      ])
      usersPoints.value = users
      revenuePoints.value = revenue
    } catch (e) {
      error.value = e?.message || 'Не удалось загрузить графики'
      usersPoints.value = []
      revenuePoints.value = []
    } finally {
      loading.value = false
    }
  }

  watch(rangeRef, () => void load(), { deep: true })

  const usersLabels = computed(() => usersPoints.value.map((p) => p.label))
  const revenueLabels = computed(() => revenuePoints.value.map((p) => p.label))

  const usersDatasets = computed(() => {
    if (!usersPoints.value.length) return []
    return [
      {
        label: 'Регистрации',
        data: usersPoints.value.map((p) => p.value),
        rgb: rgbTupleFromVar('--accent', '#58d68d'),
        filled: true,
      },
    ]
  })

  const revenueDatasets = computed(() => {
    if (!revenuePoints.value.length) return []
    return [
      {
        label: 'Доход',
        data: revenuePoints.value.map((p) => p.value),
        rgb: chartSeriesRgb.payment,
        borderRadius: 4,
        maxBarThickness: bucket.value === 'day' || bucket.value === 'hour' ? 24 : 48,
      },
    ]
  })

  const usersHasData = computed(() =>
    usersPoints.value.some((p) => p.value > 0),
  )
  const revenueHasData = computed(() =>
    revenuePoints.value.some((p) => p.value > 0),
  )

  const usersHint = computed(() => `Приток пользователей, ${bucketLabel.value} (МСК)`)
  const revenueHint = computed(() => `Валовый доход, ${bucketLabel.value}`)

  const usersAriaLabel = computed(
    () => `Приток пользователей за период, ${bucketLabel.value}, МСК`,
  )
  const revenueAriaLabel = computed(
    () => `Доход за период, ${bucketLabel.value}, валовая сумма, ₽`,
  )

  function formatCountTick(v) {
    const n = Number(v)
    if (!Number.isFinite(n)) return ''
    return n.toLocaleString('ru-RU')
  }

  function formatMoneyTick(v) {
    const n = Number(v)
    if (!Number.isFinite(n)) return ''
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
  }

  /** @param {number} i */
  function usersTooltipTitle(i) {
    const p = usersPoints.value[i]
    return p ? p.label : ''
  }

  /** @param {import('chart.js').TooltipItem<'line'>} ctx */
  function usersTooltipLabel(ctx) {
    return `${ctx.dataset.label}: ${Number(ctx.parsed.y).toLocaleString('ru-RU')}`
  }

  /** @param {import('chart.js').TooltipItem<'bar'>[]} items */
  function revenueTooltipFooter(items) {
    const first = items?.[0]
    if (!first) return ''
    const v = Number(first.raw)
    if (!Number.isFinite(v)) return ''
    return `Всего: ${v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
  }

  return {
    loading,
    error,
    bucket,
    bucketLabel,
    load,
    usersLabels,
    revenueLabels,
    usersDatasets,
    revenueDatasets,
    usersHasData,
    revenueHasData,
    usersHint,
    revenueHint,
    usersAriaLabel,
    revenueAriaLabel,
    formatCountTick,
    formatMoneyTick,
    usersTooltipTitle,
    usersTooltipLabel,
    revenueTooltipFooter,
  }
}
