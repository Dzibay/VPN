<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Chart from 'chart.js/auto'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import { isAdminRole } from '../auth/permissions.js'
import { getSessionRole } from '../auth/session.js'
import { fetchJson } from '../api/client.js'

const route = useRoute()
/** @type {import('vue').Ref<Array<{ registration_date: string | null; users_count: number; users_with_traffic_count?: number }>>} */
const rows = ref([])
const loading = ref(false)
const error = ref(null)

const isFullAdmin = computed(() => isAdminRole(getSessionRole()))

/** @type {Chart | null} */
let chartInstance = null
const chartCanvas = ref(null)

const undatedCount = computed(() => {
  const row = rows.value.find(
    (r) => r.registration_date == null || r.registration_date === '',
  )
  return row ? Number(row.users_count) || 0 : 0
})

const undatedTrafficCount = computed(() => {
  const row = rows.value.find(
    (r) => r.registration_date == null || r.registration_date === '',
  )
  return row ? Number(row.users_with_traffic_count) || 0 : 0
})

const chartPoints = computed(() => {
  const extraUsers = undatedCount.value
  const extraTraffic = undatedTrafficCount.value
  const sorted = rows.value
    .filter((r) => r.registration_date != null && r.registration_date !== '')
    .map((r) => ({
      iso: String(r.registration_date),
      dayUsers: Number(r.users_count) || 0,
      dayTraffic: Number(r.users_with_traffic_count) || 0,
    }))
    .sort((a, b) => a.iso.localeCompare(b.iso))

  let cumDatedUsers = 0
  let cumDatedTraffic = 0
  return sorted.map((row) => {
    cumDatedUsers += row.dayUsers
    cumDatedTraffic += row.dayTraffic
    return {
      iso: row.iso,
      dayUsers: row.dayUsers,
      dayTraffic: row.dayTraffic,
      cumDatedUsers,
      cumDatedTraffic,
      totalUsers: cumDatedUsers + extraUsers,
      totalTraffic: cumDatedTraffic + extraTraffic,
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

/** Склонение «день» для числа n */
function pluralRuDays(n) {
  const k = Math.abs(Math.trunc(Number(n))) % 100
  const d = k % 10
  if (k > 10 && k < 20) return 'дней'
  if (d === 1) return 'день'
  if (d >= 2 && d <= 4) return 'дня'
  return 'дней'
}

/** RGB из computed color или #RRGGBB */
function rgbTupleFromCssColor(css) {
  const m = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(css.trim())
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])]
  const hx = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(css.trim())
  if (hx) {
    return [
      parseInt(hx[1], 16),
      parseInt(hx[2], 16),
      parseInt(hx[3], 16),
    ]
  }
  return [88, 214, 141]
}

/** Цвет из CSS-переменной у :root (через временный элемент) */
function rgbTupleFromVar(name, fallbackHex) {
  if (typeof document === 'undefined') {
    return rgbTupleFromCssColor(fallbackHex)
  }
  const probe = document.createElement('span')
  probe.style.cssText =
    'position:absolute;left:-9999px;top:0;color:var(' + name + ',' + fallbackHex + ')'
  document.body.appendChild(probe)
  const rgb = rgbTupleFromCssColor(getComputedStyle(probe).color)
  probe.remove()
  return rgb
}

function rootToken(name, fallback) {
  if (typeof document === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
  return v || fallback
}

function rgba(rgb, a) {
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`
}

function fmtRu(n) {
  return Number(n).toLocaleString('ru-RU')
}

function gridColor() {
  return rootToken('--accent-chart-grid', 'rgba(88, 214, 141, 0.12)')
}

function tickColor() {
  return rootToken('--text-h', '#e8f4ec')
}

function mutedTickColor() {
  return rootToken('--muted', '#6d8578')
}

function chartTheme() {
  const accent = rgbTupleFromVar('--accent', '#58d68d')
  /** Оранжевая линия трафика (контраст к зелёным регистрациям) */
  const trafficOrange = [251, 146, 60]
  const cardBorder = rootToken('--accent-border', 'rgba(88, 214, 141, 0.42)')
  const surface = rootToken('--card-bg', 'rgba(12, 16, 14, 0.94)')
  return {
    accent,
    trafficOrange,
    accentBorder: cardBorder,
    tooltipBg: surface,
    textH: tickColor(),
    muted: mutedTickColor(),
    grid: gridColor(),
  }
}

function formatDayShort(iso) {
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

function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
}

function drawChart() {
  const el = chartCanvas.value
  if (!el || loading.value || error.value || chartPoints.value.length === 0) {
    destroyChart()
    return
  }
  destroyChart()
  const pts = chartPoints.value
  const undated = undatedCount.value
  const undatedTraffic = undatedTrafficCount.value
  const theme = chartTheme()
  const surfaceBg = rootToken('--surface', '#0c100e')
  const n = pts.length

  chartInstance = new Chart(el, {
    type: 'line',
    data: {
      labels: pts.map((p) => formatDayShort(p.iso)),
      datasets: [
        {
          label: 'Всего пользователей · накопительно',
          data: pts.map((p) => p.totalUsers),
          borderColor: rgba(theme.accent, 0.95),
          borderWidth: 2.75,
          tension: 0.35,
          cubicInterpolationMode: 'monotone',
          fill: true,
          backgroundColor: (c) => {
            const chart = c.chart
            const { ctx: cctx, chartArea } = chart
            if (!chartArea) return rgba(theme.accent, 0.12)
            const g = cctx.createLinearGradient(
              0,
              chartArea.top,
              0,
              chartArea.bottom,
            )
            g.addColorStop(0, rgba(theme.accent, 0.28))
            g.addColorStop(0.55, rgba(theme.accent, 0.07))
            g.addColorStop(1, rgba(theme.accent, 0))
            return g
          },
          pointRadius: n > 100 ? 0 : n > 48 ? 2 : 3.5,
          pointHoverRadius: 6,
          pointBorderWidth: 2,
          pointBackgroundColor: surfaceBg,
          pointBorderColor: rgba(theme.accent, 0.9),
          pointHoverBorderColor: rgba(theme.accent, 1),
          pointHoverBackgroundColor: rgba(theme.accent, 0.25),
        },
        {
          label: 'С трафиком · накопительно',
          data: pts.map((p) => p.totalTraffic),
          borderColor: rgba(theme.trafficOrange, 0.94),
          borderWidth: 2.25,
          tension: 0.35,
          cubicInterpolationMode: 'monotone',
          fill: true,
          backgroundColor: (c) => {
            const chart = c.chart
            const { ctx: cctx, chartArea } = chart
            if (!chartArea) return rgba(theme.trafficOrange, 0.06)
            const g = cctx.createLinearGradient(
              0,
              chartArea.top,
              0,
              chartArea.bottom,
            )
            g.addColorStop(0, rgba(theme.trafficOrange, 0.2))
            g.addColorStop(0.65, rgba(theme.trafficOrange, 0.06))
            g.addColorStop(1, rgba(theme.trafficOrange, 0))
            return g
          },
          pointRadius: n > 100 ? 0 : n > 48 ? 2 : 3,
          pointHoverRadius: 6,
          pointBorderWidth: 2,
          pointBackgroundColor: surfaceBg,
          pointBorderColor: rgba(theme.trafficOrange, 0.88),
          pointHoverBorderColor: rgba(theme.trafficOrange, 1),
          pointHoverBackgroundColor: rgba(theme.trafficOrange, 0.2),
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: {
        duration: 680,
        easing: 'easeOutQuart',
      },
      elements: {
        line: {
          borderJoinStyle: 'round',
          borderCapStyle: 'round',
        },
      },
      plugins: {
        legend: {
          position: 'top',
          align: 'start',
          labels: {
            color: theme.muted,
            font: { family: 'var(--sans)', size: 12, weight: '600' },
            padding: 14,
            usePointStyle: true,
            pointStyle: 'circle',
          },
        },
        tooltip: {
          backgroundColor: theme.tooltipBg,
          titleColor: theme.textH,
          bodyColor: theme.textH,
          borderColor: theme.accentBorder,
          borderWidth: 1,
          padding: 12,
          cornerRadius: 12,
          displayColors: true,
          boxPadding: 6,
          titleFont: { family: 'var(--sans)', size: 13, weight: '700' },
          bodyFont: { family: 'var(--mono)', size: 12 },
          callbacks: {
            title(items) {
              const i = items[0]?.dataIndex
              if (i == null) return ''
              const iso = pts[i]?.iso
              return iso ? formatDayShort(iso) : ''
            },
            label(ctx) {
              const i = ctx.dataIndex
              const p = pts[i]
              if (!p) return ''
              if (ctx.datasetIndex === 0) {
                return undated > 0
                  ? `Пользователей (${fmtRu(p.cumDatedUsers)}+${fmtRu(undated)})`
                  : `Пользователей (${fmtRu(p.cumDatedUsers)})`
              }
              return undatedTraffic > 0
                ? `С трафиком (${fmtRu(p.cumDatedTraffic)}+${fmtRu(undatedTraffic)})`
                : `С трафиком (${fmtRu(p.cumDatedTraffic)})`
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: theme.muted,
            maxRotation: 40,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 22,
            font: { family: 'var(--sans)', size: 11 },
          },
          grid: {
            color: theme.grid,
            drawBorder: false,
            tickLength: 0,
          },
        },
        y: {
          beginAtZero: true,
          grace: '8%',
          ticks: {
            color: theme.muted,
            font: { family: 'var(--mono)', size: 11 },
            padding: 8,
          },
          grid: {
            color: theme.grid,
            drawBorder: false,
          },
          title: {
            display: true,
            text: 'Пользователей (накопительно)',
            color: theme.muted,
            font: { family: 'var(--sans)', size: 11, weight: '600' },
            padding: { bottom: 4, top: 0 },
          },
        },
      },
    },
  })
}

async function load() {
  loading.value = true
  destroyChart()
  error.value = null
  try {
    rows.value = await fetchJson('/api/users/registrations-by-date')
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
  await nextTick()
  drawChart()
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <AdminPageShell>
    <AdminPageHeader
      title="Регистрации по дням"
      :tabs-aria-label="isFullAdmin ? 'Разделы админки' : 'Раздел менеджера'"
    >
      <template #back>
        <RouterLink v-if="isFullAdmin" class="back" to="/admin/users">
          ← Управление данными
        </RouterLink>
        <RouterLink v-else class="back" to="/cabinet">← Личный кабинет</RouterLink>
      </template>
      <template #tabs>
        <template v-if="isFullAdmin">
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users' }"
            :to="{ path: '/admin/users' }"
          >
            Пользователи
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-servers' }"
            :to="{ path: '/admin/servers' }"
          >
            Серверы
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
            :to="{ path: '/admin/users/analytics' }"
          >
            Клиенты
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
            :to="{ path: '/admin/users/registrations-by-date' }"
          >
            Регистрации по дням
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-analytics' }"
            :to="{ path: '/admin/analytics' }"
          >
            Нагрузка
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-funnel' }"
            :to="{ path: '/admin/funnel' }"
          >
            Воронка
          </RouterLink>
          <RouterLink class="tab" :to="{ path: '/admin/referrals' }">
            Реферальные токены
          </RouterLink>
        </template>
        <template v-else>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
            :to="{ path: '/admin/users/analytics' }"
          >
            Клиенты
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
            :to="{ path: '/admin/users/registrations-by-date' }"
          >
            Регистрации по дням
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-funnel' }"
            :to="{ path: '/admin/funnel' }"
          >
            Воронка
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-referrals' }"
            :to="{ path: '/admin/referrals' }"
          >
            Реферальные токены
          </RouterLink>
        </template>
      </template>
      <div class="head-row">
        <div class="head-text">
          <h2 class="section-heading">Накопление пользователей по дате регистрации</h2>
          <p class="section-sub">
            Кривые растут по мере наступления дня (UTC): сколько уже есть
            пользователей с этой датой или раньше; вторая линия — сколько из них
            с трафиком по <span class="mono-inline">user_server_traffic</span>.
          </p>
        </div>
        <div class="head-actions">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading"
            @click="load"
          >
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </AdminPageHeader>

    <section class="stats" aria-live="polite">
      <p v-if="loading" class="stats-status muted">Загрузка…</p>
      <p v-else-if="error" class="stats-status stats-status--err">
        Не удалось загрузить сводку (подробности ниже).
      </p>
      <dl v-else class="stats-grid">
        <div class="stats-card">
          <dt class="stats-label">Дней на графике</dt>
          <dd class="stats-value">
            {{ chartPoints.length.toLocaleString('ru-RU') }}
            <span class="stats-unit">{{ pluralRuDays(chartPoints.length) }}</span>
          </dd>
        </div>
        <div class="stats-card">
          <dt class="stats-label">Всего пользователей</dt>
          <dd class="stats-value">
            {{ totalUsers.toLocaleString('ru-RU') }}
          </dd>
          <p class="stats-hint">Записей в БД</p>
        </div>
        <div class="stats-card">
          <dt class="stats-label">С ненулевым трафиком</dt>
          <dd class="stats-value stats-value--traffic">
            {{ totalWithTraffic.toLocaleString('ru-RU') }}
          </dd>
          <p class="stats-hint">Up+down по последнему дню на узел</p>
        </div>
      </dl>
    </section>

    <div class="chart-panel glass">
      <p v-if="error" class="banner-err">{{ error }}</p>
      <p v-else-if="loading" class="loading-line">Загрузка…</p>
      <template v-else>
        <p
          v-if="chartPoints.length === 0 && undatedCount > 0"
          class="empty-hint"
        >
          Нет ни одной известной даты регистрации — только пользователи без
          даты:
          <strong>{{ undatedCount.toLocaleString('ru-RU') }}</strong>
          . Добавить их к точкам по дням нельзя — появится график после появления
          записей с датой.
        </p>
        <p v-else-if="chartPoints.length === 0" class="empty-hint">
          Нет данных для графика.
        </p>
        <div v-else class="chart-wrap chart-wrap-tall">
          <canvas
            ref="chartCanvas"
            aria-label="Накопление числа пользователей и пользователей с трафиком по датам регистрации UTC"
          />
        </div>
      </template>
    </div>
  </AdminPageShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem 1rem;
}

.head-text {
  min-width: min(100%, 42rem);
}

.section-heading {
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-h);
}

.section-sub {
  margin: 0;
  max-width: 46rem;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
}

.mono-inline {
  font-family: var(--mono);
  font-size: 0.78rem;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stats {
  margin-bottom: 1rem;
}

.stats-status {
  margin: 0;
  font-size: 0.92rem;
}

.stats-status--err {
  color: var(--danger);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr));
  gap: 0.75rem 1rem;
  margin: 0;
}

.stats-card {
  margin: 0;
  padding: 0.65rem 0.75rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
}

.stats-label {
  margin: 0 0 0.35rem;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.stats-value {
  margin: 0;
  font-size: 1.12rem;
  font-weight: 800;
  font-family: var(--heading, inherit);
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  line-height: 1.2;
}

.stats-value--traffic {
  color: #fb923c;
}

@media (prefers-color-scheme: light) {
  .stats-value--traffic {
    color: #ea580c;
  }
}

.stats-unit {
  margin-left: 0.25rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: lowercase;
}

.stats-hint {
  margin: 0.35rem 0 0;
  font-size: 0.76rem;
  line-height: 1.4;
  color: var(--muted);
}

.chart-panel {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
}

.chart-wrap {
  position: relative;
  min-height: 220px;
}

.chart-wrap-tall {
  min-height: min(58vh, 440px);
}

.banner-err {
  padding: 0.85rem 1.1rem;
  border-radius: 14px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 0.9rem;
  margin: 0;
}

.loading-line {
  color: var(--muted);
  font-size: 0.92rem;
  margin: 0;
}

.empty-hint {
  margin: 0;
  padding: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.5;
}
</style>
