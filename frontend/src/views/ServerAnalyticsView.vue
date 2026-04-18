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
/** @type {import('vue').Ref<{ source: string, instance: string, step_seconds: number, axis?: object, online_clients?: number | null, online_clients_from_prometheus?: boolean, points: any[] } | null>} */
const metricsBundle = ref(null)
const loading = ref(false)
const error = ref(null)

const chartCpu = ref(null)
const chartBottleneck = ref(null)
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
const axis = computed(() => metricsBundle.value?.axis ?? null)

const hourOptions = [
  { value: 6, label: '6 ч' },
  { value: 24, label: '24 ч' },
  { value: 72, label: '3 суток' },
  { value: 168, label: '7 суток' },
]

const selectedServer = computed(() =>
  servers.value.find((s) => s.id === serverId.value),
)

/** Строки для блока «конфигурация из БД» (админка) */
const serverParamRows = computed(() => {
  const s = selectedServer.value
  if (!s) return []
  const t = (v) => (v == null || v === '' ? '—' : String(v))
  const secret = (v) => {
    if (v == null || String(v).trim() === '') return '—'
    const x = String(v)
    return x.length > 24 ? `${x.slice(0, 12)}…${x.slice(-8)}` : x
  }
  return [
    { label: 'ID', value: t(s.id) },
    { label: 'Название', value: t(s.name) },
    { label: 'Host', value: t(s.host) },
    { label: 'Порт', value: t(s.port) },
    { label: 'Страна', value: t(s.country) },
    { label: 'Нагрузка в БД (подписка)', value: `${s.load_percent ?? 0}%` },
    { label: 'Активен', value: s.is_active ? 'Да' : 'Нет' },
    { label: 'ПО готово', value: s.provision_ready ? 'Да' : 'Нет' },
    { label: 'Статус провижининга', value: t(s.provision_status) },
    { label: 'Ошибка провижининга', value: t(s.provision_error) },
    { label: 'Job ID (RQ)', value: t(s.provision_job_id) },
    { label: 'Prometheus instance', value: t(s.prometheus_instance) },
    {
      label: 'Тариф канала (Мбит/с)',
      value: s.network_cap_mbps != null ? String(s.network_cap_mbps) : '—',
    },
    { label: 'VLESS UUID', value: t(s.vless_uuid) },
    { label: 'VLESS flow', value: t(s.vless_flow) },
    { label: 'REALITY dest', value: t(s.reality_dest) },
    { label: 'REALITY serverNames', value: t(s.reality_server_names) },
    { label: 'REALITY shortId', value: t(s.reality_short_id) },
    { label: 'REALITY fingerprint', value: t(s.reality_fingerprint) },
    { label: 'REALITY public key (pbk)', value: t(s.reality_public_key) },
    {
      label: 'REALITY private key',
      value: secret(s.reality_private_key),
    },
  ]
})

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

/** Округление для отображения */
function roundN(v, n = 1) {
  if (v == null || Number.isNaN(Number(v))) return null
  const x = Number(v)
  const p = 10 ** n
  return Math.round(x * p) / p
}

function fmtLoad(v) {
  const r = roundN(v, 2)
  return r == null ? '—' : `${r}`
}

function gridColor() {
  return 'rgba(139, 92, 246, 0.12)'
}

function tickColor() {
  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'rgba(230, 220, 245, 0.55)'
    : 'rgba(90, 80, 112, 0.45)'
}

function chartTooltipLabel(unit, decimals) {
  return (ctx) => {
    const v = ctx.parsed.y
    if (v == null || Number.isNaN(v)) return `${ctx.dataset.label}: —`
    const p = 10 ** decimals
    const r = Math.round(v * p) / p
    return `${ctx.dataset.label}: ${r}${unit}`
  }
}

function lineGradient(ctx, c1, c2) {
  if (!ctx?.chart?.ctx) return c1
  const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height || 220)
  g.addColorStop(0, c1)
  g.addColorStop(1, c2)
  return g
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

  const a = axis.value
  const labels = labelsFor(m)
  const rx = m.map((r) => r.net_rx_mbps)
  const tx = m.map((r) => r.net_tx_mbps)
  const netPeak = Math.max(
    0,
    ...rx.filter((x) => x != null),
    ...tx.filter((x) => x != null),
  )
  const netYMax =
    a?.network_max_mbps != null && a.network_max_mbps > 0
      ? a.network_max_mbps
      : Math.max(netPeak * 1.15, 10)

  const loads = m.map((r) => r.load_avg_1m).filter((x) => x != null)
  const loadPeak = loads.length ? Math.max(...loads) : 0
  const loadYMax =
    a?.load_y_max != null && a.load_y_max > 0
      ? a.load_y_max
      : Math.max(loadPeak * 1.2, 1)

  const tcps = m.map((r) => r.tcp_established).filter((x) => x != null)
  const tcpPeak = tcps.length ? Math.max(...tcps) : 0
  const tcpYMax =
    a?.tcp_y_max != null && a.tcp_y_max > 0
      ? a.tcp_y_max
      : Math.max(tcpPeak * 1.2, 16)

  const common = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          usePointStyle: true,
          pointStyle: 'circle',
          padding: 16,
          font: { family: 'var(--sans)', size: 12 },
          color: tickColor(),
        },
      },
      tooltip: {
        backgroundColor: 'rgba(26, 18, 38, 0.92)',
        titleFont: { family: 'var(--sans)', size: 12 },
        bodyFont: { family: 'var(--mono)', size: 12 },
        padding: 12,
        cornerRadius: 10,
        displayColors: true,
      },
    },
    scales: {
      x: {
        ticks: {
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 12,
          color: tickColor(),
          font: { size: 11 },
        },
        grid: { color: gridColor(), drawBorder: false },
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
    bottleneck: 'rgb(220, 38, 38)',
    netu: 'rgba(59, 130, 246, 0.65)',
    loadu: 'rgba(245, 158, 11, 0.7)',
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
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(99, 102, 241, 0.2)', 'rgba(99, 102, 241, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: 'Память %',
              data: m.map((r) => r.memory_percent),
              borderColor: palette.mem,
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(236, 72, 153, 0.15)', 'rgba(236, 72, 153, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: 'Диск %',
              data: m.map((r) => r.disk_used_percent),
              borderColor: palette.disk,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
          ],
        },
        options: {
          ...common,
          plugins: {
            ...common.plugins,
            tooltip: {
              ...common.plugins.tooltip,
              callbacks: {
                label: chartTooltipLabel('%', 1),
              },
            },
          },
          scales: {
            ...common.scales,
            y: {
              min: 0,
              max: 100,
              title: {
                display: true,
                text: '%',
                color: tickColor(),
                font: { size: 11, weight: '600' },
              },
              ticks: { color: tickColor() },
              grid: { color: gridColor(), drawBorder: false },
            },
          },
        },
      }),
    )
  }

  if (chartBottleneck.value) {
    chartInstances.push(
      new Chart(chartBottleneck.value, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Узкое место',
              data: m.map((r) => r.bottleneck_percent),
              borderColor: palette.bottleneck,
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(220, 38, 38, 0.2)', 'rgba(220, 38, 38, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              order: 0,
            },
            {
              label: 'Сеть % от лимита',
              data: m.map((r) => r.net_util_percent),
              borderColor: palette.netu,
              borderDash: [6, 4],
              fill: false,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 1.5,
              pointRadius: 0,
              pointHoverRadius: 3,
              order: 1,
            },
            {
              label: 'Очередь vs ядра (%)',
              data: m.map((r) => r.load_util_percent),
              borderColor: palette.loadu,
              borderDash: [4, 3],
              fill: false,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 1.5,
              pointRadius: 0,
              pointHoverRadius: 3,
              order: 1,
            },
          ],
        },
        options: {
          ...common,
          plugins: {
            ...common.plugins,
            tooltip: {
              ...common.plugins.tooltip,
              callbacks: {
                label: chartTooltipLabel('%', 1),
              },
            },
          },
          scales: {
            ...common.scales,
            y: {
              min: 0,
              max: 100,
              title: {
                display: true,
                text: '% утилизации',
                color: tickColor(),
                font: { size: 11, weight: '600' },
              },
              ticks: { color: tickColor() },
              grid: { color: gridColor(), drawBorder: false },
            },
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
              data: rx,
              borderColor: palette.rx,
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(34, 197, 94, 0.18)', 'rgba(34, 197, 94, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: 'TX Мбит/с',
              data: tx,
              borderColor: palette.tx,
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(59, 130, 246, 0.15)', 'rgba(59, 130, 246, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
          ],
        },
        options: {
          ...common,
          plugins: {
            ...common.plugins,
            tooltip: {
              ...common.plugins.tooltip,
              callbacks: {
                label: chartTooltipLabel(' Мбит/с', 2),
              },
            },
          },
          scales: {
            ...common.scales,
            y: {
              min: 0,
              max: netYMax,
              title: {
                display: true,
                text: 'Мбит/с',
                color: tickColor(),
                font: { size: 11, weight: '600' },
              },
              ticks: { color: tickColor() },
              grid: { color: gridColor(), drawBorder: false },
            },
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
              label: 'TCP established',
              data: m.map((r) => r.tcp_established),
              borderColor: palette.tcp,
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(168, 85, 247, 0.2)', 'rgba(168, 85, 247, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
          ],
        },
        options: {
          ...common,
          plugins: {
            ...common.plugins,
            tooltip: {
              ...common.plugins.tooltip,
              callbacks: {
                label: (ctx) => {
                  const v = ctx.parsed.y
                  if (v == null) return `${ctx.dataset.label}: —`
                  return `${ctx.dataset.label}: ${Math.round(v)}`
                },
              },
            },
          },
          scales: {
            ...common.scales,
            y: {
              min: 0,
              max: tcpYMax,
              title: {
                display: true,
                text: 'соединений',
                color: tickColor(),
                font: { size: 11, weight: '600' },
              },
              ticks: { color: tickColor() },
              grid: { color: gridColor(), drawBorder: false },
            },
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
              label: 'Load за 1 мин (не %)',
              data: m.map((r) => r.load_avg_1m),
              borderColor: palette.load,
              backgroundColor: (c) =>
                lineGradient(c, 'rgba(239, 68, 68, 0.18)', 'rgba(239, 68, 68, 0)'),
              fill: true,
              tension: 0.35,
              spanGaps: true,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
          ],
        },
        options: {
          ...common,
          plugins: {
            ...common.plugins,
            tooltip: {
              ...common.plugins.tooltip,
              callbacks: {
                label: chartTooltipLabel('', 2),
              },
            },
          },
          scales: {
            ...common.scales,
            y: {
              min: 0,
              max: loadYMax,
              title: {
                display: true,
                text: 'load',
                color: tickColor(),
                font: { size: 11, weight: '600' },
              },
              ticks: { color: tickColor() },
              grid: { color: gridColor(), drawBorder: false },
            },
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
    </header>

    <div class="toolbar glass">
      <label class="field-inline">
        <span>Сервер</span>
        <select
          v-model.number="serverId"
          class="select"
          :disabled="!servers.length"
          @change="onServerChange"
        >
          <option v-for="s in servers" :key="s.id" :value="s.id">
            {{ s.name || s.host }} · {{ s.host }}:{{ s.port }}
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
        class="btn-refresh"
        :disabled="loading || serverId == null"
        @click="loadMetrics"
      >
        Обновить
      </button>
    </div>

    <div v-if="metricsBundle" class="meta-strip glass">
      <span
        ><strong>instance</strong>
        <code class="inline">{{ promInstance }}</code></span
      >
      <span><strong>шаг</strong> {{ promStep }}s</span>
      <span v-if="axis?.cpu_cores"
        ><strong>CPU</strong> {{ axis.cpu_cores }} ядер</span
      >
      <span v-if="axis?.network_tariff_mbps"
        ><strong>Тариф</strong> {{ axis.network_tariff_mbps }} Мбит/с</span
      >
      <span v-if="axis?.network_nic_mbps"
        ><strong>NIC</strong> {{ roundN(axis.network_nic_mbps, 1) }} Мбит/с</span
      >
      <span v-if="axis?.network_max_mbps"
        ><strong>Ось сети</strong> {{ roundN(axis.network_max_mbps, 1) }} Мбит/с</span
      >
      <span v-if="metricsBundle?.online_clients_from_prometheus"
        ><strong>Онлайн</strong>
        {{
          metricsBundle.online_clients != null
            ? metricsBundle.online_clients
            : '—'
        }}
        (Prometheus)</span
      >
    </div>

    <p v-if="error" class="banner-err">{{ error }}</p>

    <div
      v-if="!loading && metrics.length === 0 && !error"
      class="glass empty-hint"
    >
      Нет точек за период или Prometheus не вернул данные для этого
      <code class="inline">instance</code>
      .
    </div>

    <p v-if="latest" class="snapshot-line glass">
      <strong>Время последней точки</strong>
      {{ formatTs(latest.recorded_at) }}
      <span class="snap-sep" aria-hidden="true">·</span>
      <strong>Uptime узла</strong>
      {{ formatUptime(latest.uptime_seconds) }}
      <span class="snap-muted"
        >— детали по CPU, памяти, сети и т.д. на графиках ниже.</span
      >
    </p>

    <details v-if="selectedServer" class="server-params glass">
      <summary class="server-params-summary">
        Параметры сервера (из БД)
        <span class="server-params-hint">VLESS, REALITY, провижининг…</span>
      </summary>
      <dl class="params-dl">
        <template v-for="row in serverParamRows" :key="row.label">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </template>
      </dl>
    </details>

    <div v-if="metrics.length" class="charts">
      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">Узкое место и запас</h3>
          <span class="chart-unit">0–100%</span>
        </div>
        <p class="chart-hint">
          Красная линия показывает, что упирается в потолок первым: процессор, память, диск, сеть
          или очередь задач — берётся худший из этих показателей. Пунктир: только сеть относительно
          вашего лимита (тариф или порт) и очередь задач, переведённая в проценты от числа ядер
          (если «очередь» сравнялась с числом ядер — это как «все ядра заняты», 100%).
        </p>
        <div class="chart-wrap">
          <canvas ref="chartBottleneck" />
        </div>
      </div>
      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">CPU, память, диск</h3>
          <span class="chart-unit">0–100%</span>
        </div>
        <p class="chart-hint">
          Занятость процессора, доля занятой RAM и заполненность диска под корнем. Все три шкалы
          0–100%, чтобы их было удобно сравнивать.
        </p>
        <div class="chart-wrap">
          <canvas ref="chartCpu" />
        </div>
      </div>
      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">Сеть</h3>
          <span class="chart-unit">{{
            axis?.network_max_mbps != null
              ? `${roundN(axis.network_max_mbps, 1)} Мбит/с`
              : 'по данным'
          }}</span>
        </div>
        <p class="chart-hint">
          Входящий и исходящий трафик по всем сетевым интерфейсам (кроме localhost), в Мбит/с.
          Верх графика — ваш тариф из карточки сервера, иначе скорость порта; если ничего нет — по
          пику за период.
        </p>
        <div class="chart-wrap chart-wrap-tall">
          <canvas ref="chartNet" />
        </div>
      </div>
      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">TCP established</h3>
          <span class="chart-unit">до {{ axis?.tcp_y_max != null ? Math.round(axis.tcp_y_max) : 'авто' }}</span>
        </div>
        <p class="chart-hint">
          Сколько TCP-соединений сейчас в состоянии «установлено». Не то же самое, что число
          VPN-пользователей, но по всплескам видно, насколько оживлённо на узле.
        </p>
        <div class="chart-wrap">
          <canvas ref="chartTcp" />
        </div>
      </div>
      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">Очередь задач (load average, 1 мин)</h3>
          <span class="chart-unit"
            >макс. ось ≈ {{ axis?.load_y_max != null ? fmtLoad(axis.load_y_max) : 'авто'
            }}{{ axis?.cpu_cores ? ` (${axis.cpu_cores} CPU)` : '' }}</span
          >
        </div>
        <p class="chart-hint">
          Та же «очередь задач», что и оранжевый пунктир на первом графике, но в «родных» числах
          Linux: это не проценты. Ориентир — если значение приближается к числу ядер, система
          обычно уже плотно загружена.
        </p>
        <div class="chart-wrap">
          <canvas ref="chartLoad" />
        </div>
      </div>
    </div>

    <p v-if="loading" class="loading-line">Загрузка…</p>
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
  margin: 0;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.55;
  max-width: 54rem;
}
.sub a {
  color: var(--accent);
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
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1.1rem;
  padding: 1rem 1.15rem;
  margin-bottom: 1rem;
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
.field-inline {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.select {
  font: inherit;
  padding: 0.5rem 0.75rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text);
  min-width: 15rem;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
}
.btn-refresh {
  font: inherit;
  font-weight: 700;
  padding: 0.55rem 1.15rem;
  border-radius: 12px;
  border: none;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%);
  color: var(--on-accent);
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(139, 92, 246, 0.35);
  align-self: flex-end;
}
.btn-refresh:hover:not(:disabled) {
  filter: brightness(1.06);
}
.btn-refresh:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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
.empty-hint {
  padding: 1.25rem 1.25rem;
  margin-bottom: 1rem;
  color: var(--muted);
  font-size: 0.92rem;
}
.snapshot-line {
  margin: 0 0 1rem;
  padding: 0.75rem 1rem;
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--text);
}
.snapshot-line strong {
  color: var(--muted);
  font-weight: 700;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-right: 0.35rem;
}
.snap-sep {
  margin: 0 0.5rem;
  color: var(--card-border);
  font-weight: 300;
}
.snap-muted {
  display: inline;
  margin-left: 0.35rem;
  font-size: 0.8rem;
  color: var(--muted);
  font-weight: 500;
}
.server-params {
  margin-bottom: 1.25rem;
  padding: 0;
  overflow: hidden;
}
.server-params-summary {
  cursor: pointer;
  list-style: none;
  padding: 0.85rem 1.1rem;
  font-weight: 800;
  font-size: 0.92rem;
  color: var(--text-h);
  font-family: var(--heading);
}
.server-params-summary::-webkit-details-marker {
  display: none;
}
.server-params-summary::before {
  content: '▸';
  display: inline-block;
  margin-right: 0.5rem;
  opacity: 0.55;
  transition: transform 0.15s ease;
}
.server-params[open] .server-params-summary::before {
  transform: rotate(90deg);
}
.server-params-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: none;
  letter-spacing: 0;
}
.params-dl {
  display: grid;
  grid-template-columns: minmax(7rem, 11rem) 1fr;
  gap: 0.35rem 1rem;
  padding: 0 1.1rem 1rem;
  margin: 0;
  font-size: 0.82rem;
  border-top: 1px solid var(--card-border);
  padding-top: 0.85rem;
}
.params-dl dt {
  margin: 0;
  color: var(--muted);
  font-weight: 700;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  align-self: start;
  padding-top: 0.12rem;
}
.params-dl dd {
  margin: 0;
  color: var(--text-h);
  font-family: var(--mono);
  font-size: 0.8rem;
  word-break: break-word;
}
.charts {
  display: flex;
  flex-direction: column;
  gap: 1.35rem;
}
.chart-panel {
  padding: 1.1rem 1.2rem 1.25rem;
}
.chart-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem 1rem;
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
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.chart-hint {
  margin: 0 0 0.75rem;
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 52rem;
}
.chart-wrap {
  height: 240px;
  position: relative;
}
.chart-wrap-tall {
  height: 280px;
}
.loading-line {
  margin-top: 1.25rem;
  text-align: center;
  color: var(--muted);
  font-weight: 600;
}
</style>
