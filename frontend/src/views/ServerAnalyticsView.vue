<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import Chart from 'chart.js/auto'
import { fetchJson } from '../api/client.js'

const route = useRoute()
const router = useRouter()

const servers = ref([])
const serverId = ref(null)
const hours = ref(24)
/** @type {import('vue').Ref<{ source: string, instance: string, step_seconds: number, points: any[] } | null>} */
const metricsBundle = ref(null)
const loading = ref(false)
const error = ref(null)

const chartCpu = ref(null)
const chartNet = ref(null)
const chartTcp = ref(null)
const chartLoad = ref(null)

/** @type {Chart[]} */
let chartInstances = []

function destroyCharts() {
  chartInstances.forEach((c) => c.destroy())
  chartInstances = []
}

const metrics = computed(() => metricsBundle.value?.points ?? [])

const hourOptions = [
  { value: 6, label: '6 ч' },
  { value: 24, label: '24 ч' },
  { value: 72, label: '3 суток' },
  { value: 168, label: '7 суток' },
]

const selectedServer = computed(() =>
  servers.value.find((s) => s.id === serverId.value),
)

const latest = computed(() => {
  const m = metrics.value
  return m.length ? m[m.length - 1] : null
})

const promInstance = computed(() => metricsBundle.value?.instance ?? '—')

const promStep = computed(() => metricsBundle.value?.step_seconds ?? '—')

function formatTs(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatUptime(sec) {
  if (sec == null) return '—'
  const s = Number(sec)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}д ${h}ч`
  if (h > 0) return `${h}ч ${m}м`
  return `${m}м`
}

async function loadServers() {
  servers.value = await fetchJson('/api/servers')
  const q = route.query.server
  if (q != null && q !== '') {
    const id = parseInt(String(q), 10)
    if (!Number.isNaN(id)) {
      serverId.value = id
      return
    }
  }
  if (serverId.value == null && servers.value.length) {
    serverId.value = servers.value[0].id
  }
}

async function loadMetrics() {
  if (serverId.value == null) return
  loading.value = true
  error.value = null
  metricsBundle.value = null
  try {
    const step =
      hours.value <= 24 ? 60 : hours.value <= 72 ? 120 : 180
    metricsBundle.value = await fetchJson(
      `/api/servers/${serverId.value}/metrics?hours=${hours.value}&step=${step}`,
    )
  } catch (e) {
    error.value = e.message || String(e)
    metricsBundle.value = null
  } finally {
    loading.value = false
  }
  await nextTick()
  drawCharts()
}

function labelsFor(m) {
  return m.map((row) => formatTs(row.recorded_at))
}

function drawCharts() {
  destroyCharts()
  const m = metrics.value
  if (!m.length) return

  const labels = labelsFor(m)
  const common = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'top' },
    },
    scales: {
      x: {
        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
      },
    },
  }

  const palette = {
    cpu: 'rgb(99, 102, 241)',
    mem: 'rgb(236, 72, 153)',
    disk: 'rgb(245, 158, 11)',
    rx: 'rgb(34, 197, 94)',
    tx: 'rgb(59, 130, 246)',
    tcp: 'rgb(168, 85, 247)',
    load: 'rgb(239, 68, 68)',
  }

  if (chartCpu.value) {
    chartInstances.push(
      new Chart(chartCpu.value, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'CPU %',
              data: m.map((r) => r.cpu_percent),
              borderColor: palette.cpu,
              tension: 0.2,
              spanGaps: true,
            },
            {
              label: 'Память %',
              data: m.map((r) => r.memory_percent),
              borderColor: palette.mem,
              tension: 0.2,
              spanGaps: true,
            },
            {
              label: 'Диск %',
              data: m.map((r) => r.disk_used_percent),
              borderColor: palette.disk,
              tension: 0.2,
              spanGaps: true,
            },
          ],
        },
        options: {
          ...common,
          scales: {
            ...common.scales,
            y: { min: 0, max: 100, title: { display: true, text: '%' } },
          },
        },
      }),
    )
  }

  if (chartNet.value) {
    chartInstances.push(
      new Chart(chartNet.value, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'RX Мбит/с',
              data: m.map((r) => r.net_rx_mbps),
              borderColor: palette.rx,
              tension: 0.2,
              spanGaps: true,
            },
            {
              label: 'TX Мбит/с',
              data: m.map((r) => r.net_tx_mbps),
              borderColor: palette.tx,
              tension: 0.2,
              spanGaps: true,
            },
          ],
        },
        options: {
          ...common,
          scales: {
            ...common.scales,
            y: { min: 0, title: { display: true, text: 'Мбит/с' } },
          },
        },
      }),
    )
  }

  if (chartTcp.value) {
    chartInstances.push(
      new Chart(chartTcp.value, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'TCP (CurrEstab)',
              data: m.map((r) => r.tcp_established),
              borderColor: palette.tcp,
              tension: 0.2,
              spanGaps: true,
            },
          ],
        },
        options: {
          ...common,
          scales: {
            ...common.scales,
            y: { min: 0, title: { display: true, text: 'соединений' } },
          },
        },
      }),
    )
  }

  if (chartLoad.value) {
    chartInstances.push(
      new Chart(chartLoad.value, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Load avg 1m',
              data: m.map((r) => r.load_avg_1m),
              borderColor: palette.load,
              tension: 0.2,
              spanGaps: true,
            },
          ],
        },
        options: {
          ...common,
          scales: {
            ...common.scales,
            y: { min: 0, title: { display: true, text: 'load' } },
          },
        },
      }),
    )
  }
}

function onServerChange() {
  router.replace({
    path: '/admin/analytics',
    query: { server: String(serverId.value) },
  })
  loadMetrics()
}

watch(hours, () => {
  loadMetrics()
})

onMounted(async () => {
  try {
    await loadServers()
    if (
      serverId.value != null &&
      String(route.query.server || '') !== String(serverId.value)
    ) {
      router.replace({
        path: '/admin/analytics',
        query: { server: String(serverId.value) },
      })
    }
    await loadMetrics()
  } catch (e) {
    error.value = e.message || String(e)
  }
})

onBeforeUnmount(() => {
  destroyCharts()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/admin?tab=servers">← Серверы</RouterLink>
      <h1 class="page-title">Аналитика нагрузки</h1>
      <p class="sub">
        Данные из
        <strong>Prometheus</strong>
        (метрики
        <a
          href="https://github.com/prometheus/node_exporter"
          target="_blank"
          rel="noopener noreferrer"
          >node_exporter</a
        >). Задайте
        <code class="inline">PROMETHEUS_BASE_URL</code>
        в API и при необходимости поле «Prometheus instance» у сервера (label
        <code class="inline">instance</code>
        , иначе
        <code class="inline">host:9100</code>
        ).
      </p>
    </header>

    <div class="toolbar card">
      <label class="field-inline">
        <span>Сервер</span>
        <select
          v-model.number="serverId"
          class="select"
          :disabled="!servers.length"
          @change="onServerChange"
        >
          <option v-for="s in servers" :key="s.id" :value="s.id">
            {{ s.name || s.host }} ({{ s.host }}) — load {{ s.load_percent ?? 0 }}%
          </option>
        </select>
      </label>
      <label class="field-inline">
        <span>Период</span>
        <select v-model.number="hours" class="select">
          <option v-for="o in hourOptions" :key="o.value" :value="o.value">
            {{ o.label }}
          </option>
        </select>
      </label>
      <button
        type="button"
        class="btn-secondary"
        :disabled="loading || serverId == null"
        @click="loadMetrics"
      >
        Обновить
      </button>
    </div>

    <p v-if="metricsBundle" class="meta card">
      <span
        ><strong>instance:</strong>
        <code class="inline">{{ promInstance }}</code></span
      >
      <span
        ><strong>шаг:</strong>
        {{ promStep }}s</span
      >
    </p>

    <p v-if="error" class="banner-err">{{ error }}</p>

    <div
      v-if="!loading && metrics.length === 0 && !error"
      class="card muted"
    >
      Нет точек за период или Prometheus не вернул данные для этого
      <code class="inline">instance</code>
      . Проверьте scrape-конфиг и наличие метрик
      <code class="inline">node_*</code>
      .
    </div>

    <section v-if="latest" class="snapshot card">
      <h2 class="snap-title">Последняя точка ({{ formatTs(latest.recorded_at) }})</h2>
      <dl class="snap-grid">
        <div><dt>CPU</dt><dd>{{ latest.cpu_percent ?? '—' }}%</dd></div>
        <div><dt>Память</dt><dd>{{ latest.memory_percent ?? '—' }}%</dd></div>
        <div>
          <dt>RAM</dt>
          <dd>
            <template
              v-if="latest.memory_used_mb != null && latest.memory_total_mb != null"
            >
              {{ Math.round(latest.memory_used_mb) }} /
              {{ Math.round(latest.memory_total_mb) }} МиБ
            </template>
            <template v-else>—</template>
          </dd>
        </div>
        <div><dt>Диск</dt><dd>{{ latest.disk_used_percent ?? '—' }}%</dd></div>
        <div><dt>Load 1m</dt><dd>{{ latest.load_avg_1m ?? '—' }}</dd></div>
        <div><dt>TCP</dt><dd>{{ latest.tcp_established ?? '—' }}</dd></div>
        <div><dt>RX</dt><dd>{{ latest.net_rx_mbps ?? '—' }} Мбит/с</dd></div>
        <div><dt>TX</dt><dd>{{ latest.net_tx_mbps ?? '—' }} Мбит/с</dd></div>
        <div><dt>Uptime</dt><dd>{{ formatUptime(latest.uptime_seconds) }}</dd></div>
        <div>
          <dt>load_percent (БД)</dt>
          <dd>{{ selectedServer?.load_percent ?? '—' }}%</dd>
        </div>
      </dl>
    </section>

    <div v-if="metrics.length" class="charts">
      <div class="chart-card card">
        <h3 class="chart-title">CPU, память, диск (%)</h3>
        <div class="chart-wrap">
          <canvas ref="chartCpu" />
        </div>
      </div>
      <div class="chart-card card">
        <h3 class="chart-title">Сеть (Мбит/с)</h3>
        <div class="chart-wrap">
          <canvas ref="chartNet" />
        </div>
      </div>
      <div class="chart-card card">
        <h3 class="chart-title">TCP established</h3>
        <div class="chart-wrap">
          <canvas ref="chartTcp" />
        </div>
      </div>
      <div class="chart-card card">
        <h3 class="chart-title">Средняя нагрузка (1 мин)</h3>
        <div class="chart-wrap">
          <canvas ref="chartLoad" />
        </div>
      </div>
    </div>

    <p v-if="loading" class="muted pad">Загрузка…</p>
  </div>
</template>

<style scoped>
.page {
  padding: 1.25rem 1.5rem 2.5rem;
  max-width: 1200px;
  margin: 0 auto;
}
.head {
  margin-bottom: 1.25rem;
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
  margin: 0 0 0.35rem;
  font-size: 1.65rem;
  font-weight: 700;
  color: var(--text-h);
}
.sub {
  margin: 0;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.5;
  max-width: 52rem;
}
.sub a {
  color: var(--accent);
}
.inline {
  font-family: var(--mono);
  font-size: 0.82em;
  background: var(--surface-glass);
  padding: 0.1rem 0.35rem;
  border-radius: 6px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem;
  margin-bottom: 1rem;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  margin-bottom: 1rem;
  font-size: 0.88rem;
  color: var(--text);
}
.field-inline {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
}
.select {
  font: inherit;
  padding: 0.45rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass);
  color: var(--text);
  min-width: 14rem;
}
.btn-secondary {
  font: inherit;
  font-weight: 600;
  padding: 0.5rem 1rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass);
  color: var(--text-h);
  cursor: pointer;
  align-self: flex-end;
}
.btn-secondary:hover:not(:disabled) {
  border-color: var(--accent-border);
  background: var(--nav-link-hover-bg);
}
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.banner-err {
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 0.9rem;
  margin: 0 0 1rem;
}
.snapshot {
  margin-bottom: 1.25rem;
}
.snap-title {
  margin: 0 0 0.85rem;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-h);
}
.snap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.75rem 1.25rem;
  margin: 0;
}
.snap-grid dt {
  margin: 0;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.snap-grid dd {
  margin: 0.15rem 0 0;
  font-size: 1rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
}
.charts {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.chart-title {
  margin: 0 0 0.65rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-h);
}
.chart-wrap {
  height: 220px;
  position: relative;
}
.pad {
  margin-top: 1rem;
}
.muted {
  color: var(--muted);
}
</style>
