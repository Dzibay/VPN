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
const chartTrafficUsers = ref(null)

/** @type {import('vue').Ref<{ server_id: number, collected_at: string | null, collect_error: string | null, collect_detail?: object | null, users: Array<{ user_id: number, telegram_id: string | null, up_bytes: number, down_bytes: number, total_bytes: number }> } | null>} */
const userTrafficBundle = ref(null)
const userTrafficLoading = ref(false)
/** true только при запросе с collect=true (SSH), чтобы различать «тихую» подгрузку из БД */
const userTrafficCollectPending = ref(false)
const userTrafficError = ref(null)
/** Пока true — идёт collect=true (SSH); не вызывать loadUserTraffic(false) из loadMetrics, иначе сбросится надпись SSH и начнётся гонка. */
const userTrafficSSHInFlight = ref(false)

/** Счётчик параллельных запросов трафика — только последний обновляет UI. */
let userTrafficFetchGen = 0

/** Интервал опроса RQ-задачи сбора трафика (слишком частый — сотни строк в access-логе uvicorn). */
const USER_TRAFFIC_JOB_POLL_MS = 2500

/** Таймаут fetch (чуть больше бэкенда XRAY_STATS_SSH_TIMEOUT_SECONDS). Полифилл, если нет AbortSignal.timeout. */
function abortSignalAfterMs(ms) {
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    return AbortSignal.timeout(ms)
  }
  const c = new AbortController()
  setTimeout(() => c.abort(), ms)
  return c.signal
}

/** @type {Chart[]} */
let chartInstances = []
/** @type {Chart | null} */
let chartTrafficUsersInstance = null

function destroyCharts() {
  chartInstances.forEach((c) => c.destroy())
  chartInstances = []
  if (chartTrafficUsersInstance) {
    chartTrafficUsersInstance.destroy()
    chartTrafficUsersInstance = null
  }
}

const metrics = computed(() => metricsBundle.value?.points ?? [])
const axis = computed(() => metricsBundle.value?.axis ?? null)

const hourOptions = [
  { value: 1, label: '1 ч' },
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

const userTrafficCollectedLabel = computed(() => {
  const t = userTrafficBundle.value?.collected_at
  if (!t) return ''
  return formatTs(t)
})

const userTrafficLoadingHeadline = computed(() => {
  if (!userTrafficLoading.value) return ''
  if (userTrafficCollectPending.value) {
    const h = selectedServer.value?.host
    return h
      ? `Воркер RQ: узел ${h} — SSH + xray api statsquery…`
      : 'Воркер RQ: выполняется сбор трафика (SSH + statsquery)…'
  }
  return 'Загрузка трафика из БД…'
})

/** Подсказки при SSH-опросе: цепочка не «порт с интернета», а localhost на VPS после SSH */
const userTrafficLoadingHints = computed(() => {
  if (!userTrafficLoading.value || !userTrafficCollectPending.value) return []
  return [
    'Запрос ставит задачу в очередь Redis; SSH выполняет процесс воркера (как при установке Xray) — на той же машине должен быть запущен «python -m worker.run» и доступен Redis.',
    'На узле после SSH выполняется xray api statsquery к 127.0.0.1 (Stats API). Снаружи этот порт открывать не нужно.',
    'Долго висит — проверьте воркер и ключ PROVISION_SSH_KEY_PATH на его машине; в «Детали опроса» — stdout/stderr и код выхода.',
  ]
})

const userTrafficCollectDetail = computed(
  () => userTrafficBundle.value?.collect_detail ?? null,
)

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
  return 'rgba(88, 214, 141, 0.12)'
}

function tickColor() {
  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'rgba(200, 228, 210, 0.55)'
    : 'rgba(45, 85, 65, 0.45)'
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
      hours.value <= 3
        ? 15
        : hours.value <= 24
          ? 60
          : hours.value <= 72
            ? 120
            : 180
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
  if (!userTrafficSSHInFlight.value) {
    await loadUserTraffic(false)
  }
}

function userTrafficLabel(u) {
  if (u.telegram_id && String(u.telegram_id).trim()) return String(u.telegram_id)
  return `id ${u.user_id}`
}

function drawTrafficUserChart() {
  if (chartTrafficUsers.value == null) return
  if (chartTrafficUsersInstance) {
    chartTrafficUsersInstance.destroy()
    chartTrafficUsersInstance = null
  }
  const bundle = userTrafficBundle.value
  if (!bundle?.users?.length) return
  const users = [...bundle.users].sort((a, b) => b.total_bytes - a.total_bytes)
  const mib = (b) => b / (1024 * 1024)
  chartTrafficUsersInstance = new Chart(chartTrafficUsers.value, {
    type: 'bar',
    data: {
      labels: users.map((u) => userTrafficLabel(u)),
      datasets: [
        {
          label: 'Исходящий к клиенту (down), МиБ',
          data: users.map((u) => mib(u.down_bytes)),
          backgroundColor: 'rgba(88, 214, 141, 0.78)',
        },
        {
          label: 'От клиента (up), МиБ',
          data: users.map((u) => mib(u.up_bytes)),
          backgroundColor: 'rgba(34, 197, 94, 0.78)',
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
            text: 'МиБ',
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

/**
 * @param {boolean} collect — всегда false: только строки из БД. Сбор с узла — отдельно loadUserTrafficFromNode (RQ).
 */
async function loadUserTraffic(collect = false) {
  if (serverId.value == null) return
  const gen = ++userTrafficFetchGen
  userTrafficLoading.value = true
  userTrafficCollectPending.value = collect
  userTrafficError.value = null
  try {
    const fetchOpts = {
      signal: abortSignalAfterMs(45000),
    }
    const data = await fetchJson(
      `/api/servers/${serverId.value}/user-traffic?collect=${collect}`,
      fetchOpts,
    )
    if (gen !== userTrafficFetchGen) return
    userTrafficBundle.value = data
  } catch (e) {
    if (gen !== userTrafficFetchGen) return
    const name = e?.name || ''
    if (name === 'AbortError' || name === 'TimeoutError') {
      userTrafficError.value = 'Таймаут запроса к API.'
    } else {
      userTrafficError.value = e.message || String(e)
    }
    userTrafficBundle.value = null
  } finally {
    if (gen === userTrafficFetchGen) {
      userTrafficLoading.value = false
      userTrafficCollectPending.value = false
    }
  }
  if (gen !== userTrafficFetchGen) return
  await nextTick()
  drawTrafficUserChart()
}

async function loadUserTrafficFromNode() {
  if (serverId.value == null) return
  const gen = ++userTrafficFetchGen
  userTrafficLoading.value = true
  userTrafficCollectPending.value = true
  userTrafficSSHInFlight.value = true
  userTrafficError.value = null
  try {
    const enq = await fetchJson(
      `/api/servers/${serverId.value}/user-traffic/collect`,
      { method: 'POST' },
    )
    if (gen !== userTrafficFetchGen) return
    const jobId = enq.job_id
    const deadline = Date.now() + 130000
    let poll = null
    while (Date.now() < deadline) {
      poll = await fetchJson(
        `/api/servers/${serverId.value}/user-traffic/collect-jobs/${jobId}`,
      )
      if (gen !== userTrafficFetchGen) return
      if (poll.status === 'finished' || poll.status === 'failed') break
      await new Promise((r) => setTimeout(r, USER_TRAFFIC_JOB_POLL_MS))
    }
    if (gen !== userTrafficFetchGen) return
    if (!poll) {
      userTrafficError.value = 'Нет ответа от опроса задачи'
      userTrafficBundle.value = null
      return
    }
    if (poll.status === 'failed') {
      userTrafficError.value =
        poll.job_error || poll.bundle?.collect_error || 'Ошибка задачи воркера'
      userTrafficBundle.value = poll.bundle
      return
    }
    if (poll.status === 'finished' && poll.bundle) {
      userTrafficBundle.value = poll.bundle
    } else if (poll.status === 'queued' || poll.status === 'started') {
      userTrafficError.value =
        'Таймаут ожидания воркера. Запустите процесс «python -m worker.run» и проверьте Redis.'
      userTrafficBundle.value = null
    } else {
      userTrafficError.value = 'Нет данных после сбора'
    }
  } catch (e) {
    if (gen !== userTrafficFetchGen) return
    const name = e?.name || ''
    if (name === 'AbortError' || name === 'TimeoutError') {
      userTrafficError.value = 'Таймаут запроса к API.'
    } else {
      userTrafficError.value = e.message || String(e)
    }
    userTrafficBundle.value = null
  } finally {
    if (gen === userTrafficFetchGen) {
      userTrafficLoading.value = false
      userTrafficCollectPending.value = false
      userTrafficSSHInFlight.value = false
    }
  }
  if (gen !== userTrafficFetchGen) return
  await nextTick()
  drawTrafficUserChart()
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
        backgroundColor: 'rgba(4, 12, 9, 0.94)',
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
    tx: 'rgb(45, 179, 157)',
    tcp: 'rgb(168, 85, 247)',
    load: 'rgb(239, 68, 68)',
    bottleneck: 'rgb(220, 38, 38)',
    netu: 'rgba(45, 179, 157, 0.65)',
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
                lineGradient(c, 'rgba(45, 179, 157, 0.18)', 'rgba(45, 179, 157, 0)'),
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

watch(serverId, () => {
  userTrafficFetchGen++
  userTrafficSSHInFlight.value = false
  userTrafficLoading.value = false
  userTrafficCollectPending.value = false
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
        :disabled="loading || userTrafficLoading || serverId == null"
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

    <div v-if="serverId != null" class="chart-panel glass traffic-users-block">
      <div class="chart-head traffic-chart-head">
        <h3 class="chart-title">Трафик по пользователям (Xray)</h3>
        <div class="traffic-chart-actions">
          <span v-if="userTrafficCollectedLabel" class="chart-unit">{{
            userTrafficCollectedLabel
          }}</span>
          <button
            type="button"
            class="btn-traffic-sync"
            :disabled="userTrafficLoading || serverId == null"
            @click="loadUserTrafficFromNode"
          >
            {{
              userTrafficLoading ? 'Опрос узла…' : 'Собрать с узла (SSH)'
            }}
          </button>
        </div>
      </div>
      <p class="chart-hint">
        По умолчанию — данные из БД (быстро). Кнопка справа: SSH на узел, затем на самом VPS —
        <code class="inline">xray api statsquery</code> к
        <code class="inline">127.0.0.1</code> (Stats API). Порт API не должен быть открыт в интернет; его
        слушает только Xray на localhost. Сбор ставит задачу в очередь воркера (SSH с той же машины, что и провижининг). Метки в Xray:
        <code class="inline">u12@vpn</code> = id пользователя в БД.
      </p>
      <p v-if="userTrafficBundle?.collect_error" class="banner-warn">
        {{ userTrafficBundle.collect_error }}
      </p>
      <p v-if="userTrafficError" class="banner-err">{{ userTrafficError }}</p>
      <div v-if="userTrafficLoading" class="traffic-loading-block">
        <p class="loading-line">{{ userTrafficLoadingHeadline }}</p>
        <ul
          v-if="userTrafficLoadingHints.length"
          class="loading-hint-list"
        >
          <li v-for="(line, i) in userTrafficLoadingHints" :key="i">
            {{ line }}
          </li>
        </ul>
      </div>
      <div
        v-else
        class="chart-wrap chart-wrap-tall traffic-users-canvas-wrap"
      >
        <canvas ref="chartTrafficUsers" />
      </div>
      <details
        v-if="userTrafficCollectDetail && !userTrafficLoading"
        class="traffic-collect-detail"
      >
        <summary class="traffic-collect-summary">
          Детали опроса узла (SSH)
          <span
            v-if="userTrafficCollectDetail.parsed_users != null"
            class="traffic-collect-badge"
            >пользователей в ответе: {{ userTrafficCollectDetail.parsed_users }}</span
          >
        </summary>
        <dl class="traffic-collect-dl">
          <template v-if="userTrafficCollectDetail.ssh_target">
            <dt>SSH</dt>
            <dd>
              <code class="inline">{{ userTrafficCollectDetail.ssh_target }}</code>
              <span v-if="userTrafficCollectDetail.ssh_port != null" class="traffic-collect-meta">
                порт {{ userTrafficCollectDetail.ssh_port }}</span
              >
            </dd>
          </template>
          <template v-if="userTrafficCollectDetail.xray_api_listen">
            <dt>Stats API на узле</dt>
            <dd>
              <code class="inline">{{ userTrafficCollectDetail.xray_api_listen }}</code>
            </dd>
          </template>
          <template v-if="userTrafficCollectDetail.remote_command">
            <dt>Удалённая команда</dt>
            <dd class="traffic-collect-cmd">{{ userTrafficCollectDetail.remote_command }}</dd>
          </template>
          <template
            v-if="
              userTrafficCollectDetail.exit_code != null ||
              userTrafficCollectDetail.duration_ms != null
            "
          >
            <dt>Результат</dt>
            <dd class="traffic-collect-meta">
              <span v-if="userTrafficCollectDetail.exit_code != null"
                >код {{ userTrafficCollectDetail.exit_code }}</span
              >
              <span
                v-if="
                  userTrafficCollectDetail.exit_code != null &&
                  userTrafficCollectDetail.duration_ms != null
                "
                class="traffic-collect-sep"
                aria-hidden="true"
                >·</span
              >
              <span v-if="userTrafficCollectDetail.duration_ms != null"
                >{{ Math.round(userTrafficCollectDetail.duration_ms) }} мс</span
              >
            </dd>
          </template>
          <template v-if="userTrafficCollectDetail.skipped_reason">
            <dt>Примечание</dt>
            <dd>{{ userTrafficCollectDetail.skipped_reason }}</dd>
          </template>
        </dl>
        <div v-if="userTrafficCollectDetail.stdout_preview" class="traffic-collect-pre-wrap">
          <div class="traffic-collect-pre-label">stdout (фрагмент)</div>
          <pre class="traffic-collect-pre">{{ userTrafficCollectDetail.stdout_preview }}</pre>
        </div>
        <div v-if="userTrafficCollectDetail.stderr_preview" class="traffic-collect-pre-wrap">
          <div class="traffic-collect-pre-label">stderr (фрагмент)</div>
          <pre class="traffic-collect-pre">{{ userTrafficCollectDetail.stderr_preview }}</pre>
        </div>
      </details>
      <p
        v-if="
          !userTrafficLoading &&
          userTrafficBundle &&
          userTrafficBundle.users &&
          userTrafficBundle.users.length === 0
        "
        class="chart-hint muted-hint"
      >
        Нет строк в БД для этого узла — после синхронизации Xray и подключений клиентов данные
        появятся.
      </p>
    </div>

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
  box-shadow: 0 4px 14px var(--accent-glow);
  align-self: flex-end;
}
.btn-refresh:hover:not(:disabled) {
  filter: brightness(1.06);
}
.btn-refresh:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.banner-warn {
  padding: 0.85rem 1.1rem;
  border-radius: 14px;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.42);
  color: var(--text-h);
  font-size: 0.88rem;
  margin: 0 0 1rem;
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
.traffic-chart-head {
  flex-wrap: wrap;
  gap: 0.75rem;
}
.traffic-chart-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
  margin-left: auto;
}
.btn-traffic-sync {
  font: inherit;
  font-weight: 700;
  font-size: 0.82rem;
  padding: 0.45rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  cursor: pointer;
  white-space: nowrap;
}
.btn-traffic-sync:hover:not(:disabled) {
  border-color: var(--accent-border);
  color: var(--accent);
}
.btn-traffic-sync:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.traffic-users-block {
  margin-bottom: 1.15rem;
}
.traffic-users-canvas-wrap {
  min-height: 280px;
}
.muted-hint {
  margin-top: 0.65rem;
  color: var(--muted);
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
.traffic-loading-block {
  margin-top: 1rem;
  padding: 0.75rem 0.5rem 1rem;
}
.loading-line {
  margin: 0;
  text-align: center;
  color: var(--text-h);
  font-weight: 700;
  font-size: 0.92rem;
  line-height: 1.4;
}
.loading-hint-list {
  margin: 0.65rem 0 0;
  padding: 0 0 0 1.15rem;
  max-width: 46rem;
  margin-left: auto;
  margin-right: auto;
  text-align: left;
  color: var(--muted);
  font-size: 0.76rem;
  line-height: 1.5;
}
.loading-hint-list li {
  margin: 0.35rem 0;
}
.traffic-collect-detail {
  margin-top: 1rem;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: rgba(0, 0, 0, 0.12);
}
.traffic-collect-summary {
  cursor: pointer;
  list-style: none;
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text-h);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
.traffic-collect-summary::-webkit-details-marker {
  display: none;
}
.traffic-collect-summary::before {
  content: '▸';
  display: inline-block;
  margin-right: 0.35rem;
  opacity: 0.55;
  transition: transform 0.15s ease;
}
.traffic-collect-detail[open] .traffic-collect-summary::before {
  transform: rotate(90deg);
}
.traffic-collect-badge {
  font-weight: 600;
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.traffic-collect-dl {
  display: grid;
  grid-template-columns: minmax(6rem, 9rem) 1fr;
  gap: 0.35rem 0.75rem;
  margin: 0.75rem 0 0;
  padding: 0;
  font-size: 0.78rem;
}
.traffic-collect-dl dt {
  margin: 0;
  color: var(--muted);
  font-weight: 700;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.traffic-collect-dl dd {
  margin: 0;
  color: var(--text);
  word-break: break-word;
}
.traffic-collect-cmd {
  font-family: var(--mono);
  font-size: 0.74rem;
  line-height: 1.4;
  white-space: pre-wrap;
}
.traffic-collect-meta {
  font-size: 0.78rem;
  color: var(--muted);
}
.traffic-collect-sep {
  margin: 0 0.35rem;
  color: var(--card-border);
}
.traffic-collect-pre-wrap {
  margin-top: 0.65rem;
}
.traffic-collect-pre-label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.traffic-collect-pre {
  margin: 0;
  padding: 0.55rem 0.65rem;
  max-height: 220px;
  overflow: auto;
  font-family: var(--mono);
  font-size: 0.72rem;
  line-height: 1.35;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--card-border);
  color: var(--text-h);
}
</style>
