<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import Chart from '../utils/chartSetup.js'
import { fetchJson } from '../api/client.js'
import { adminChartTheme, rgba } from '../utils/adminChartTheme.js'

/** @typedef {{ subscription: string[]; one_time: string[] }} FinanceBuckets */

const loading = ref(false)
const error = ref(null)
/**
 * @type {import('vue').Ref<null | {
 *   months: string[]
 *   cash: FinanceBuckets
 *   spread: FinanceBuckets
 *   grand_total: string
 *   payment_count: number
 * }>}
 */
const summary = ref(null)

/** «cash» — вся сумма в месяце платежа; «spread» — amount/months по месяцам подписки вперёд (UTC). */
const chartDistribution = ref(/** @type {'cash' | 'spread'} */ ('cash'))

/** @type {Chart | null} */
let chartInstance = null

const chartCanvas = ref(null)

/** Нижний слой стека → верхний (порядок важен для stacked bar). */
const KIND_ORDER = /** @type {const} */ ([
  { field: 'subscription', label: 'Подписка' },
  { field: 'one_time', label: 'Разовая' },
])

const activeBuckets = computed(() => {
  const s = summary.value
  if (!s) return null
  const raw = chartDistribution.value === 'spread' ? s.spread : s.cash
  if (!raw || typeof raw !== 'object') {
    return { subscription: [], one_time: [] }
  }
  return {
    subscription: Array.isArray(raw.subscription) ? raw.subscription : [],
    one_time: Array.isArray(raw.one_time) ? raw.one_time : [],
  }
})

function formatMonthLabel(ym) {
  const [ys, ms] = String(ym).split('-')
  const y = Number(ys)
  const m = Number(ms)
  if (!y || !m || m < 1 || m > 12) return String(ym)
  const d = new Date(Date.UTC(y, m - 1, 1))
  return d.toLocaleDateString('ru-RU', {
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

const totalFormatted = computed(() => {
  const g = summary.value?.grand_total
  const n = g != null ? Number(String(g).replace(',', '.')) : 0
  if (!Number.isFinite(n)) return '0,00'
  return n.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
})

const paymentCountLabel = computed(() => {
  const n = summary.value?.payment_count
  if (n == null || !Number.isFinite(Number(n))) return '0'
  return Number(n).toLocaleString('ru-RU')
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
  const s = summary.value
  const buckets = activeBuckets.value
  if (!s?.months?.length || !buckets) return

  const theme = adminChartTheme()
  /** @type {Record<string, [number, number, number]>} */
  const rgbByField = {
    subscription: theme.accent,
    one_time: theme.trafficOrange,
  }

  const labels = s.months.map(formatMonthLabel)

  const datasets = KIND_ORDER.map(({ field, label }) => ({
    label,
    data: parseAmounts(buckets[field]),
    backgroundColor: rgba(rgbByField[field] ?? theme.accent, 0.82),
    borderRadius: 4,
    borderSkipped: false,
    maxBarThickness: 48,
  }))

  chartInstance = new Chart(el, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      datasets: {
        bar: {
          categoryPercentage: 0.65,
          barPercentage: 0.9,
        },
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: tickColor(),
            font: { family: 'var(--sans)', size: 12 },
            boxWidth: 14,
            boxHeight: 14,
          },
        },
        tooltip: {
          backgroundColor: 'rgba(4, 12, 9, 0.94)',
          titleFont: { family: 'var(--sans)', size: 12 },
          bodyFont: { family: 'var(--mono)', size: 12 },
          filter: (item) => Number(item.raw) > 0,
          callbacks: {
            footer(items) {
              const first = items?.[0]
              if (!first) return ''
              const idx = first.dataIndex
              const chart = first.chart
              let sum = 0
              for (const ds of chart.data.datasets) {
                const v = Number(ds.data[idx])
                if (Number.isFinite(v)) sum += v
              }
              return `Всего: ${sum.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
            },
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: tickColor(), maxRotation: 45, minRotation: 0 },
          grid: { color: gridColor(), drawBorder: false },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          ticks: {
            color: tickColor(),
            callback(v) {
              const n = Number(v)
              if (!Number.isFinite(n)) return ''
              return n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
            },
          },
          grid: { color: gridColor(), drawBorder: false },
          title: {
            display: true,
            text: '₽',
            color: tickColor(),
            font: { size: 11, weight: '600' },
          },
        },
      },
    },
  })
}

async function load() {
  loading.value = true
  error.value = null
  summary.value = null
  destroyChart()
  try {
    summary.value = await fetchJson('/api/admin/payments/finance-summary')
  } catch (e) {
    error.value = e.message || String(e)
    summary.value = null
  } finally {
    loading.value = false
  }
  await nextTick()
  drawChart()
}

watch(chartDistribution, async () => {
  await nextTick()
  drawChart()
})

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <AdminStaffShell title="Финансы">
    <template #headerExtras>
      <div class="head-row">
        <h2 class="section-heading">Доходы по месяцам</h2>
        <div class="head-actions">
          <div
            class="dist-toggle"
            role="group"
            aria-label="Как считать суммы по месяцам на графике"
          >
            <button
              type="button"
              class="dist-btn"
              :class="{ 'dist-btn--active': chartDistribution === 'cash' }"
              :disabled="loading"
              @click="chartDistribution = 'cash'"
            >
              По дате платежа
            </button>
            <button
              type="button"
              class="dist-btn"
              :class="{ 'dist-btn--active': chartDistribution === 'spread' }"
              :disabled="loading"
              @click="chartDistribution = 'spread'"
            >
              По месяцам оплаты
            </button>
          </div>
          <button type="button" class="btn-secondary" :disabled="loading" @click="load">
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </template>

    <p v-if="loading && summary == null" class="muted">Загрузка сводки…</p>
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <template v-else-if="summary">
      <section class="total-card" aria-live="polite">
        <p class="total-label">Сумма всех платежей</p>
        <p class="total-value">{{ totalFormatted }}&nbsp;₽</p>
        <p class="total-meta">
          {{ paymentCountLabel }} записей
        </p>
      </section>

      <div v-if="!summary.months.length" class="empty-box">
        <p class="muted">Платежей пока нет — график появится после первых оплат.</p>
      </div>
      <div v-else class="chart-wrap">
        <canvas ref="chartCanvas" />
      </div>
    </template>
  </AdminStaffShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}

.section-heading {
  margin: 0;
  font-size: 1.05rem;
  color: var(--text-h);
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.dist-toggle {
  display: inline-flex;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  overflow: hidden;
  background: var(--surface);
}

.dist-btn {
  margin: 0;
  padding: 0.45rem 0.75rem;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  white-space: nowrap;
}

.dist-btn:hover:not(:disabled) {
  color: var(--text-h);
  background: rgba(127, 127, 127, 0.08);
}

.dist-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.dist-btn--active {
  color: var(--text-h);
  background: rgba(88, 214, 141, 0.14);
}

.total-card {
  margin: 0 0 1.25rem;
  padding: 1rem 1.1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass);
  max-width: 36rem;
}

.total-label {
  margin: 0 0 0.35rem;
  font-size: 0.82rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.total-value {
  margin: 0;
  font-size: 1.65rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  letter-spacing: -0.02em;
}

.total-meta {
  margin: 0.5rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.45;
}

.legend-hint {
  display: inline;
}

.chart-wrap {
  position: relative;
  width: 100%;
  height: min(420px, 55vh);
  min-height: 280px;
}

.empty-box {
  padding: 1.5rem 1rem;
  border-radius: 12px;
  border: 1px dashed var(--card-border);
  text-align: center;
}

.muted {
  color: var(--muted);
}

.msg-err {
  color: var(--danger);
  margin-bottom: 0.75rem;
}
</style>
