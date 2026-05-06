import { computed, nextTick, reactive, ref, watch } from 'vue'
import { rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { fetchJson } from '../api/client.js'

/**
 * @typedef {'day' | 'hour'} StatsGranularity
 * @typedef {{ stats_date: string | null; period_start_utc?: string | null; users_count: number; users_with_traffic_count?: number; active_users_count?: number; subscription_devices_users_count?: number }} DailyStatsRow
 */

/** Полночь текущего календарного дня UTC (YYYY-MM-DD). */
export function utcTodayIso() {
  const d = new Date()
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Подпись календарного дня UTC (YYYY-MM-DD). */
export function formatDayShort(iso) {
  if (iso == null || iso === '') return '—'
  try {
    const s = String(iso).slice(0, 10)
    return new Date(s + 'T12:00:00Z').toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return String(iso)
  }
}

/** Почасовая метка: значение из API (UTC), подпись в Москве (как в JSON ответа). */
export function formatHourShortMsk(isoOrTs) {
  if (isoOrTs == null || isoOrTs === '') return '—'
  try {
    return (
      new Date(isoOrTs).toLocaleString('ru-RU', {
        timeZone: 'Europe/Moscow',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }) + ' МСК'
    )
  } catch {
    return String(isoOrTs)
  }
}

/** @deprecated используйте formatHourShortMsk */
export const formatHourShortUtc = formatHourShortMsk

function isUndatedRow(r) {
  const noDate = r.stats_date == null || r.stats_date === ''
  const noPeriod =
    r.period_start_utc == null || r.period_start_utc === ''
  return noDate && noPeriod
}

function hasChartBucket(r, gran) {
  if (gran === 'hour') {
    return r.period_start_utc != null && r.period_start_utc !== ''
  }
  return r.stats_date != null && r.stats_date !== ''
}

function bucketSortKey(r, gran) {
  if (gran === 'hour') {
    const s = r.period_start_utc
    if (s == null || s === '') return null
    const ms = utcHourFloorMs(Date.parse(s))
    return Number.isFinite(ms) ? new Date(ms).toISOString() : null
  }
  const d = r.stats_date
  if (d == null || d === '') return null
  return String(d).slice(0, 10)
}

/** Начало календарного дня UTC по строке YYYY-MM-DD (мс). */
function utcDayStartMs(isoDay) {
  const s = String(isoDay).slice(0, 10)
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return NaN
  return Date.UTC(y, m - 1, d)
}

/** YYYY-MM-DD для момента UTC (полночь этого календарного дня). */
function formatUtcDayIso(ms) {
  const x = new Date(ms)
  const y = x.getUTCFullYear()
  const mo = String(x.getUTCMonth() + 1).padStart(2, '0')
  const day = String(x.getUTCDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
}

/** Полночь часа UTC для метки времени (мс). */
function utcHourFloorMs(ms) {
  const d = new Date(ms)
  return Date.UTC(
    d.getUTCFullYear(),
    d.getUTCMonth(),
    d.getUTCDate(),
    d.getUTCHours(),
    0,
    0,
    0,
  )
}

/**
 * Достраивает календарные дни UTC между первым и последним бакетом.
 * @param {Array<{ iso: string; periodStart: string | null; dayUsers: number; dayTraffic: number; dayActive: number; dayDevices: number }>} sortedRows
 */
function densifyUtcDays(sortedRows) {
  if (!sortedRows.length) return sortedRows
  const map = new Map(
    sortedRows.map((r) => [String(r.iso).slice(0, 10), r]),
  )
  const minMs = utcDayStartMs(sortedRows[0].iso)
  const maxMs = utcDayStartMs(sortedRows[sortedRows.length - 1].iso)
  if (!Number.isFinite(minMs) || !Number.isFinite(maxMs) || minMs > maxMs) {
    return sortedRows
  }
  const out = []
  for (let ms = minMs; ms <= maxMs; ms += 86400000) {
    const iso = formatUtcDayIso(ms)
    const row = map.get(iso)
    out.push(
      row ?? {
        iso,
        periodStart: null,
        dayUsers: 0,
        dayTraffic: 0,
        dayActive: 0,
        dayDevices: 0,
      },
    )
  }
  return out
}

/**
 * Общая загрузка `/api/users/daily-stats` и расчёт данных для `AdminLineChartPanel`
 * (страница «Статистика по дням» и график на «Воронке» — только утилиты формата даты).
 */
export function useUsersDailyStatsChart() {
  /** @type {import('vue').Ref<StatsGranularity>} */
  const granularity = ref('day')

  /** Календарный день UTC для почасового графика (YYYY-MM-DD). */
  const hourDayUtc = ref(utcTodayIso())

  /** @type {import('vue').Ref<DailyStatsRow[]>} */
  const rows = ref([])
  const loading = ref(false)
  const error = ref(null)

  watch(granularity, () => {
    void load()
  })

  watch(hourDayUtc, () => {
    if (granularity.value === 'hour') void load()
  })

  /** Явная смена режима (не деструктурировать ``granularity`` из композабла — потеряется реактивность). */
  function setGranularity(g) {
    granularity.value = g
  }

  const undatedCount = computed(() => {
    const row = rows.value.find((r) => isUndatedRow(r))
    return row ? Number(row.users_count) || 0 : 0
  })

  const undatedTrafficCount = computed(() => {
    const row = rows.value.find((r) => isUndatedRow(r))
    return row ? Number(row.users_with_traffic_count) || 0 : 0
  })

  const chartPoints = computed(() => {
    const gran = granularity.value
    const extraUsers = undatedCount.value
    const extraTraffic = undatedTrafficCount.value
    const sorted = rows.value
      .filter((r) => hasChartBucket(r, gran))
      .map((r) => ({
        iso: bucketSortKey(r, gran),
        periodStart: gran === 'hour' ? r.period_start_utc : null,
        dayUsers: Number(r.users_count) || 0,
        dayTraffic: Number(r.users_with_traffic_count) || 0,
        dayActive: Number(r.active_users_count) || 0,
        dayDevices: Number(r.subscription_devices_users_count) || 0,
      }))
      .filter((row) => row.iso != null)
      .sort((a, b) => String(a.iso).localeCompare(String(b.iso)))

    const dense =
      gran === 'hour' ? sorted : densifyUtcDays(sorted)

    /* Почасовой API отдаёт уже накопительные итоги на конец часа (все пользователи до этого момента). */
    if (gran === 'hour') {
      return dense.map((row) => ({
        iso: row.iso,
        periodStart: row.periodStart,
        dayUsers: row.dayUsers,
        dayTraffic: row.dayTraffic,
        dayActive: row.dayActive,
        dayDevices: row.dayDevices,
        cumDatedUsers: row.dayUsers,
        cumDatedTraffic: row.dayTraffic,
        cumDatedDevices: row.dayDevices,
        totalUsers: row.dayUsers + extraUsers,
        totalTraffic: row.dayTraffic + extraTraffic,
        totalDevices: row.dayDevices,
      }))
    }

    let cumDatedUsers = 0
    let cumDatedTraffic = 0
    let cumDatedDevices = 0
    return dense.map((row) => {
      cumDatedUsers += row.dayUsers
      cumDatedTraffic += row.dayTraffic
      cumDatedDevices += row.dayDevices
      return {
        iso: row.iso,
        periodStart: row.periodStart,
        dayUsers: row.dayUsers,
        dayTraffic: row.dayTraffic,
        dayActive: row.dayActive,
        dayDevices: row.dayDevices,
        cumDatedUsers,
        cumDatedTraffic,
        cumDatedDevices,
        totalUsers: cumDatedUsers + extraUsers,
        totalTraffic: cumDatedTraffic + extraTraffic,
        totalDevices: cumDatedDevices,
      }
    })
  })

  const totalUsers = computed(() => {
    if (granularity.value === 'hour') {
      let mx = 0
      for (const r of rows.value) {
        if (!hasChartBucket(r, 'hour')) continue
        mx = Math.max(mx, Number(r.users_count) || 0)
      }
      return mx + undatedCount.value
    }
    return rows.value.reduce((acc, r) => acc + (Number(r.users_count) || 0), 0)
  })

  const totalWithTraffic = computed(() => {
    if (granularity.value === 'hour') {
      let mx = 0
      for (const r of rows.value) {
        if (!hasChartBucket(r, 'hour')) continue
        mx = Math.max(mx, Number(r.users_with_traffic_count) || 0)
      }
      return mx + undatedTrafficCount.value
    }
    return rows.value.reduce(
      (acc, r) => acc + (Number(r.users_with_traffic_count) || 0),
      0,
    )
  })

  const totalWithSubscriptionDevices = computed(() => {
    if (granularity.value === 'hour') {
      let mx = 0
      for (const r of rows.value) {
        if (!hasChartBucket(r, 'hour')) continue
        mx = Math.max(mx, Number(r.subscription_devices_users_count) || 0)
      }
      return mx
    }
    return rows.value
      .filter((r) => hasChartBucket(r, granularity.value))
      .reduce(
        (acc, r) => acc + (Number(r.subscription_devices_users_count) || 0),
        0,
      )
  })

  /** Значение «активных за день» для текущего календарного дня UTC (только режим по дням). */
  const activeUsersWidget = computed(() => {
    if (granularity.value === 'hour' || loading.value || error.value) {
      return { today: '—' }
    }
    const row = rows.value.find((r) => String(r.stats_date) === utcTodayIso())
    const todayVal = row ? Number(row.active_users_count) || 0 : 0
    return {
      today: todayVal.toLocaleString('ru-RU'),
    }
  })

  function pluralRuDays(n) {
    const k = Math.abs(Math.trunc(Number(n))) % 100
    const d = k % 10
    if (k > 10 && k < 20) return 'дней'
    if (d === 1) return 'день'
    if (d >= 2 && d <= 4) return 'дня'
    return 'дней'
  }

  function pluralRuHours(n) {
    const k = Math.abs(Math.trunc(Number(n))) % 100
    const d = k % 10
    if (k > 10 && k < 20) return 'часов'
    if (d === 1) return 'час'
    if (d >= 2 && d <= 4) return 'часа'
    return 'часов'
  }

  function pluralRuBuckets(n, gran) {
    return gran === 'hour' ? pluralRuHours(n) : pluralRuDays(n)
  }

  const bucketAxisLabel = computed(() =>
    granularity.value === 'hour' ? 'Часов на графике' : 'Дней на графике',
  )

  const chartAriaLabel = computed(() =>
    granularity.value === 'hour'
      ? `По часам UTC за ${formatDayShort(hourDayUtc.value)} (подписи времени — МСК): накопление регистраций и первых подключений устройств`
      : 'По дням UTC: накопление регистраций и клиентов с устройствами, активные по трафику',
  )

  function fmtRu(n) {
    return Number(n).toLocaleString('ru-RU')
  }

  function fmtDeltaRu(n) {
    const v = Number(n) || 0
    if (v > 0) return `+${fmtRu(v)}`
    if (v < 0) return fmtRu(v)
    return '0'
  }

  const registrationChartLabels = computed(() =>
    chartPoints.value.map((p) =>
      granularity.value === 'hour'
        ? formatHourShortMsk(p.periodStart || p.iso)
        : formatDayShort(p.iso),
    ),
  )

  const activeSkyRgb = [56, 189, 248]
  const deviceVioletRgb = [167, 139, 250]

  const registrationChartDatasets = computed(() => {
    const pts = chartPoints.value
    const accentRgb = rgbTupleFromVar('--accent', '#58d68d')
    const trafficOrange = [251, 146, 60]
    const registrationsDs = {
      label: 'Всего пользователей · накопительно',
      data: pts.map((p) => p.totalUsers),
      rgb: accentRgb,
    }
    const trafficDs = {
      label: 'С трафиком · накопительно',
      data: pts.map((p) => p.totalTraffic),
      rgb: trafficOrange,
    }
    const devicesDs = {
      label: 'С подключением (устройства) · накопительно',
      data: pts.map((p) => p.totalDevices),
      rgb: deviceVioletRgb,
    }
    if (granularity.value === 'hour') {
      return [registrationsDs, devicesDs]
    }
    return [
      registrationsDs,
      trafficDs,
      devicesDs,
      {
        label: 'Активные · за день',
        data: pts.map((p) => p.dayActive),
        rgb: activeSkyRgb,
        filled: false,
      },
    ]
  })

  function registrationTooltipTitle(i) {
    const p = chartPoints.value[i]
    if (!p) return ''
    return granularity.value === 'hour'
      ? formatHourShortMsk(p.periodStart || p.iso)
      : formatDayShort(p.iso)
  }

  function registrationTooltipLabel(ctx) {
    const gran = granularity.value
    const i = ctx.dataIndex
    const pts = chartPoints.value
    const p = pts[i]
    if (!p) return ''
    const und = undatedCount.value
    const undT = undatedTrafficCount.value
    const stepWord = gran === 'hour' ? 'часа' : 'дня'

    if (gran === 'hour') {
      if (ctx.datasetIndex === 0) {
        const prevUsers = i > 0 ? pts[i - 1].totalUsers : und
        const dUsers = p.totalUsers - prevUsers
        return [
          `Пользователи: ${fmtRu(p.totalUsers)}`,
          `Без даты регистрации: ${fmtRu(und)}`,
          `Прирост с предыдущего ${stepWord}: ${fmtDeltaRu(dUsers)}`,
        ]
      }
      if (ctx.datasetIndex === 1) {
        const prevDev = i > 0 ? pts[i - 1].totalDevices : 0
        const dDev = p.totalDevices - prevDev
        return [
          `С подключением (записи устройств): ${fmtRu(p.totalDevices)}`,
          `Прирост с предыдущего ${stepWord}: ${fmtDeltaRu(dDev)}`,
        ]
      }
      return []
    }

    const prevUsers = i > 0 ? pts[i - 1].totalUsers : und
    const prevTraffic = i > 0 ? pts[i - 1].totalTraffic : undT
    const dUsers = p.totalUsers - prevUsers
    const dTraffic = p.totalTraffic - prevTraffic

    if (ctx.datasetIndex === 0) {
      return [
        `Пользователи: ${fmtRu(p.totalUsers)}`,
        `Без даты регистрации: ${fmtRu(und)}`,
        `Прирост с предыдущего ${stepWord}: ${fmtDeltaRu(dUsers)}`,
      ]
    }
    if (ctx.datasetIndex === 1) {
      return [
        `С трафиком: ${fmtRu(p.totalTraffic)}`,
        `Без даты регистрации: ${fmtRu(undT)}`,
        `Прирост с предыдущего ${stepWord}: ${fmtDeltaRu(dTraffic)}`,
      ]
    }
    if (ctx.datasetIndex === 2) {
      const prevDev = i > 0 ? pts[i - 1].totalDevices : 0
      const dDev = p.totalDevices - prevDev
      return [
        `С подключением (записи устройств): ${fmtRu(p.totalDevices)}`,
        `Прирост с предыдущего ${stepWord}: ${fmtDeltaRu(dDev)}`,
      ]
    }
    const prevA = i > 0 ? pts[i - 1].dayActive : 0
    const dA = p.dayActive - prevA
    return [
      `Активных за день: ${fmtRu(p.dayActive)}`,
      `К предыдущему дню: ${fmtDeltaRu(dA)}`,
    ]
  }

  async function load() {
    loading.value = true
    error.value = null
    try {
      const g = granularity.value
      let url = `/api/users/daily-stats?granularity=${encodeURIComponent(g)}`
      if (g === 'hour') {
        let day = String(hourDayUtc.value ?? '').trim().slice(0, 10)
        if (!day) {
          day = utcTodayIso()
          hourDayUtc.value = day
        }
        url += `&hour_day=${encodeURIComponent(day)}`
      }
      const data = await fetchJson(url)
      rows.value = Array.isArray(data.stats_by_date) ? data.stats_by_date : []
    } catch (e) {
      error.value = e.message || String(e)
      rows.value = []
    } finally {
      loading.value = false
    }
    await nextTick()
  }

  return reactive({
    granularity,
    hourDayUtc,
    setGranularity,
    rows,
    loading,
    error,
    load,
    undatedCount,
    undatedTrafficCount,
    chartPoints,
    totalUsers,
    totalWithTraffic,
    totalWithSubscriptionDevices,
    activeUsersWidget,
    pluralRuDays,
    pluralRuBuckets,
    bucketAxisLabel,
    chartAriaLabel,
    registrationChartLabels,
    registrationChartDatasets,
    registrationTooltipTitle,
    registrationTooltipLabel,
  })
}
