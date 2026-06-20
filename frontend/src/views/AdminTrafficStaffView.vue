<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import { fetchJson } from '../api/client.js'
import { chartSeriesRgb, rgbTupleFromVar } from '../utils/adminChartTheme.js'
import {
  addCalendarDayIso,
  formatMskCalendarDayShort,
  mskTodayIso,
  subtractCalendarDaysIso,
} from '../utils/mskDate.js'

/** @typedef {{ server_id: number; name: string | null; host: string; delta_inbound_bytes: number[] }} ServerSeries */
/** @typedef {{ stats_date: string | null; users_count: number; users_with_traffic_count: number; subscription_devices_users_count: number }} DailyStatsRow */

const loading = ref(false)
const trafficError = ref(null)
const userStatsError = ref(null)
const days = ref(30)

/** @type {import('vue').Ref<{ dates: string[]; total_delta_inbound_bytes: number[]; servers: ServerSeries[]; exit_server_ids?: number[] } | null>} */
const bundle = ref(null)

/** @type {import('vue').Ref<DailyStatsRow[]>} */
const userStatsRows = ref([])

const dayOptions = [
  { value: 7, label: '7 дней' },
  { value: 30, label: '30 дней' },
  { value: 60, label: '60 дней' },
  { value: 90, label: '90 дней' },
  { value: 180, label: '180 дней' },
]

const SERVER_LINE_RGB = [
  [56, 189, 248],
  [167, 139, 250],
  [129, 140, 248],
  [45, 212, 191],
  [52, 211, 153],
  [244, 114, 182],
  [245, 158, 11],
  [236, 72, 153],
  [34, 197, 94],
  [251, 146, 60],
]

function formatTrafficDayLabel(trafficDate) {
  const s = String(trafficDate ?? '').trim().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return s || '—'
  const [y, m, d] = s.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

function bytesToGib(bytes) {
  return Number(bytes || 0) / 1024 ** 3
}

function formatChartYTick(v) {
  const gib = Number(v)
  if (!Number.isFinite(gib)) return '—'
  if (gib >= 100) return `${Math.round(gib)} ГиБ`
  if (gib >= 10) return `${Math.round(gib * 10) / 10} ГиБ`
  return `${Math.round(gib * 100) / 100} ГиБ`
}

function formatCountYTick(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('ru-RU')
}

function serverLabel(s) {
  const name = String(s.name ?? '').trim()
  if (name) return name
  const host = String(s.host ?? '').trim()
  return host || `Узел ${s.server_id}`
}

const exitServerIdSet = computed(
  () => new Set((bundle.value?.exit_server_ids ?? []).map((id) => Number(id))),
)

/** Узлы на графике — все, кроме текущих каскадных exit. */
const chartServers = computed(() =>
  (bundle.value?.servers ?? []).filter((s) => !exitServerIdSet.value.has(s.server_id)),
)

/** Выходные узлы — зачёркнуты в легенде, линий нет. */
const excludedExitServers = computed(() =>
  (bundle.value?.servers ?? []).filter((s) => exitServerIdSet.value.has(s.server_id)),
)

const excludedLegendLabels = computed(() =>
  excludedExitServers.value.map((s) => serverLabel(s)),
)

const chartTotalGib = computed(() => {
  const n = bundle.value?.dates?.length ?? 0
  if (!n) return []
  const totals = Array.from({ length: n }, () => 0)
  for (const s of chartServers.value) {
    const deltas = s.delta_inbound_bytes ?? []
    for (let i = 0; i < n; i++) {
      totals[i] += Number(deltas[i] || 0)
    }
  }
  return totals.map(bytesToGib)
})

const chartLabels = computed(() =>
  (bundle.value?.dates ?? []).map((d) => formatTrafficDayLabel(d)),
)

const chartDatasets = computed(() => {
  const data = bundle.value
  if (!data?.dates?.length) return []

  const total = {
    label: 'Суммарно (входящий)',
    data: chartTotalGib.value,
    rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.traffic]),
    filled: true,
    borderWidth: 2.75,
  }

  const perServer = chartServers.value.map((s, idx) => ({
    label: serverLabel(s),
    data: (s.delta_inbound_bytes ?? []).map(bytesToGib),
    rgb: /** @type {[number, number, number]} */ ([
      ...SERVER_LINE_RGB[idx % SERVER_LINE_RGB.length],
    ]),
    filled: false,
    borderWidth: 1.75,
  }))

  return [total, ...perServer]
})

const hasData = computed(() => {
  const data = bundle.value
  if (!data?.dates?.length) return false
  return chartTotalGib.value.some((v) => Number(v) > 0)
})

const chartAriaLabel =
  'По дням UTC: суточный входящий трафик (down) суммарно по всем узлам и по каждому узлу отдельно'

function registrationTooltipTitle(i) {
  const d = bundle.value?.dates?.[i]
  if (!d) return chartLabels.value[i] ?? ''
  return `${formatTrafficDayLabel(d)} (UTC)`
}

/** @param {import('chart.js').TooltipItem<'line'>} ctx */
function registrationTooltipLabel(ctx) {
  const i = ctx.dataIndex
  if (ctx.datasetIndex === 0) {
    const gib = chartTotalGib.value[i]
    return `${ctx.dataset.label}: ${formatChartYTick(gib)}`
  }
  const bytes = chartServers.value[ctx.datasetIndex - 1]?.delta_inbound_bytes?.[i]
  return `${ctx.dataset.label}: ${formatChartYTick(bytesToGib(bytes))}`
}

/** Суточные метрики за последние ``days`` календарных дней МСК (не накопительно). */
const userStatsPoints = computed(() => {
  const rows = userStatsRows.value.filter(
    (r) => r.stats_date != null && String(r.stats_date).trim() !== '',
  )
  const endIso = mskTodayIso()
  const startIso = subtractCalendarDaysIso(endIso, Math.max(0, days.value - 1))
  const map = new Map(
    rows.map((r) => [String(r.stats_date).slice(0, 10), r]),
  )
  const out = []
  let iso = startIso
  while (iso <= endIso) {
    const row = map.get(iso)
    out.push({
      iso,
      registrations: Number(row?.users_count) || 0,
      connections: Number(row?.subscription_devices_users_count) || 0,
      withTraffic: Number(row?.users_with_traffic_count) || 0,
    })
    if (iso === endIso) break
    iso = addCalendarDayIso(iso)
  }
  return out
})

const userStatsLabels = computed(() =>
  userStatsPoints.value.map((p) => formatMskCalendarDayShort(p.iso)),
)

const userStatsDatasets = computed(() => {
  const pts = userStatsPoints.value
  if (!pts.length) return []
  return [
    {
      label: 'Регистрации',
      data: pts.map((p) => p.registrations),
      rgb: rgbTupleFromVar('--accent', '#58d68d'),
      filled: true,
    },
    {
      label: 'Подключения устройств',
      data: pts.map((p) => p.connections),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.device]),
      filled: false,
    },
    {
      label: 'Новые с трафиком',
      data: pts.map((p) => p.withTraffic),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.traffic]),
      filled: false,
    },
  ]
})

const userStatsHasData = computed(() =>
  userStatsPoints.value.some(
    (p) => p.registrations > 0 || p.connections > 0 || p.withTraffic > 0,
  ),
)

const userStatsAriaLabel =
  'По дням МСК: регистрации, первые подключения устройств и новые пользователи с ненулевым трафиком за сутки'

function userStatsTooltipTitle(i) {
  const p = userStatsPoints.value[i]
  if (!p) return ''
  return `${formatMskCalendarDayShort(p.iso)} (МСК)`
}

/** @param {import('chart.js').TooltipItem<'line'>} ctx */
function userStatsTooltipLabel(ctx) {
  const v = ctx.parsed.y
  return `${ctx.dataset.label}: ${formatCountYTick(v)}`
}

async function load() {
  loading.value = true
  trafficError.value = null
  userStatsError.value = null
  const daysParam = encodeURIComponent(days.value)
  const [trafficRes, statsRes] = await Promise.allSettled([
    fetchJson(`/api/servers/user-traffic/daily-summary-all?days=${daysParam}`),
    fetchJson('/api/users/daily-stats?granularity=day'),
  ])
  if (trafficRes.status === 'fulfilled') {
    bundle.value = trafficRes.value
  } else {
    trafficError.value =
      trafficRes.reason?.message || String(trafficRes.reason)
    bundle.value = null
  }
  if (statsRes.status === 'fulfilled') {
    const rows = statsRes.value?.stats_by_date
    userStatsRows.value = Array.isArray(rows) ? rows : []
  } else {
    userStatsError.value =
      statsRes.reason?.message || String(statsRes.reason)
    userStatsRows.value = []
  }
  loading.value = false
}

watch(days, () => {
  void load()
})

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="Трафик" shell-class="admin-traffic-page">
    <template #headerExtras>
      <div class="toolbar">
        <label class="days-field">
          <span class="days-label">Период</span>
          <select v-model.number="days" class="days-select" :disabled="loading">
            <option v-for="o in dayOptions" :key="o.value" :value="o.value">
              {{ o.label }}
            </option>
          </select>
        </label>
        <AppRefreshButton :loading="loading" @click="load" />
      </div>
    </template>

    <AdminLineChartPanel
      title="Входящий трафик по дням"
      unit-label="ГиБ / сутки"
      hint=""
      :aria-label="chartAriaLabel"
      :loading="loading"
      :error="trafficError"
      :has-data="hasData"
      y-title="ГиБ за сутки"
      y-grace="8%"
      :labels="chartLabels"
      :datasets="chartDatasets"
      :excluded-legend-labels="excludedLegendLabels"
      :format-y-tick="formatChartYTick"
      :get-tooltip-title="registrationTooltipTitle"
      :get-tooltip-label="registrationTooltipLabel"
    >
      <template #empty>
        <p class="empty-hint">
          Нет данных о трафике за выбранный период. Убедитесь, что выполняется сбор
          трафика с узлов (задачи RQ или страница «Нагрузка»).
        </p>
      </template>
    </AdminLineChartPanel>

    <AdminLineChartPanel
      title="Пользователи по дням"
      unit-label="за сутки"
      hint="Календарные дни Europe/Moscow. Регистрации — новые учётные пользователи; подключения — первое устройство в subscription_devices; новые с трафиком — зарегистрированные в этот день с ненулевым суммарным трафиком."
      :aria-label="userStatsAriaLabel"
      :loading="loading"
      :error="userStatsError"
      :has-data="userStatsHasData"
      y-title="Пользователей"
      y-grace="8%"
      :labels="userStatsLabels"
      :datasets="userStatsDatasets"
      :format-y-tick="formatCountYTick"
      :get-tooltip-title="userStatsTooltipTitle"
      :get-tooltip-label="userStatsTooltipLabel"
    >
      <template #empty>
        <p class="empty-hint">Нет данных о регистрациях и подключениях за выбранный период.</p>
      </template>
    </AdminLineChartPanel>
  </AdminStaffShell>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem 1rem;
  margin-bottom: 0.5rem;
}

.days-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.days-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}

.days-select {
  min-width: 8.5rem;
  padding: 0.45rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 0.88rem;
}

.empty-hint {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.5;
  max-width: 42rem;
}
</style>
