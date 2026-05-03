import { computed, nextTick, ref } from 'vue'
import { rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { fetchJson } from '../api/client.js'

/** @typedef {{ stats_date: string | null; users_count: number; users_with_traffic_count?: number; active_users_count?: number; subscription_devices_users_count?: number }} DailyStatsRow */

export function utcTodayIso() {
  const d = new Date()
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function formatDayShort(iso) {
  if (iso == null || iso === '') return '—'
  try {
    return new Date(iso + 'T12:00:00Z').toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return String(iso)
  }
}

/**
 * Общая загрузка `/api/users/daily-stats` и расчёт данных для `AdminLineChartPanel`
 * (страница «Статистика по дням» и график на «Воронке»).
 */
export function useUsersDailyStatsChart() {
  /** @type {import('vue').Ref<DailyStatsRow[]>} */
  const rows = ref([])
  const loading = ref(false)
  const error = ref(null)

  const undatedCount = computed(() => {
    const row = rows.value.find((r) => r.stats_date == null || r.stats_date === '')
    return row ? Number(row.users_count) || 0 : 0
  })

  const undatedTrafficCount = computed(() => {
    const row = rows.value.find((r) => r.stats_date == null || r.stats_date === '')
    return row ? Number(row.users_with_traffic_count) || 0 : 0
  })

  const chartPoints = computed(() => {
    const extraUsers = undatedCount.value
    const extraTraffic = undatedTrafficCount.value
    const sorted = rows.value
      .filter((r) => r.stats_date != null && r.stats_date !== '')
      .map((r) => ({
        iso: String(r.stats_date),
        dayUsers: Number(r.users_count) || 0,
        dayTraffic: Number(r.users_with_traffic_count) || 0,
        dayActive: Number(r.active_users_count) || 0,
        dayDevices: Number(r.subscription_devices_users_count) || 0,
      }))
      .sort((a, b) => a.iso.localeCompare(b.iso))

    let cumDatedUsers = 0
    let cumDatedTraffic = 0
    let cumDatedDevices = 0
    return sorted.map((row) => {
      cumDatedUsers += row.dayUsers
      cumDatedTraffic += row.dayTraffic
      cumDatedDevices += row.dayDevices
      return {
        iso: row.iso,
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

  const totalUsers = computed(() =>
    rows.value.reduce((acc, r) => acc + (Number(r.users_count) || 0), 0),
  )

  const totalWithTraffic = computed(() =>
    rows.value.reduce(
      (acc, r) => acc + (Number(r.users_with_traffic_count) || 0),
      0,
    ),
  )

  const totalWithSubscriptionDevices = computed(() =>
    rows.value
      .filter((r) => r.stats_date != null && r.stats_date !== '')
      .reduce(
        (acc, r) => acc + (Number(r.subscription_devices_users_count) || 0),
        0,
      ),
  )

  /** Пик «активных за день» на графике и значение за текущий календарный день UTC. */
  const activeUsersWidget = computed(() => {
    if (loading.value || error.value) {
      return { peak: '—', today: '—' }
    }
    const row = rows.value.find((r) => String(r.stats_date) === utcTodayIso())
    const todayVal = row ? Number(row.active_users_count) || 0 : 0
    let peakVal = 0
    for (const p of chartPoints.value) {
      const a = Number(p.dayActive) || 0
      if (a > peakVal) peakVal = a
    }
    return {
      peak: peakVal.toLocaleString('ru-RU'),
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
    chartPoints.value.map((p) => formatDayShort(p.iso)),
  )

  const activeSkyRgb = [56, 189, 248]
  const deviceVioletRgb = [167, 139, 250]

  const registrationChartDatasets = computed(() => {
    const pts = chartPoints.value
    const accentRgb = rgbTupleFromVar('--accent', '#58d68d')
    const trafficOrange = [251, 146, 60]
    return [
      {
        label: 'Всего пользователей · накопительно',
        data: pts.map((p) => p.totalUsers),
        rgb: accentRgb,
      },
      {
        label: 'С трафиком · накопительно',
        data: pts.map((p) => p.totalTraffic),
        rgb: trafficOrange,
      },
      {
        label: 'С подключением (устройства) · накопительно',
        data: pts.map((p) => p.totalDevices),
        rgb: deviceVioletRgb,
      },
      {
        label: 'Активные · за день',
        data: pts.map((p) => p.dayActive),
        rgb: activeSkyRgb,
        filled: false,
      },
    ]
  })

  function registrationTooltipTitle(i) {
    const iso = chartPoints.value[i]?.iso
    return iso ? formatDayShort(iso) : ''
  }

  function registrationTooltipLabel(ctx) {
    const i = ctx.dataIndex
    const pts = chartPoints.value
    const p = pts[i]
    if (!p) return ''
    const und = undatedCount.value
    const undT = undatedTrafficCount.value
    const prevUsers = i > 0 ? pts[i - 1].totalUsers : und
    const prevTraffic = i > 0 ? pts[i - 1].totalTraffic : undT
    const dUsers = p.totalUsers - prevUsers
    const dTraffic = p.totalTraffic - prevTraffic

    if (ctx.datasetIndex === 0) {
      return [
        `Пользователи: ${fmtRu(p.totalUsers)}`,
        `Без даты регистрации: ${fmtRu(und)}`,
        `Прирост с предыдущего дня: ${fmtDeltaRu(dUsers)}`,
      ]
    }
    if (ctx.datasetIndex === 1) {
      return [
        `С трафиком: ${fmtRu(p.totalTraffic)}`,
        `Без даты регистрации: ${fmtRu(undT)}`,
        `Прирост с предыдущего дня: ${fmtDeltaRu(dTraffic)}`,
      ]
    }
    if (ctx.datasetIndex === 2) {
      const prevDev = i > 0 ? pts[i - 1].totalDevices : 0
      const dDev = p.totalDevices - prevDev
      return [
        `С подключением (записи устройств): ${fmtRu(p.totalDevices)}`,
        `Прирост с предыдущего дня: ${fmtDeltaRu(dDev)}`,
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
      const data = await fetchJson('/api/users/daily-stats')
      rows.value = Array.isArray(data.stats_by_date) ? data.stats_by_date : []
    } catch (e) {
      error.value = e.message || String(e)
      rows.value = []
    } finally {
      loading.value = false
    }
    await nextTick()
  }

  return {
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
    registrationChartLabels,
    registrationChartDatasets,
    registrationTooltipTitle,
    registrationTooltipLabel,
  }
}
