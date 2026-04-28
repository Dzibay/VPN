<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Chart from 'chart.js/auto'
import { fetchJson } from '../api/client.js'
import { formatTrafficBytes as formatBytes } from '../utils/formatTraffic.js'

const route = useRoute()

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<object | null>} */
const bundle = ref(null)

/** @type {Chart | null} */
let chartInstance = null

const userId = computed(() => {
  const raw = route.params.userId
  const n = parseInt(String(raw), 10)
  return Number.isFinite(n) ? n : null
})

const userTitle = computed(() => {
  const b = bundle.value
  if (!b) return ''
  const tg = b.telegram_id && String(b.telegram_id).trim()
  return tg ? tg : `id ${b.user_id}`
})

function gridColor() {
  return 'rgba(88, 214, 141, 0.12)'
}

function tickColor() {
  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'rgba(200, 228, 210, 0.55)'
    : 'rgba(45, 85, 65, 0.45)'
}

function serverLabel(row) {
  const n = row.name && String(row.name).trim()
  if (n) return n
  return `${row.host}:${row.port}`
}

function formatDate(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return String(d)
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
  if (!el) return
  destroyChart()
  const b = bundle.value
  if (!b?.servers?.length) return
  const rows = [...b.servers].sort((a, b) => b.total_bytes - a.total_bytes)
  const mb = (x) => x / (1000 * 1000)
  chartInstance = new Chart(el, {
    type: 'bar',
    data: {
      labels: rows.map((r) => serverLabel(r)),
      datasets: [
        {
          label: 'К клиенту (down), МБ',
          data: rows.map((r) => mb(r.down_bytes)),
          backgroundColor: 'rgba(88, 214, 141, 0.78)',
        },
        {
          label: 'От клиента (up), МБ',
          data: rows.map((r) => mb(r.up_bytes)),
          backgroundColor: 'rgba(69, 179, 157, 0.78)',
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: tickColor(),
            font: { family: 'var(--sans)', size: 12 },
          },
        },
        tooltip: {
          backgroundColor: 'rgba(4, 12, 9, 0.94)',
          titleFont: { family: 'var(--sans)', size: 12 },
          bodyFont: { family: 'var(--mono)', size: 12 },
        },
      },
      scales: {
        x: {
          stacked: true,
          min: 0,
          ticks: { color: tickColor() },
          grid: { color: gridColor(), drawBorder: false },
          title: {
            display: true,
            text: 'МБ',
            color: tickColor(),
            font: { size: 11, weight: '600' },
          },
        },
        y: {
          stacked: true,
          ticks: { color: tickColor(), maxRotation: 0 },
          grid: { color: gridColor(), drawBorder: false },
        },
      },
    },
  })
}

const chartCanvas = ref(null)

async function load() {
  if (userId.value == null) {
    error.value = 'Некорректный id пользователя'
    bundle.value = null
    return
  }
  loading.value = true
  error.value = null
  bundle.value = null
  try {
    bundle.value = await fetchJson(
      `/api/users/${userId.value}/traffic-by-server`,
    )
  } catch (e) {
    error.value = e.message || String(e)
    bundle.value = null
  } finally {
    loading.value = false
  }
  await nextTick()
  drawChart()
}

watch(
  () => route.params.userId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/admin?tab=users">← Пользователи</RouterLink>
      <h1 class="page-title">Трафик по серверам</h1>
      <p v-if="bundle" class="sub">
        Пользователь <strong>{{ userTitle }}</strong>
        <span class="sub-sep">·</span>
        подписка до {{ formatDate(bundle.subscription_until) }}
      </p>
    </header>

    <p v-if="error" class="banner-err">{{ error }}</p>
    <p v-if="loading" class="loading-line">Загрузка…</p>

    <template v-if="!loading && bundle">
      <div class="meta-strip glass">
        <span
          ><strong>Всего вверх</strong>
          {{ formatBytes(bundle.total_up_bytes) }}</span
        >
        <span
          ><strong>Всего вниз</strong>
          {{ formatBytes(bundle.total_down_bytes) }}</span
        >
        <span
          ><strong>Сумма</strong>
          {{ formatBytes(bundle.total_up_bytes + bundle.total_down_bytes) }}</span
        >
        <span><strong>Узлов в БД</strong> {{ bundle.servers.length }}</span>
      </div>

      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">Распределение по узлам</h3>
          <span class="chart-unit">МБ</span>
        </div>
        <p class="chart-hint">
          Данные из накопленных счётчиков в БД (после сбора
          <code class="inline">xray api statsquery</code> на каждом узле). Узлы без записей
          показываются с нулями.
        </p>
        <div
          v-if="bundle.servers.length === 0"
          class="empty-hint"
        >
          В базе нет серверов.
        </div>
        <div v-else class="chart-wrap chart-wrap-tall">
          <canvas ref="chartCanvas" />
        </div>
      </div>

      <div class="table-wrap glass">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Узел</th>
              <th>Host</th>
              <th>Страна</th>
              <th>Статус</th>
              <th class="num">Вверх</th>
              <th class="num">Вниз</th>
              <th class="num">Всего</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in bundle.servers" :key="s.server_id">
              <td class="mono">{{ s.server_id }}</td>
              <td>{{ s.name || '—' }}</td>
              <td class="mono">{{ s.host }}:{{ s.port }}</td>
              <td>{{ s.country || '—' }}</td>
              <td>
                <span class="pill" :class="{ 'pill--ok': s.provision_ready }">{{
                  s.provision_ready ? 'готов' : 'не готов'
                }}</span>
                <span class="pill pill--muted" :class="{ 'pill--active': s.is_active }">{{
                  s.is_active ? 'активен' : 'выкл'
                }}</span>
              </td>
              <td class="num mono">{{ formatBytes(s.up_bytes) }}</td>
              <td class="num mono">{{ formatBytes(s.down_bytes) }}</td>
              <td class="num mono">{{ formatBytes(s.total_bytes) }}</td>
              <td class="row-actions">
                <RouterLink
                  class="link-analytics"
                  :to="{
                    path: '/admin/analytics',
                    query: { server: s.server_id },
                  }"
                >
                  Графики узла
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  padding: 1.35rem 1.5rem 3rem;
  max-width: 1180px;
  margin: 0 auto;
}
.head {
  margin-bottom: 1.35rem;
}
.back {
  display: inline-block;
  margin-bottom: 0.5rem;
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.9rem;
}
.back:hover {
  text-decoration: underline;
}
.page-title {
  margin: 0 0 0.4rem;
  font-size: 1.85rem;
  font-weight: 800;
  font-family: var(--heading);
  letter-spacing: -0.03em;
  color: var(--text-h);
}
.sub {
  margin: 0.35rem 0 0;
  font-size: 0.9rem;
  color: var(--muted);
  line-height: 1.5;
}
.sub strong {
  color: var(--text-h);
}
.sub-sep {
  margin: 0 0.35rem;
  opacity: 0.45;
}
.inline {
  font-family: var(--mono);
  font-size: 0.82em;
  background: var(--code-bg);
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
}
.glass {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(10px);
}
.meta-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem 1.75rem;
  padding: 0.75rem 1.1rem;
  margin-bottom: 1rem;
  font-size: 0.84rem;
  color: var(--text);
}
.meta-strip strong {
  color: var(--muted);
  font-weight: 700;
  margin-right: 0.35rem;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.banner-err {
  padding: 0.85rem 1.1rem;
  border-radius: 14px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 0.9rem;
  margin: 0 0 1rem;
}
.loading-line {
  color: var(--muted);
  font-size: 0.92rem;
}
.chart-panel {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1.15rem;
}
.chart-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}
.chart-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.chart-unit {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.chart-hint {
  margin: 0 0 0.85rem;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.5;
  max-width: 52rem;
}
.chart-wrap {
  position: relative;
  min-height: 220px;
}
.chart-wrap-tall {
  min-height: 320px;
}
.empty-hint {
  padding: 1rem 0;
  color: var(--muted);
  font-size: 0.9rem;
}
.table-wrap {
  padding: 0.5rem 0 0;
  overflow-x: auto;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
}
.table th,
.table td {
  padding: 0.55rem 0.65rem;
  text-align: left;
  border-bottom: 1px solid var(--card-border);
  vertical-align: middle;
}
.table th {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  font-weight: 700;
}
.table tbody tr:last-child td {
  border-bottom: none;
}
.num {
  text-align: right;
  white-space: nowrap;
}
.mono {
  font-family: var(--mono);
  font-size: 0.82rem;
}
.pill {
  display: inline-block;
  margin-right: 0.35rem;
  padding: 0.12rem 0.45rem;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--surface);
  color: var(--muted);
  border: 1px solid var(--card-border);
}
.pill--ok {
  background: rgba(34, 197, 94, 0.14);
  border-color: rgba(34, 197, 94, 0.45);
  color: var(--text-h);
}
.pill--muted {
  opacity: 0.85;
}
.pill--active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}
.row-actions {
  text-align: right;
  white-space: nowrap;
}
.link-analytics {
  color: var(--accent);
  font-weight: 600;
  font-size: 0.82rem;
  text-decoration: none;
}
.link-analytics:hover {
  text-decoration: underline;
}
</style>
