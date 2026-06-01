<script setup>
import { computed, ref, watch } from 'vue'
import AdminDoughnutChart from '../../components/AdminDoughnutChart.vue'
import FinanceTrendChart from './FinanceTrendChart.vue'
import StateNote from '../../components/StateNote.vue'
import { fetchJson } from '../../api/client.js'
import { downloadCsv } from '../../utils/csv.js'

const props = defineProps({
  from: { type: String, required: true },
  to: { type: String, required: true },
})

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<any>} */
const data = ref(null)

const TAX_MODE_LABELS = {
  npd: 'НПД',
  usn_income: 'УСН «Доходы»',
  usn_profit: 'УСН «Д−Р»',
  none: 'Без налога',
  custom: 'Налог',
}
const TAX_BASE_LABELS = {
  gross: 'с валовой выручки',
  net: 'с чистой выручки',
  profit: 'с прибыли',
}

function money(v) {
  const n = Number(String(v ?? '').replace(',', '.'))
  if (!Number.isFinite(n)) return '0,00'
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function num(v) {
  const n = Number(String(v ?? '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}

function formatMonthLabel(ym) {
  const [ys, ms] = String(ym).split('-')
  const y = Number(ys)
  const m = Number(ms)
  if (!y || !m || m < 1 || m > 12) return String(ym)
  const d = new Date(Date.UTC(y, m - 1, 1))
  return d.toLocaleDateString('ru-RU', { month: 'short', year: 'numeric', timeZone: 'UTC' })
}

const totals = computed(() => data.value?.totals ?? null)
const tax = computed(() => data.value?.tax ?? null)
const currency = computed(() => data.value?.currency || 'RUB')

const taxRatePercent = computed(() => {
  const r = num(tax.value?.rate)
  return (r * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
})

const taxLineLabel = computed(() => {
  const t = tax.value
  if (!t) return 'Налог'
  if (t.mode === 'none') return 'Налог (не облагается)'
  const mode = TAX_MODE_LABELS[t.mode] || 'Налог'
  const base = TAX_BASE_LABELS[t.base] || ''
  return `Налог (${mode}, ${taxRatePercent.value}% ${base})`
})

const monthLabels = computed(() => (data.value?.months ?? []).map(formatMonthLabel))
const hasMonths = computed(() => (data.value?.months ?? []).length > 0)

const series = computed(() => data.value?.series ?? {})
const trendRevenue = computed(() => (series.value.revenue_net ?? []).map(num))
const trendExpenses = computed(() => (series.value.expenses_total ?? []).map(num))
const trendProfit = computed(() => (series.value.profit_net ?? []).map(num))
const trendEarned = computed(() => (series.value.earned_net ?? []).map(num))
const trendDeferred = computed(() => (series.value.deferred_net_end ?? []).map(num))

const REVENUE_RGB = [56, 214, 141]
const EXPENSE_RGB = [239, 68, 68]
const PROFIT_RGB = [56, 189, 248]
const EARNED_RGB = [45, 212, 191]
const FROZEN_RGB = [167, 139, 250]

// «cash» — по дате платежа (вся сумма сразу); «accrual» — признание по дням + остаток обязательств.
const chartMode = ref('cash')

const chartBars = computed(() => {
  if (chartMode.value === 'accrual') {
    return [
      { label: 'Заработано (по дням)', data: trendEarned.value, rgb: EARNED_RGB },
      { label: 'Расходы', data: trendExpenses.value, rgb: EXPENSE_RGB },
    ]
  }
  return [
    { label: 'Чистая выручка', data: trendRevenue.value, rgb: REVENUE_RGB },
    { label: 'Расходы', data: trendExpenses.value, rgb: EXPENSE_RGB },
  ]
})
const chartLine = computed(() =>
  chartMode.value === 'accrual'
    ? null
    : { label: 'Чистая прибыль', data: trendProfit.value, rgb: PROFIT_RGB },
)
const chartSecondary = computed(() =>
  chartMode.value === 'accrual'
    ? { label: 'Заморожено (обязательства)', data: trendDeferred.value, rgb: FROZEN_RGB }
    : null,
)
const chartAria = computed(() =>
  chartMode.value === 'accrual'
    ? 'Динамика: заработано по дням, расходы и остаток обязательств по месяцам'
    : 'Динамика: чистая выручка, расходы и прибыль по месяцам',
)

// Денежная позиция на дату snapshot: поступило / свободно (заработано) / заморожено.
const deferred = computed(() => data.value?.deferred ?? null)
const moneyPosition = computed(() => {
  const d = deferred.value
  if (!d) return null
  const received = num(d.received_net)
  const frozen = num(d.deferred_net)
  const free = num(d.earned_net)
  const frozenPct = received > 0 ? ((frozen / received) * 100).toFixed(1) : '0'
  return { received, frozen, free, frozenPct, asOf: d.as_of, active: d.active_obligations }
})

function fmtAsOf(iso) {
  if (!iso) return ''
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', timeZone: 'UTC' })
}

const categorySlices = computed(() => {
  const cats = data.value?.category_totals ?? []
  return cats
    .map((c) => ({ label: c.title, value: num(c.total), color: c.color }))
    .filter((s) => s.value > 0)
})
const hasExpenses = computed(() => categorySlices.value.length > 0)
const expensesTotalNum = computed(() => num(totals.value?.expenses_total))

function categoryShare(value) {
  const total = expensesTotalNum.value
  if (total <= 0) return '0'
  return ((num(value) / total) * 100).toFixed(1)
}

const profitNegative = computed(() => num(totals.value?.profit_net) < 0)

const kpiCards = computed(() => {
  const t = totals.value
  if (!t) return []
  return [
    { key: 'gross', label: 'Валовая выручка', value: money(t.revenue_gross), sub: `Чистая: ${money(t.revenue_net)} ₽`, tone: 'revenue' },
    { key: 'commission', label: 'Комиссии PSP', value: money(t.psp_commission), sub: 'эквайринг', tone: 'muted' },
    { key: 'expenses', label: 'Расходы', value: money(t.expenses_total), sub: 'операционные', tone: 'expense' },
    { key: 'tax', label: 'Налог', value: money(t.tax), sub: tax.value?.mode === 'none' ? '—' : `${taxRatePercent.value}%`, tone: 'muted' },
    { key: 'profit', label: 'Чистая прибыль', value: money(t.profit_net), sub: `Маржа: ${t.margin_percent}%`, tone: profitNegative.value ? 'loss' : 'profit' },
  ]
})

function exportCsv() {
  const d = data.value
  if (!d) return
  const months = d.months || []
  const s = d.series || {}
  const rows = [
    [
      'Месяц',
      'Валовая выручка',
      'Чистая выручка',
      'Комиссии PSP',
      'Расходы',
      'Налог',
      'Чистая прибыль',
      'Заработано (по дням)',
      'Заморожено на конец месяца',
    ],
  ]
  for (let i = 0; i < months.length; i += 1) {
    rows.push([
      months[i],
      s.revenue_gross?.[i] ?? '0',
      s.revenue_net?.[i] ?? '0',
      s.psp_commission?.[i] ?? '0',
      s.expenses_total?.[i] ?? '0',
      s.tax?.[i] ?? '0',
      s.profit_net?.[i] ?? '0',
      s.earned_net?.[i] ?? '0',
      s.deferred_net_end?.[i] ?? '0',
    ])
  }
  const t = d.totals
  rows.push([
    'Итого',
    t.revenue_gross,
    t.revenue_net,
    t.psp_commission,
    t.expenses_total,
    t.tax,
    t.profit_net,
    '',
    '',
  ])
  downloadCsv(`pl_${d.range_from}_${d.range_to}.csv`, rows)
}

async function load() {
  if (!props.from || !props.to) return
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ from: props.from, to: props.to })
    data.value = await fetchJson(`/api/admin/accounting/summary?${params.toString()}`)
  } catch (e) {
    error.value = e.message || String(e)
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.from, props.to],
  () => {
    void load()
  },
  { immediate: true },
)

defineExpose({ reload: load })
</script>

<template>
  <StateNote v-if="loading && data == null" loading text="Загрузка сводки…" />
  <p v-else-if="error" class="msg-err">{{ error }}</p>

  <template v-else-if="totals">
    <div class="overview-toolbar">
      <button type="button" class="btn-secondary btn-sm" @click="exportCsv">Экспорт P&amp;L (CSV)</button>
    </div>

    <section class="kpi-grid" aria-label="Ключевые показатели за период">
      <article
        v-for="c in kpiCards"
        :key="c.key"
        class="kpi-card"
        :class="`kpi-card--${c.tone}`"
      >
        <p class="kpi-label">{{ c.label }}</p>
        <p class="kpi-value">{{ c.value }}&nbsp;<span class="kpi-cur">₽</span></p>
        <p class="kpi-sub">{{ c.sub }}</p>
      </article>
    </section>

    <section
      v-if="moneyPosition"
      class="money-position"
      aria-label="Денежная позиция: свободные и замороженные деньги"
    >
      <div class="mp-head">
        <h3 class="mp-title">Денежная позиция</h3>
        <span class="mp-asof">на {{ fmtAsOf(moneyPosition.asOf) }}</span>
      </div>
      <div class="mp-cards">
        <article class="mp-card mp-card--received">
          <p class="mp-label">Поступило (после комиссии)</p>
          <p class="mp-value">{{ money(moneyPosition.received) }}&nbsp;<span class="mp-cur">₽</span></p>
          <p class="mp-sub">За всё время · кэш на счетах</p>
        </article>
        <article class="mp-card mp-card--free">
          <p class="mp-label">Свободно от обязательств</p>
          <p class="mp-value">{{ money(moneyPosition.free) }}&nbsp;<span class="mp-cur">₽</span></p>
          <p class="mp-sub">За всё время · по дням оказанной услуги</p>
        </article>
        <article class="mp-card mp-card--frozen">
          <p class="mp-label">Заморожено (обязательства)</p>
          <p class="mp-value">{{ money(moneyPosition.frozen) }}&nbsp;<span class="mp-cur">₽</span></p>
          <p class="mp-sub">{{ moneyPosition.frozenPct }}% от поступлений · {{ moneyPosition.active }} с оплаченной подпиской · за всё время</p>
        </article>
      </div>
      <div class="mp-bar" :title="`Заморожено ${moneyPosition.frozenPct}%`">
        <div
          class="mp-bar-free"
          :style="{ width: `${100 - Number(moneyPosition.frozenPct)}%` }"
        />
        <div class="mp-bar-frozen" :style="{ width: `${moneyPosition.frozenPct}%` }" />
      </div>
    </section>

    <div class="grid-2">
      <section class="panel pl-panel" aria-label="Отчёт о прибылях и убытках">
        <h3 class="panel-title">Прибыли и убытки (P&amp;L)</h3>
        <table class="pl-table">
          <tbody>
            <tr>
              <td class="pl-name">Валовая выручка</td>
              <td class="pl-amount pl-pos">{{ money(totals.revenue_gross) }} ₽</td>
            </tr>
            <tr>
              <td class="pl-name">− Комиссии эквайринга (PSP)</td>
              <td class="pl-amount pl-neg">−{{ money(totals.psp_commission) }} ₽</td>
            </tr>
            <tr class="pl-subtotal">
              <td class="pl-name">= Чистая выручка</td>
              <td class="pl-amount">{{ money(totals.revenue_net) }} ₽</td>
            </tr>
            <tr>
              <td class="pl-name">− Операционные расходы</td>
              <td class="pl-amount pl-neg">−{{ money(totals.expenses_total) }} ₽</td>
            </tr>
            <tr v-for="c in categorySlices" :key="c.label" class="pl-cat">
              <td class="pl-name">
                <span class="cat-dot" :style="{ background: c.color }" />
                {{ c.label }}
              </td>
              <td class="pl-amount pl-muted">{{ money(c.value) }} ₽</td>
            </tr>
            <tr>
              <td class="pl-name">− {{ taxLineLabel }}</td>
              <td class="pl-amount pl-neg">−{{ money(totals.tax) }} ₽</td>
            </tr>
            <tr class="pl-total" :class="{ 'pl-total--loss': profitNegative }">
              <td class="pl-name">= Чистая прибыль</td>
              <td class="pl-amount">{{ money(totals.profit_net) }} ₽</td>
            </tr>
            <tr class="pl-margin">
              <td class="pl-name">Маржа</td>
              <td class="pl-amount">{{ totals.margin_percent }}%</td>
            </tr>
          </tbody>
        </table>
        <p class="pl-meta">{{ Number(totals.payment_count).toLocaleString('ru-RU') }} платежей за период</p>
      </section>

      <section class="panel" aria-label="Структура расходов по категориям">
        <h3 class="panel-title">Структура расходов</h3>
        <template v-if="hasExpenses">
          <AdminDoughnutChart
            aria-label="Структура расходов по категориям"
            :has-data="hasExpenses"
            :slices="categorySlices"
          />
          <table class="cat-table">
            <tbody>
              <tr v-for="c in categorySlices" :key="c.label">
                <td class="cat-name">
                  <span class="cat-dot" :style="{ background: c.color }" />
                  {{ c.label }}
                </td>
                <td class="cat-amount">{{ money(c.value) }} ₽</td>
                <td class="cat-share">{{ categoryShare(c.value) }}%</td>
              </tr>
            </tbody>
          </table>
        </template>
        <p v-else class="muted empty-line">
          Расходов за период нет. Добавьте их во вкладке «Расходы».
        </p>
      </section>
    </div>

    <section class="panel" aria-label="Динамика доходов и расходов">
      <div class="dyn-head">
        <h3 class="panel-title dyn-title">Динамика по месяцам</h3>
        <div class="mode-toggle" role="group" aria-label="Режим признания выручки">
          <button
            type="button"
            class="mode-btn"
            :class="{ 'mode-btn--active': chartMode === 'cash' }"
            @click="chartMode = 'cash'"
          >
            Кассовый
          </button>
          <button
            type="button"
            class="mode-btn"
            :class="{ 'mode-btn--active': chartMode === 'accrual' }"
            @click="chartMode = 'accrual'"
          >
            Начисление по дням
          </button>
        </div>
      </div>
      <FinanceTrendChart
        v-if="hasMonths"
        :aria-label="chartAria"
        :has-data="hasMonths"
        :labels="monthLabels"
        :bars="chartBars"
        :line="chartLine"
        :secondary="chartSecondary"
      />
      <p v-else class="muted empty-line">Нет данных за выбранный период.</p>
    </section>
  </template>
</template>

<style scoped>
.muted {
  color: var(--muted);
}
.msg-err {
  color: var(--danger);
  margin-bottom: 0.75rem;
}
.empty-line {
  padding: 1rem 0;
  font-size: 0.9rem;
}

.overview-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.75rem;
}
.btn-sm {
  padding: 0.4rem 0.85rem;
  font-size: 0.82rem;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}
.kpi-card {
  padding: 0.85rem 1rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass, var(--surface));
  box-shadow: var(--shadow-sm);
}
.kpi-label {
  margin: 0 0 0.3rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.kpi-value {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  letter-spacing: -0.01em;
}
.kpi-cur {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--muted);
}
.kpi-sub {
  margin: 0.3rem 0 0;
  font-size: 0.76rem;
  color: var(--muted);
}
.kpi-card--profit {
  border-color: color-mix(in srgb, #34d399 45%, var(--card-border));
  background: color-mix(in srgb, #34d399 9%, var(--surface));
}
.kpi-card--profit .kpi-value {
  color: #2bb673;
}
.kpi-card--loss {
  border-color: color-mix(in srgb, #ef4444 45%, var(--card-border));
  background: color-mix(in srgb, #ef4444 9%, var(--surface));
}
.kpi-card--loss .kpi-value {
  color: #ef4444;
}
.kpi-card--revenue .kpi-value {
  color: var(--text-h);
}
.kpi-card--expense .kpi-value {
  color: #e08a4a;
}

/* Денежная позиция */
.money-position {
  padding: 1rem 1.15rem 1.15rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  background: var(--surface-glass, var(--surface));
  box-shadow: var(--shadow-sm);
  margin-bottom: 1rem;
}
.mp-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}
.mp-title {
  margin: 0;
  font-size: 1.02rem;
  font-weight: 800;
  font-family: var(--heading, inherit);
  color: var(--text-h);
}
.mp-asof {
  font-size: 0.78rem;
  color: var(--muted);
  white-space: nowrap;
}
.mp-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
}
.mp-card {
  padding: 0.85rem 1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
}
.mp-label {
  margin: 0 0 0.3rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.mp-value {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  letter-spacing: -0.01em;
}
.mp-cur {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--muted);
}
.mp-sub {
  margin: 0.3rem 0 0;
  font-size: 0.74rem;
  color: var(--muted);
  line-height: 1.35;
}
.mp-card--free {
  border-color: color-mix(in srgb, #2dd4bf 45%, var(--card-border));
  background: color-mix(in srgb, #2dd4bf 8%, var(--surface));
}
.mp-card--free .mp-value {
  color: #14b8a6;
}
.mp-card--frozen {
  border-color: color-mix(in srgb, #a78bfa 45%, var(--card-border));
  background: color-mix(in srgb, #a78bfa 8%, var(--surface));
}
.mp-card--frozen .mp-value {
  color: #8b5cf6;
}
.mp-bar {
  display: flex;
  height: 12px;
  margin-top: 0.9rem;
  border-radius: 999px;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--card-border);
}
.mp-bar-free {
  background: #2dd4bf;
  transition: width 0.4s ease;
}
.mp-bar-frozen {
  background: #a78bfa;
  transition: width 0.4s ease;
}
.mp-hint {
  margin: 0.75rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.5;
  max-width: 56rem;
}

/* Переключатель режима графика */
.dyn-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}
.dyn-title {
  margin: 0;
}
.dyn-hint {
  margin: 0.4rem 0 0.85rem;
  font-size: 0.8rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 56rem;
}
.mode-toggle {
  display: inline-flex;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  overflow: hidden;
  background: var(--surface);
}
.mode-btn {
  margin: 0;
  padding: 0.4rem 0.8rem;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  white-space: nowrap;
}
.mode-btn:hover:not(.mode-btn--active) {
  color: var(--text-h);
  background: rgba(127, 127, 127, 0.08);
}
.mode-btn--active {
  color: var(--text-h);
  background: rgba(88, 214, 141, 0.14);
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}
.panel {
  padding: 1rem 1.15rem 1.15rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  background: var(--surface-glass, var(--surface));
  box-shadow: var(--shadow-sm);
  margin-bottom: 1rem;
}
.panel-title {
  margin: 0 0 0.85rem;
  font-size: 1.02rem;
  font-weight: 800;
  font-family: var(--heading, inherit);
  color: var(--text-h);
}

.pl-table {
  width: 100%;
  border-collapse: collapse;
}
.pl-table td {
  padding: 0.4rem 0;
  font-size: 0.9rem;
  border-bottom: 1px solid color-mix(in srgb, var(--card-border) 60%, transparent);
}
.pl-name {
  color: var(--text-h);
}
.pl-amount {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  font-weight: 600;
}
.pl-pos {
  color: var(--text-h);
}
.pl-neg {
  color: #e0795a;
}
.pl-muted {
  color: var(--muted);
  font-weight: 500;
}
.pl-subtotal td {
  font-weight: 700;
  color: var(--text-h);
}
.pl-cat .pl-name {
  padding-left: 1.1rem;
  font-size: 0.82rem;
  color: var(--muted);
}
.pl-total td {
  padding-top: 0.6rem;
  font-size: 1.05rem;
  font-weight: 800;
  color: #2bb673;
  border-bottom: none;
}
.pl-total--loss td {
  color: #ef4444;
}
.pl-margin td {
  color: var(--muted);
  font-size: 0.82rem;
  border-bottom: none;
}
.pl-meta {
  margin: 0.75rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}

.cat-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  margin-right: 0.45rem;
  vertical-align: middle;
}
.cat-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.85rem;
}
.cat-table td {
  padding: 0.35rem 0;
  font-size: 0.85rem;
  border-bottom: 1px solid color-mix(in srgb, var(--card-border) 50%, transparent);
}
.cat-name {
  color: var(--text-h);
}
.cat-amount {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  white-space: nowrap;
}
.cat-share {
  text-align: right;
  color: var(--muted);
  width: 4rem;
  font-variant-numeric: tabular-nums;
}
</style>
