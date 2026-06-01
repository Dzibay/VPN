<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminBarChart from '../../components/AdminBarChart.vue'
import { fetchJson } from '../../api/client.js'
import { adminChartTheme } from '../../utils/adminChartTheme.js'

/** @typedef {{ subscription: string[]; one_time: string[] }} FinanceBuckets */

const loading = ref(false)
const error = ref(null)
/**
 * @type {import('vue').Ref<null | {
 *   months: string[]
 *   cash: FinanceBuckets
 *   cash_gross: FinanceBuckets
 *   spread: FinanceBuckets
 *   spread_gross: FinanceBuckets
 *   grand_total: string
 *   grand_total_gross: string
 *   payment_count: number
 * }>}
 */
const summary = ref(null)

/** «cash» — вся сумма в месяце платежа; «spread» — net_amount/months по месяцам подписки вперёд (UTC). */
const chartDistribution = ref(/** @type {'cash' | 'spread'} */ ('cash'))

/** По умолчанию — чистый доход после комиссии PSP. */
const useNetAmount = ref(true)

/** Нижний слой стека → верхний (порядок важен для stacked bar). */
const KIND_ORDER = /** @type {const} */ ([
  { field: 'subscription', label: 'Подписка' },
  { field: 'one_time', label: 'Разовая' },
])

const activeBuckets = computed(() => {
  const s = summary.value
  if (!s) return null
  const useNet = useNetAmount.value
  const raw =
    chartDistribution.value === 'spread'
      ? useNet
        ? s.spread
        : s.spread_gross ?? s.spread
      : useNet
        ? s.cash
        : s.cash_gross ?? s.cash
  if (!raw || typeof raw !== 'object') {
    return { subscription: [], one_time: [] }
  }
  return {
    subscription: Array.isArray(raw.subscription) ? raw.subscription : [],
    one_time: Array.isArray(raw.one_time) ? raw.one_time : [],
  }
})

const totalLabel = computed(() =>
  useNetAmount.value ? 'Чистый доход (после комиссии)' : 'Валовая сумма платежей',
)

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
  const rawTotal = useNetAmount.value
    ? summary.value?.grand_total
    : summary.value?.grand_total_gross ?? summary.value?.grand_total
  const n = rawTotal != null ? Number(String(rawTotal).replace(',', '.')) : 0
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

const financeChartLabels = computed(() => {
  const s = summary.value
  if (!s?.months?.length) return []
  return s.months.map(formatMonthLabel)
})

const financeChartDatasets = computed(() => {
  const s = summary.value
  const buckets = activeBuckets.value
  if (!s?.months?.length || !buckets) return []
  const theme = adminChartTheme()
  /** @type {Record<string, [number, number, number]>} */
  const rgbByField = {
    subscription: theme.accent,
    one_time: theme.trafficOrange,
  }
  return KIND_ORDER.map(({ field, label }) => ({
    label,
    data: parseAmounts(buckets[field]),
    rgb: rgbByField[field] ?? theme.accent,
    borderRadius: 4,
    maxBarThickness: 48,
  }))
})

function financeFormatValueTick(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}

/** @param {import('chart.js').TooltipItem<'bar'>[]} items */
function financeTooltipFooter(items) {
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
}

/** @param {import('chart.js').TooltipItem<'bar'>} item */
function financeTooltipFilter(item) {
  return Number(item.raw) > 0
}

async function load() {
  loading.value = true
  error.value = null
  summary.value = null
  try {
    summary.value = await fetchJson('/api/admin/payments/finance-summary')
  } catch (e) {
    error.value = e.message || String(e)
    summary.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
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

  <p v-if="loading && summary == null" class="muted">Загрузка сводки…</p>
  <p v-else-if="error" class="msg-err">{{ error }}</p>

  <template v-else-if="summary">
    <section class="total-card" aria-live="polite">
      <p class="total-label">{{ totalLabel }}</p>
      <p class="total-value">{{ totalFormatted }}&nbsp;₽</p>
      <label class="fee-row">
        <input v-model="useNetAmount" type="checkbox" class="fee-input" />
        <span class="fee-label">Учитывать комиссию</span>
      </label>
      <p class="total-meta">{{ paymentCountLabel }} записей</p>
    </section>

    <div v-if="!summary.months.length" class="empty-box">
      <p class="muted">Платежей пока нет — график появится после первых оплат.</p>
    </div>
    <AdminBarChart
      v-else
      preset="finance"
      aria-label="Доходы по месяцам (UTC), ₽"
      :has-data="summary.months.length > 0"
      :labels="financeChartLabels"
      :datasets="financeChartDatasets"
      stacked
      value-axis-title="₽"
      :format-value-tick="financeFormatValueTick"
      :get-tooltip-footer="financeTooltipFooter"
      :tooltip-filter="financeTooltipFilter"
    />
  </template>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
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

.fee-row {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0.65rem 0 0;
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-h);
  user-select: none;
}

.fee-input {
  margin: 0.15rem 0 0;
  width: 1rem;
  height: 1rem;
  accent-color: var(--accent, #58d68d);
  cursor: pointer;
  flex-shrink: 0;
}

.fee-label {
  line-height: 1.35;
}

.total-meta {
  margin: 0.5rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.45;
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
