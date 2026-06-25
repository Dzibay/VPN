import { computed, nextTick, reactive, ref, watch } from 'vue'
import { chartSeriesRgb, rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { fetchJson } from '../api/client.js'
import {
  addCalendarDayIso,
  formatMskCalendarDayShort,
  formatMskDateTimeShort,
  formatMskHourAxis,
  mskTodayIso,
  subtractCalendarDaysIso,
  utcHourFloorMs,
  utcTodayIso,
} from '../utils/mskDate.js'

/** Сколько последних календарных дней МСК показывать на линейном графике (данные API — за весь срок). */
const CHART_VISIBLE_MSK_DAYS = 30

/**
 * @typedef {'day' | 'hour'} StatsGranularity
 * @typedef {{ stats_date: string | null; period_start_utc?: string | null; users_count: number; users_with_traffic_count?: number; active_users_count?: number; subscription_devices_users_count?: number; users_cumulative_traffic_over_100_mbit_count?: number; persistent_traffic_users_count?: number; users_with_payment_count?: number; active_users_with_payment_count?: number; users_with_active_subscription_count?: number }} DailyStatsRow
 */

/**
 * Метрики по `traffic_date` (UTC): отображаем только полностью завершённые сутки UTC.
 *
 * SQL ``fn_users_daily_stats_compute`` агрегирует трафик по календарным дням МСК,
 * но снимки ``user_server_traffic`` хранятся в UTC. Для дня ``D`` агрегат
 * ``users_cumulative_traffic_over_100_mbit_count`` / ``active_users_count`` и т.п.
 * считается по последнему UTC-снимку ``traffic_date <= D``. Если ``D == utc_today``,
 * день UTC ещё не закончился — снимки за ``traffic_date = utc_today`` накапливаются
 * в течение дня. В МСК (UTC+3) большую часть суток ``msk_today == utc_today``,
 * но в первые 3 часа МСК ``msk_today - 1 == utc_today`` — и тогда «предпоследний»
 * по МСК день оказывается незакрытым по UTC. Чтобы не рисовать частичные значения
 * (видимые как «странный провал»), скрываем и сам ``utc_today``.
 */
function resolveTrafficSnapshotMetric(dayIso, raw, utcCap) {
  const iso = String(dayIso).slice(0, 10)
  const utcToday = String(utcCap || utcTodayIso()).slice(0, 10)
  if (iso >= utcToday) return null
  if (iso >= mskTodayIso()) return null
  if (raw == null) return null
  return Number(raw) || 0
}

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

/**
 * Достраивает календарные дни Europe/Moscow между первым и последним бакетом.
 * @param {Array<{ iso: string; periodStart: string | null; dayUsers: number; dayTraffic: number; dayActive: number; dayDevices: number; dayOver100Mbit: number; dayPersistentTraffic: number; dayPayment: number; dayActiveWithPayment: number; dayActiveSubscription: number }>} sortedRows
 */
function densifyMskDays(sortedRows) {
  if (!sortedRows.length) return sortedRows
  const map = new Map(
    sortedRows.map((r) => [String(r.iso).slice(0, 10), r]),
  )
  let iso = String(sortedRows[0].iso).slice(0, 10)
  const endIso = String(sortedRows[sortedRows.length - 1].iso).slice(0, 10)
  if (!iso || !endIso || iso > endIso) return sortedRows
  const out = []
  while (iso <= endIso) {
    const row = map.get(iso)
    out.push(
      row ?? {
        iso,
        periodStart: null,
        dayUsers: 0,
        dayTraffic: 0,
        dayActive: 0,
        dayDevices: 0,
        dayOver100Mbit: 0,
        dayPersistentTraffic: 0,
        dayPayment: 0,
        dayPaymentsFirst: 0,
        dayPaymentsRepeat: 0,
        dayActiveWithPayment: 0,
        dayActiveSubscription: 0,
      },
    )
    if (iso === endIso) break
    iso = addCalendarDayIso(iso)
  }
  return out
}

/**
 * Общая загрузка `/api/users/daily-stats` и расчёт данных для `AdminLineChartPanel`
 * (страница «Статистика по дням»). Даты/МСК — ``utils/mskDate.js``; бакеты с API.
 */
/**
 * @param {import('vue').Ref<{ from: string; to: string }> | null} [dateRangeRef] — фильтр дней МСК для API
 */
export function useUsersDailyStatsChart(dateRangeRef = null) {
  /** @type {import('vue').Ref<StatsGranularity>} */
  const granularity = ref('day')

  /** Календарный день Москвы для почасового графика (YYYY-MM-DD в запросе hour_day). */
  const hourDayMsk = ref(mskTodayIso())

  /** На начало выбранных суток МСК (для прироста относительно 00:00). */
  const hourBaselineUsers = ref(0)
  const hourBaselineTraffic = ref(0)
  const hourBaselineDevices = ref(0)
  const hourUndatedUsers = ref(0)

  const dayBaselineUsers = ref(0)
  const dayBaselineTraffic = ref(0)
  const dayBaselineDevices = ref(0)
  const dayBaselinePayment = ref(0)

  /** @type {import('vue').Ref<DailyStatsRow[]>} */
  const rows = ref([])
  const trafficUtcToday = ref(/** @type {string | null} */ (null))
  const loading = ref(false)
  const error = ref(null)

  /** Режим «по дням»: все серии кроме регистраций — в % от накопленных пользователей за день. */
  const chartPercentMode = ref(false)

  watch(granularity, (g) => {
    if (g === 'hour') chartPercentMode.value = false
    void load()
  })

  watch(hourDayMsk, () => {
    if (granularity.value === 'hour') void load()
  })

  if (dateRangeRef) {
    watch(dateRangeRef, () => {
      if (granularity.value === 'day') void load()
    }, { deep: true })
  }

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

  const undatedPaymentCount = computed(() => {
    const row = rows.value.find((r) => isUndatedRow(r))
    return row ? Number(row.users_with_payment_count) || 0 : 0
  })

  const allChartPoints = computed(() => {
    const gran = granularity.value
    const extraUsers = undatedCount.value
    const extraTraffic = undatedTrafficCount.value
    const extraPayment = undatedPaymentCount.value
    const sorted = rows.value
      .filter((r) => hasChartBucket(r, gran))
      .map((r) => {
        const iso = bucketSortKey(r, gran)
        return {
        iso,
        periodStart: gran === 'hour' ? r.period_start_utc : null,
        dayUsers: Number(r.users_count) || 0,
        dayTraffic: Number(r.users_with_traffic_count) || 0,
        dayActive: resolveTrafficSnapshotMetric(
          iso,
          r.active_users_count,
          trafficUtcToday.value,
        ),
        dayDevices: Number(r.subscription_devices_users_count) || 0,
        dayOver100Mbit: resolveTrafficSnapshotMetric(
          iso,
          r.users_cumulative_traffic_over_100_mbit_count,
          trafficUtcToday.value,
        ),
        dayPersistentTraffic: resolveTrafficSnapshotMetric(
          iso,
          r.persistent_traffic_users_count,
          trafficUtcToday.value,
        ),
        dayPayment: Number(r.users_with_payment_count) || 0,
        dayPaymentsFirst: Number(r.payments_first_count) || 0,
        dayPaymentsRepeat: Number(r.payments_repeat_count) || 0,
        dayActiveWithPayment: resolveTrafficSnapshotMetric(
          iso,
          r.active_users_with_payment_count,
          trafficUtcToday.value,
        ),
        dayActiveSubscription:
          Number(r.users_with_active_subscription_count) || 0,
      }
      })
      .filter((row) => row.iso != null)
      .sort((a, b) => String(a.iso).localeCompare(String(b.iso)))

    const dense =
      gran === 'hour' ? sorted : densifyMskDays(sorted)

    /* Почасовой API отдаёт уже накопительные итоги на конец часа (все пользователи до этого момента). */
    if (gran === 'hour') {
      /* Почасовой API уже включает пользователей без registered_at; baseline не дублируем. */
      return dense.map((row) => ({
        iso: row.iso,
        periodStart: row.periodStart,
        dayUsers: row.dayUsers,
        dayTraffic: row.dayTraffic,
        dayActive: row.dayActive,
        dayDevices: row.dayDevices,
        dayOver100Mbit: 0,
        dayPersistentTraffic: 0,
        dayPayment: 0,
        dayPaymentsFirst: 0,
        dayPaymentsRepeat: 0,
        dayActiveWithPayment: 0,
        dayActiveSubscription: 0,
        cumDatedUsers: row.dayUsers,
        cumDatedTraffic: row.dayTraffic,
        cumDatedDevices: row.dayDevices,
        cumDatedPayment: 0,
        totalUsers: row.dayUsers,
        totalTraffic: row.dayTraffic,
        totalDevices: row.dayDevices,
        totalPayment: 0,
      }))
    }

    let cumDatedUsers = dayBaselineUsers.value
    let cumDatedTraffic = dayBaselineTraffic.value
    let cumDatedDevices = dayBaselineDevices.value
    let cumDatedPayment = dayBaselinePayment.value
    return dense.map((row) => {
      cumDatedUsers += row.dayUsers
      cumDatedTraffic += row.dayTraffic
      cumDatedDevices += row.dayDevices
      cumDatedPayment += row.dayPayment
      return {
        iso: row.iso,
        periodStart: row.periodStart,
        dayUsers: row.dayUsers,
        dayTraffic: row.dayTraffic,
        dayActive: row.dayActive,
        dayDevices: row.dayDevices,
        dayOver100Mbit: row.dayOver100Mbit,
        dayPersistentTraffic: row.dayPersistentTraffic,
        dayPayment: row.dayPayment,
        dayPaymentsFirst: row.dayPaymentsFirst,
        dayPaymentsRepeat: row.dayPaymentsRepeat,
        dayActiveWithPayment: row.dayActiveWithPayment,
        dayActiveSubscription: row.dayActiveSubscription,
        cumDatedUsers,
        cumDatedTraffic,
        cumDatedDevices,
        cumDatedPayment,
        totalUsers: cumDatedUsers + extraUsers,
        totalTraffic: cumDatedTraffic + extraTraffic,
        totalDevices: cumDatedDevices,
        totalPayment: cumDatedPayment + extraPayment,
      }
    })
  })

  /** Точки для отрисовки: дневной режим — последние 30 суток МСК, накопление уже по полной истории. */
  const chartPoints = computed(() => {
    const pts = allChartPoints.value
    if (granularity.value !== 'day' || !pts.length) return pts
    const endIso = String(pts[pts.length - 1].iso).slice(0, 10)
    const startIso = subtractCalendarDaysIso(endIso, CHART_VISIBLE_MSK_DAYS - 1)
    return pts.filter((p) => String(p.iso).slice(0, 10) >= startIso)
  })

  const totalUsers = computed(() => {
    if (granularity.value === 'hour') {
      let mx = 0
      for (const r of rows.value) {
        if (!hasChartBucket(r, 'hour')) continue
        mx = Math.max(mx, Number(r.users_count) || 0)
      }
      return mx
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
      return mx
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

  const totalWithPayment = computed(() => {
    if (granularity.value === 'hour') {
      return 0
    }
    return rows.value.reduce(
      (acc, r) => acc + (Number(r.users_with_payment_count) || 0),
      0,
    )
  })

  /** Значение «активных за день» для текущего календарного дня МСК (только режим по дням). */
  const activeUsersWidget = computed(() => {
    if (granularity.value === 'hour' || loading.value || error.value) {
      return { today: '—' }
    }
    const row = rows.value.find((r) => String(r.stats_date) === mskTodayIso())
    if (!row || row.active_users_count == null) {
      return { today: '—' }
    }
    const todayVal = Number(row.active_users_count) || 0
    return {
      today: todayVal.toLocaleString('ru-RU'),
    }
  })

  const activeUsersWithPaymentWidget = computed(() => {
    if (granularity.value === 'hour' || loading.value || error.value) {
      return { today: '—' }
    }
    const row = rows.value.find((r) => String(r.stats_date) === mskTodayIso())
    if (!row || row.active_users_with_payment_count == null) {
      return { today: '—' }
    }
    const todayVal = Number(row.active_users_with_payment_count) || 0
    return {
      today: todayVal.toLocaleString('ru-RU'),
    }
  })

  /** Снимок: пользователи с активной подпиской на конец сегодняшнего дня МСК. */
  const activeSubscriptionWidget = computed(() => {
    if (granularity.value === 'hour' || loading.value || error.value) {
      return { today: '—' }
    }
    const row = rows.value.find((r) => String(r.stats_date) === mskTodayIso())
    const todayVal = row
      ? Number(row.users_with_active_subscription_count) || 0
      : 0
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

  const chartAriaLabel = computed(() => {
    if (granularity.value === 'hour') {
      return `По часам за ${formatMskCalendarDayShort(hourDayMsk.value)} (МСК): накопление пользователей и первых подключений устройств`
    }
    if (chartPercentMode.value) {
      return 'По дням МСК: доля от накопленных регистраций — с трафиком, с устройствами, с оплатой, активные, с оплатой активных, >100 Мбит, возвращающиеся активные, с активной подпиской'
    }
    return 'По дням МСК: накопление регистраций и клиентов с устройствами, с оплатой, активные по трафику, активные с оплатой, с активной подпиской (снимок), >100 Мбит накопленного объёма, возвращающиеся активные'
  })

  const chartYTitle = computed(() =>
    granularity.value === 'day' && chartPercentMode.value
      ? '% от регистраций'
      : 'Пользователей',
  )

  function pctOfUsers(value, totalUsers) {
    if (value == null) return null
    const t = Number(totalUsers) || 0
    if (t <= 0) return 0
    return (Number(value) / t) * 100
  }

  function formatChartYTick(v) {
    const n = Number(v)
    if (!Number.isFinite(n)) return ''
    if (granularity.value === 'day' && chartPercentMode.value) {
      return `${n.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`
    }
    return n.toLocaleString('ru-RU')
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

  /** Одна строка тултипа: «Метрика: 12 (+3)». */
  function lineValueDelta(label, value, delta) {
    return [`${label}: ${fmtRu(value)} (${fmtDeltaRu(delta)})`]
  }

  function fmtPct(n) {
    return `${Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`
  }

  function fmtDeltaPct(n) {
    const v = Number(n) || 0
    if (v > 0) return `+${v.toFixed(1)}%`
    if (v < 0) return `${v.toFixed(1)}%`
    return '0%'
  }

  /** Тултип в режиме %: доля и абсолют, прирост в процентных пунктах. */
  function lineValueDeltaPct(label, rawValue, pct, deltaPct) {
    return [
      `${label}: ${fmtPct(pct)} · ${fmtRu(rawValue)} (${fmtDeltaPct(deltaPct)})`,
    ]
  }

  const registrationChartLabels = computed(() =>
    chartPoints.value.map((p) =>
      granularity.value === 'hour'
        ? formatMskHourAxis(p.periodStart || p.iso)
        : formatMskCalendarDayShort(p.iso),
    ),
  )

  const registrationChartDatasets = computed(() => {
    const pts = chartPoints.value
    const accentRgb = rgbTupleFromVar('--accent', '#58d68d')
    const trafficOrange = chartSeriesRgb.traffic
    const percent = granularity.value === 'day' && chartPercentMode.value
    const registrationsDs = {
      label: 'Всего пользователей',
      data: pts.map((p) => p.totalUsers),
      rgb: accentRgb,
    }
    const trafficDs = {
      label: 'С трафиком',
      data: percent
        ? pts.map((p) => pctOfUsers(p.totalTraffic, p.totalUsers))
        : pts.map((p) => p.totalTraffic),
      rgb: trafficOrange,
    }
    const devicesDs = {
      label: 'С подключением устройства',
      data: percent
        ? pts.map((p) => pctOfUsers(p.totalDevices, p.totalUsers))
        : pts.map((p) => p.totalDevices),
      rgb: chartSeriesRgb.device,
    }
    if (granularity.value === 'hour') {
      return [registrationsDs, devicesDs]
    }
    if (percent) {
      return [
        trafficDs,
        devicesDs,
        {
          label: 'С оплатой',
          data: pts.map((p) => pctOfUsers(p.totalPayment, p.totalUsers)),
          rgb: chartSeriesRgb.payment,
        },
        {
          label: 'Активные',
          data: pts.map((p) => pctOfUsers(p.dayActive, p.totalUsers)),
          rgb: chartSeriesRgb.active,
          filled: false,
        },
        {
          label: 'С оплатой активных',
          data: pts.map((p) => pctOfUsers(p.dayActiveWithPayment, p.totalUsers)),
          rgb: chartSeriesRgb.activePay,
          filled: false,
        },
        {
          label: 'С трафиком > 100 Мбит',
          data: pts.map((p) => pctOfUsers(p.dayOver100Mbit, p.totalUsers)),
          rgb: chartSeriesRgb.over100Mbit,
          filled: false,
        },
        {
          label: 'Возвращающиеся активные',
          data: pts.map((p) =>
            pctOfUsers(p.dayPersistentTraffic, p.totalUsers),
          ),
          rgb: chartSeriesRgb.persistent,
          filled: false,
        },
        {
          label: 'С активной подпиской',
          data: pts.map((p) =>
            pctOfUsers(p.dayActiveSubscription, p.totalUsers),
          ),
          rgb: chartSeriesRgb.subscription,
          filled: false,
        },
      ]
    }
    return [
      registrationsDs,
      trafficDs,
      devicesDs,
      {
        label: 'С оплатой',
        data: pts.map((p) => p.totalPayment),
        rgb: chartSeriesRgb.payment,
      },
      {
        label: 'Активные',
        data: pts.map((p) => p.dayActive),
        rgb: chartSeriesRgb.active,
        filled: false,
      },
      {
        label: 'С оплатой активных',
        data: pts.map((p) => p.dayActiveWithPayment),
        rgb: chartSeriesRgb.activePay,
        filled: false,
      },
      {
        label: 'С трафиком > 100 Мбит',
        data: pts.map((p) => p.dayOver100Mbit),
        rgb: chartSeriesRgb.over100Mbit,
        filled: false,
      },
      {
        label: 'Возвращающиеся активные',
        data: pts.map((p) => p.dayPersistentTraffic),
        rgb: chartSeriesRgb.persistent,
        filled: false,
      },
      {
        label: 'С активной подпиской',
        data: pts.map((p) => p.dayActiveSubscription),
        rgb: chartSeriesRgb.subscription,
        filled: false,
      },
    ]
  })

  function registrationTooltipTitle(i) {
    const p = chartPoints.value[i]
    if (!p) return ''
    return granularity.value === 'hour'
      ? formatMskDateTimeShort(p.periodStart || p.iso)
      : formatMskCalendarDayShort(p.iso)
  }

  function registrationTooltipLabel(ctx) {
    const gran = granularity.value
    const i = ctx.dataIndex
    const pts = chartPoints.value
    const p = pts[i]
    if (!p) return ''
    const label = String(ctx.dataset?.label ?? '')

    if (gran === 'hour') {
      if (ctx.datasetIndex === 0) {
        const prevUsers =
          i > 0 ? pts[i - 1].totalUsers : hourBaselineUsers.value
        const dUsers = p.totalUsers - prevUsers
        return lineValueDelta('Пользователи', p.totalUsers, dUsers)
      }
      if (ctx.datasetIndex === 1) {
        const prevDev =
          i > 0 ? pts[i - 1].totalDevices : hourBaselineDevices.value
        const dDev = p.totalDevices - prevDev
        return lineValueDelta(
          'С подключением',
          p.totalDevices,
          dDev,
        )
      }
      return []
    }

    const percent = chartPercentMode.value
    const prev = i > 0 ? pts[i - 1] : null

    if (percent) {
      const base = p.totalUsers
      const prevBase = prev?.totalUsers ?? 0
      if (label === 'С трафиком') {
        const pct = pctOfUsers(p.totalTraffic, base)
        const prevPct = prev
          ? pctOfUsers(prev.totalTraffic, prevBase)
          : 0
        return lineValueDeltaPct(
          'С трафиком',
          p.totalTraffic,
          pct,
          pct - prevPct,
        )
      }
      if (label === 'С подключением устройства') {
        const pct = pctOfUsers(p.totalDevices, base)
        const prevPct = prev
          ? pctOfUsers(prev.totalDevices, prevBase)
          : 0
        return lineValueDeltaPct(
          'С подключением',
          p.totalDevices,
          pct,
          pct - prevPct,
        )
      }
      if (label === 'С оплатой') {
        const pct = pctOfUsers(p.totalPayment, base)
        const prevPct = prev
          ? pctOfUsers(prev.totalPayment, prevBase)
          : 0
        return lineValueDeltaPct(
          'С оплатой',
          p.totalPayment,
          pct,
          pct - prevPct,
        )
      }
      if (label === 'Активные') {
        if (p.dayActive == null) return ['Активных: день ещё не завершён (трафик UTC)']
        const pct = pctOfUsers(p.dayActive, base)
        const prevPct = prev ? pctOfUsers(prev.dayActive, prevBase) : 0
        return lineValueDeltaPct(
          'Активных',
          p.dayActive,
          pct,
          pct - (prevPct ?? 0),
        )
      }
      if (label === 'С оплатой активных') {
        if (p.dayActiveWithPayment == null) {
          return ['С оплатой активных: день ещё не завершён (трафик UTC)']
        }
        const pct = pctOfUsers(p.dayActiveWithPayment, base)
        const prevPct = prev
          ? pctOfUsers(prev.dayActiveWithPayment, prevBase)
          : 0
        return lineValueDeltaPct(
          'С оплатой активных',
          p.dayActiveWithPayment,
          pct,
          pct - prevPct,
        )
      }
      if (label === 'С трафиком > 100 Мбит') {
        if (p.dayOver100Mbit == null) {
          return ['С трафиком > 100 Мбит: день ещё не завершён (трафик UTC)']
        }
        const pct = pctOfUsers(p.dayOver100Mbit, base)
        const prevPct = prev
          ? pctOfUsers(prev.dayOver100Mbit, prevBase)
          : 0
        return lineValueDeltaPct(
          'С трафиком > 100 Мбит',
          p.dayOver100Mbit,
          pct,
          pct - prevPct,
        )
      }
      if (label === 'Возвращающиеся активные') {
        if (p.dayPersistentTraffic == null) {
          return ['Возвращающиеся активные: день ещё не завершён (трафик UTC)']
        }
        const pct = pctOfUsers(p.dayPersistentTraffic, base)
        const prevPct = prev
          ? pctOfUsers(prev.dayPersistentTraffic, prevBase)
          : 0
        return lineValueDeltaPct(
          'Возвращающиеся активные',
          p.dayPersistentTraffic,
          pct,
          pct - prevPct,
        )
      }
      if (label === 'С активной подпиской') {
        const pct = pctOfUsers(p.dayActiveSubscription, base)
        const prevPct = prev
          ? pctOfUsers(prev.dayActiveSubscription, prevBase)
          : 0
        return lineValueDeltaPct(
          'С активной подпиской',
          p.dayActiveSubscription,
          pct,
          pct - prevPct,
        )
      }
      return []
    }

    const prevUsers = prev?.totalUsers ?? 0
    const prevTraffic = prev?.totalTraffic ?? 0
    const prevPayment = prev?.totalPayment ?? 0
    const dUsers = p.totalUsers - prevUsers
    const dTraffic = p.totalTraffic - prevTraffic
    const dPayment = p.totalPayment - prevPayment

    if (label === 'Всего пользователей') {
      return lineValueDelta('Пользователи', p.totalUsers, dUsers)
    }
    if (label === 'С трафиком') {
      return lineValueDelta('С трафиком', p.totalTraffic, dTraffic)
    }
    if (label === 'С подключением устройства') {
      const prevDev = prev?.totalDevices ?? 0
      const dDev = p.totalDevices - prevDev
      return lineValueDelta(
        'С подключением',
        p.totalDevices,
        dDev,
      )
    }
    if (label === 'С оплатой') {
      return lineValueDelta(
        'С оплатой',
        p.totalPayment,
        dPayment,
      )
    }
    if (label === 'Активные') {
      if (p.dayActive == null) return ['Активных: день ещё не завершён (трафик UTC)']
      const prevA = prev?.dayActive ?? 0
      const dA = p.dayActive - prevA
      return lineValueDelta('Активных', p.dayActive, dA)
    }
    if (label === 'С оплатой активных') {
      if (p.dayActiveWithPayment == null) {
        return ['С оплатой активных: день ещё не завершён (трафик UTC)']
      }
      const prevAp = prev?.dayActiveWithPayment ?? 0
      const dAp = p.dayActiveWithPayment - prevAp
      return lineValueDelta(
        'С оплатой активных',
        p.dayActiveWithPayment,
        dAp,
      )
    }
    if (label === 'С трафиком > 100 Мбит') {
      if (p.dayOver100Mbit == null) {
        return ['С трафиком > 100 Мбит: день ещё не завершён (трафик UTC)']
      }
      const prevH = prev?.dayOver100Mbit ?? 0
      const dH = p.dayOver100Mbit - prevH
      return lineValueDelta(
        'С трафиком > 100 Мбит',
        p.dayOver100Mbit,
        dH,
      )
    }
    if (label === 'Возвращающиеся активные') {
      if (p.dayPersistentTraffic == null) {
        return ['Возвращающиеся активные: день ещё не завершён (трафик UTC)']
      }
      const prevP = prev?.dayPersistentTraffic ?? 0
      const dP = p.dayPersistentTraffic - prevP
      return lineValueDelta(
        'Возвращающиеся активные',
        p.dayPersistentTraffic,
        dP,
      )
    }
    if (label === 'С активной подпиской') {
      const prevS = prev?.dayActiveSubscription ?? 0
      const dS = p.dayActiveSubscription - prevS
      return lineValueDelta(
        'С активной подпиской',
        p.dayActiveSubscription,
        dS,
      )
    }
    return []
  }

  async function load() {
    loading.value = true
    error.value = null
    try {
      const g = granularity.value
      let url = `/api/users/daily-stats?granularity=${encodeURIComponent(g)}`
      if (g === 'day' && dateRangeRef?.value) {
        const { from, to } = dateRangeRef.value
        if (from) url += `&from=${encodeURIComponent(String(from).slice(0, 10))}`
        if (to) url += `&to=${encodeURIComponent(String(to).slice(0, 10))}`
      }
      if (g === 'hour') {
        let day = String(hourDayMsk.value ?? '').trim().slice(0, 10)
        if (!day) {
          day = mskTodayIso()
          hourDayMsk.value = day
        }
        url += `&hour_day=${encodeURIComponent(day)}`
      }
      const data = await fetchJson(url)
      rows.value = Array.isArray(data.stats_by_date) ? data.stats_by_date : []
      trafficUtcToday.value =
        data.traffic_utc_today != null
          ? String(data.traffic_utc_today).slice(0, 10)
          : null
      if (g === 'hour') {
        hourBaselineUsers.value =
          Number(data.hour_baseline_users_count) || 0
        hourBaselineTraffic.value =
          Number(data.hour_baseline_users_with_traffic_count) || 0
        hourBaselineDevices.value =
          Number(data.hour_baseline_subscription_devices_users_count) || 0
        hourUndatedUsers.value = Number(data.hour_undated_users_count) || 0
      } else {
        hourBaselineUsers.value = 0
        hourBaselineTraffic.value = 0
        hourBaselineDevices.value = 0
        hourUndatedUsers.value = 0
        dayBaselineUsers.value =
          Number(data.day_baseline_users_count) || 0
        dayBaselineTraffic.value =
          Number(data.day_baseline_users_with_traffic_count) || 0
        dayBaselineDevices.value =
          Number(data.day_baseline_subscription_devices_users_count) || 0
        dayBaselinePayment.value =
          Number(data.day_baseline_users_with_payment_count) || 0
      }
    } catch (e) {
      error.value = e.message || String(e)
      rows.value = []
      hourBaselineUsers.value = 0
      hourBaselineTraffic.value = 0
      hourBaselineDevices.value = 0
      hourUndatedUsers.value = 0
      dayBaselineUsers.value = 0
      dayBaselineTraffic.value = 0
      dayBaselineDevices.value = 0
      dayBaselinePayment.value = 0
    } finally {
      loading.value = false
    }
    await nextTick()
  }

  return reactive({
    granularity,
    hourDayMsk,
    setGranularity,
    rows,
    loading,
    error,
    load,
    undatedCount,
    undatedTrafficCount,
    undatedPaymentCount,
    chartPoints,
    totalUsers,
    totalWithTraffic,
    totalWithSubscriptionDevices,
    totalWithPayment,
    activeUsersWidget,
    activeUsersWithPaymentWidget,
    activeSubscriptionWidget,
    pluralRuDays,
    pluralRuBuckets,
    bucketAxisLabel,
    chartAriaLabel,
    chartYTitle,
    chartPercentMode,
    formatChartYTick,
    registrationChartLabels,
    registrationChartDatasets,
    registrationTooltipTitle,
    registrationTooltipLabel,
  })
}
