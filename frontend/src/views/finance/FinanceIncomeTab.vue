<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminBarChartPanel from '../../components/AdminBarChartPanel.vue'
import AppRefreshButton from '../../components/AppRefreshButton.vue'
import StateNote from '../../components/StateNote.vue'
import { fetchJson } from '../../api/client.js'
import { adminChartTheme } from '../../utils/adminChartTheme.js'
import {
  chartBarPositiveTooltipFilter,
  chartBarStackedMoneyTooltipFooter,
  formatChartMoneyTick,
} from '../../utils/adminChartFormatters.js'

/** @typedef {{ subscription: string[]; one_time: string[] }} FinanceBuckets */

const loading = ref(false)
const error = ref(null)
/**
 * @type {import('vue').Ref<null | {
 *   months: string[]
 *   days: string[]
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
/** Дневная сводка для средних (UTC); при режиме «По дням» совпадает с summary. */
const dailySummary = ref(null)

/** «cash» — вся сумма в месяце платежа; «spread» — net_amount/months по месяцам подписки; «daily» — по дням UTC. */
const chartDistribution = ref(/** @type {'cash' | 'spread' | 'daily'} */ ('daily'))

/** По умолчанию — чистый доход после комиссии PSP. */
const useNetAmount = ref(true)

const isDailyView = computed(() => chartDistribution.value === 'daily')

const sectionHeading = computed(() =>
  isDailyView.value ? 'Доходы по дням' : 'Доходы по месяцам',
)

/** Нижний слой стека → верхний (порядок важен для stacked bar). */
const KIND_ORDER = /** @type {const} */ ([
  { field: 'subscription', label: 'Подписка' },
  { field: 'one_time', label: 'Разовая' },
])

const periodKeys = computed(() => {
  const s = summary.value
  if (!s) return []
  if (isDailyView.value) return Array.isArray(s.days) ? s.days : []
  return Array.isArray(s.months) ? s.months : []
})

const activeBuckets = computed(() => {
  const s = summary.value
  if (!s) return null
  const useNet = useNetAmount.value
  const raw =
    isDailyView.value || chartDistribution.value === 'cash'
      ? useNet
        ? s.cash
        : s.cash_gross ?? s.cash
      : useNet
        ? s.spread
        : s.spread_gross ?? s.spread
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

function formatDayLabel(iso) {
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric',
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
  return formatMoney(n)
})

const paymentCountLabel = computed(() => {
  const n = summary.value?.payment_count
  if (n == null || !Number.isFinite(Number(n))) return '0'
  return Number(n).toLocaleString('ru-RU')
})

function formatMoney(n) {
  if (!Number.isFinite(n)) return '0,00'
  return n.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function utcTodayIso() {
  return new Date().toISOString().slice(0, 10)
}

function shiftUtcDay(isoDay, deltaDays) {
  const t = Date.parse(`${String(isoDay).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(t)) return isoDay
  return new Date(t + deltaDays * 86400000).toISOString().slice(0, 10)
}

function daysBetweenInclusive(fromIso, toIso) {
  const a = Date.parse(`${String(fromIso).slice(0, 10)}T00:00:00Z`)
  const b = Date.parse(`${String(toIso).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return 1
  return Math.floor((b - a) / 86400000) + 1
}

function dailyAmountsFromSummary(s, useNet) {
  if (!s?.days?.length) return []
  const raw = useNet ? s.cash : s.cash_gross ?? s.cash
  if (!raw || typeof raw !== 'object') return []
  const sub = parseAmounts(raw.subscription)
  const one = parseAmounts(raw.one_time)
  return s.days.map((day, i) => ({
    day: String(day).slice(0, 10),
    amount: (sub[i] || 0) + (one[i] || 0),
  }))
}

const averageIncome = computed(() => {
  const ds = dailySummary.value
  if (!ds?.days?.length) return null

  const today = utcTodayIso()
  const firstDay = String(ds.days[0]).slice(0, 10)
  const dayRows = dailyAmountsFromSummary(ds, useNetAmount.value)
  const grandRaw = useNetAmount.value
    ? ds.grand_total
    : ds.grand_total_gross ?? ds.grand_total
  const grand = Number(String(grandRaw ?? '').replace(',', '.'))

  const weekFrom = shiftUtcDay(today, -6)
  const monthFrom = shiftUtcDay(today, -29)

  function sumFrom(fromDay) {
    return dayRows
      .filter((r) => r.day >= fromDay && r.day <= today)
      .reduce((s, r) => s + r.amount, 0)
  }

  const allSpan = daysBetweenInclusive(firstDay, today)
  return {
    all: Number.isFinite(grand) && allSpan > 0 ? grand / allSpan : 0,
    month: sumFrom(monthFrom) / 30,
    week: sumFrom(weekFrom) / 7,
  }
})

const averageIncomeFormatted = computed(() => {
  const a = averageIncome.value
  if (!a) return null
  return {
    all: formatMoney(a.all),
    month: formatMoney(a.month),
    week: formatMoney(a.week),
  }
})

const financeChartLabels = computed(() => {
  if (!periodKeys.value.length) return []
  return isDailyView.value
    ? periodKeys.value.map(formatDayLabel)
    : periodKeys.value.map(formatMonthLabel)
})

const financeChartDatasets = computed(() => {
  const buckets = activeBuckets.value
  if (!periodKeys.value.length || !buckets) return []
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
    maxBarThickness: isDailyView.value ? 24 : 48,
  }))
})

const chartAriaLabel = computed(() =>
  isDailyView.value
    ? 'Доходы по дням (UTC), ₽'
    : 'Доходы по месяцам (UTC), ₽',
)

function financeFormatValueTick(v) {
  return formatChartMoneyTick(v)
}

const financeTooltipFooter = chartBarStackedMoneyTooltipFooter

/** @param {import('chart.js').TooltipItem<'bar'>} item */
const financeTooltipFilter = chartBarPositiveTooltipFilter

async function load() {
  loading.value = true
  error.value = null
  summary.value = null
  dailySummary.value = null
  const granularity = isDailyView.value ? 'day' : 'month'
  try {
    if (isDailyView.value) {
      const data = await fetchJson(
        `/api/admin/payments/finance-summary?granularity=day`,
      )
      summary.value = data
      dailySummary.value = data
    } else {
      const [chartData, dayData] = await Promise.all([
        fetchJson(`/api/admin/payments/finance-summary?granularity=${granularity}`),
        fetchJson('/api/admin/payments/finance-summary?granularity=day'),
      ])
      summary.value = chartData
      dailySummary.value = dayData
    }
  } catch (e) {
    error.value = e.message || String(e)
    summary.value = null
    dailySummary.value = null
  } finally {
    loading.value = false
  }
}

watch(chartDistribution, (next, prev) => {
  const needsReload =
    next === 'daily' ||
    prev === 'daily' ||
    summary.value == null
  if (needsReload) void load()
})

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="head-row">
    <div class="head-actions">
      <div
        class="dist-toggle"
        role="group"
        :aria-label="
          isDailyView
            ? 'Группировка доходов по календарным дням UTC'
            : 'Как считать суммы по месяцам на графике'
        "
      >
        <button
          type="button"
          class="dist-btn"
          :class="{ 'dist-btn--active': chartDistribution === 'daily' }"
          :disabled="loading"
          @click="chartDistribution = 'daily'"
        >
          По дням
        </button>
        <button
          type="button"
          class="dist-btn"
          :class="{ 'dist-btn--active': chartDistribution === 'cash' }"
          :disabled="loading"
          @click="chartDistribution = 'cash'"
        >
          По месяцам
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
      <AppRefreshButton :busy="loading" @click="load" />
    </div>
  </div>

  <StateNote v-if="loading && summary == null" loading text="Загрузка сводки…" />
  <p v-else-if="error" class="msg-err">{{ error }}</p>

  <template v-else-if="summary">
    <div class="stats-row">
      <section class="total-card" aria-live="polite">
        <p class="total-label">{{ totalLabel }}</p>
        <p class="total-value">{{ totalFormatted }}&nbsp;₽</p>
        <label class="fee-row">
          <input v-model="useNetAmount" type="checkbox" class="fee-input" />
          <span class="fee-label">Учитывать комиссию</span>
        </label>
        <p class="total-meta">{{ paymentCountLabel }} записей</p>
      </section>

      <section
        v-if="averageIncomeFormatted"
        class="avg-card"
        aria-label="Средний дневной доход"
      >
        <p class="total-label">Средний доход в день</p>
        <dl class="avg-grid">
          <div class="avg-item">
            <dt class="avg-key">За всё время</dt>
            <dd class="avg-val">{{ averageIncomeFormatted.all }}&nbsp;₽</dd>
          </div>
          <div class="avg-item">
            <dt class="avg-key">30 дней</dt>
            <dd class="avg-val">{{ averageIncomeFormatted.month }}&nbsp;₽</dd>
          </div>
          <div class="avg-item">
            <dt class="avg-key">7 дней</dt>
            <dd class="avg-val">{{ averageIncomeFormatted.week }}&nbsp;₽</dd>
          </div>
        </dl>
      </section>
    </div>

    <AdminBarChartPanel
      :title="sectionHeading"
      :aria-label="chartAriaLabel"
      :has-data="periodKeys.length > 0"
      :labels="financeChartLabels"
      :datasets="financeChartDatasets"
      stacked
      y-title="₽"
      legend-style="box"
      :format-value-tick="financeFormatValueTick"
      :get-tooltip-footer="financeTooltipFooter"
      :tooltip-filter="financeTooltipFilter"
      :category-max-ticks="isDailyView ? 18 : 22"
      :category-max-rotation="isDailyView ? 55 : undefined"
    >
      <template #empty>
        <p class="muted">Платежей пока нет — график появится после первых оплат.</p>
      </template>
    </AdminBarChartPanel>
  </template>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
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
  margin: 0;
  padding: 1rem 1.1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass);
  flex: 1 1 16rem;
  min-width: 0;
}

.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.85rem;
  margin: 0 0 1.25rem;
  align-items: stretch;
}

.avg-card {
  margin: 0;
  padding: 1rem 1.1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass);
  flex: 1 1 18rem;
  min-width: 0;
}

.avg-hint {
  margin: 0 0 0.65rem;
  font-size: 0.76rem;
  color: var(--muted);
  line-height: 1.35;
}

.avg-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem 0.75rem;
  margin: 0;
}

.avg-item {
  min-width: 0;
}

.avg-key {
  margin: 0 0 0.2rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}

.avg-val {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  letter-spacing: -0.01em;
}

@media (max-width: 720px) {
  .avg-grid {
    grid-template-columns: 1fr;
  }
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
