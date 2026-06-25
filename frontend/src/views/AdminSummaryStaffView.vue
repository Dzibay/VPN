<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminBarChart from '../components/AdminBarChart.vue'
import StatWidget from '../components/StatWidget.vue'
import StateNote from '../components/StateNote.vue'
import { fetchJson } from '../api/client.js'
import { useAdminSummaryCharts } from '../composables/useAdminSummaryCharts.js'
import { mskTodayIso, subtractCalendarDaysIso } from '../utils/mskDate.js'

const PERIOD_PRESETS = [
  { key: 'day', label: 'День' },
  { key: 'week', label: 'Неделя' },
  { key: 'month', label: 'Месяц' },
  { key: 'quarter', label: 'Квартал' },
  { key: 'half_year', label: 'Полгода' },
  { key: 'year', label: 'Год' },
  { key: 'all', label: 'Всё время' },
]

const periodPreset = ref('month')
const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const data = ref(null)

const pad2 = (n) => String(n).padStart(2, '0')

function mskParts() {
  const [y, m, d] = mskTodayIso().split('-').map(Number)
  return { y, m, d }
}

function monthStart(y, m) {
  return `${y}-${pad2(m)}-01`
}

function shiftMonth(y, m, delta) {
  let ny = y
  let nm = m + delta
  while (nm <= 0) {
    nm += 12
    ny -= 1
  }
  while (nm > 12) {
    nm -= 12
    ny += 1
  }
  return { y: ny, m: nm }
}

const computedRange = computed(() => {
  const today = mskTodayIso()
  const { y, m } = mskParts()
  switch (periodPreset.value) {
    case 'day':
      return { from: today, to: today }
    case 'week':
      return { from: subtractCalendarDaysIso(today, 6), to: today }
    case 'month':
      return { from: monthStart(y, m), to: today }
    case 'quarter': {
      const qStart = Math.floor((m - 1) / 3) * 3 + 1
      return { from: monthStart(y, qStart), to: today }
    }
    case 'half_year': {
      const { y: hy, m: hm } = shiftMonth(y, m, -6)
      return { from: monthStart(hy, hm), to: today }
    }
    case 'all':
      return { from: '2020-01-01', to: today }
    case 'year':
    default:
      return { from: monthStart(y, 1), to: today }
  }
})

function money(v) {
  const n = Number(String(v ?? '').replace(',', '.'))
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function int(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toLocaleString('ru-RU') : '—'
}

function pct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

const periodLabel = computed(() => {
  const p = PERIOD_PRESETS.find((x) => x.key === periodPreset.value)
  return p?.label ?? ''
})

const charts = useAdminSummaryCharts(computedRange)

const revenueCategoryMaxTicks = computed(() => {
  const b = charts.bucket.value
  if (b === 'hour' || b === 'day') return 12
  if (b === 'week') return 14
  return 18
})

const {
  loading: chartsLoading,
  error: chartsError,
  bucket: chartsBucket,
  usersHint,
  revenueHint,
  usersAriaLabel,
  revenueAriaLabel,
  usersLabels,
  revenueLabels,
  usersDatasets,
  revenueDatasets,
  usersHasData,
  revenueHasData,
  formatCountTick,
  formatMoneyTick,
  usersTooltipTitle,
  usersTooltipLabel,
  revenueTooltipFooter,
} = charts

async function load() {
  loading.value = true
  error.value = null
  try {
    const { from, to } = computedRange.value
    const params = new URLSearchParams({ from, to })
    data.value = await fetchJson(`/api/admin/summary?${params}`)
  } catch (e) {
    error.value = e?.message || 'Не удалось загрузить сводку'
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(periodPreset, () => {
  void load()
})

onMounted(() => {
  void load()
  void charts.load()
})
</script>

<template>
  <AdminStaffShell title="Сводка">
    <template #headerExtras>
      <div class="period-row">
        <div class="period-presets" role="group" :aria-label="`Период: ${periodLabel}`">
          <button
            v-for="p in PERIOD_PRESETS"
            :key="p.key"
            type="button"
            class="period-btn"
            :class="{ 'period-btn--active': periodPreset === p.key }"
            @click="periodPreset = p.key"
          >
            {{ p.label }}
          </button>
        </div>
      </div>
    </template>

    <StateNote v-if="error" variant="error">{{ error }}</StateNote>

    <section class="stats widgets-row" aria-live="polite">
      <div class="widgets-grid">
        <StatWidget title="Пользователи">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : int(data?.users_total) }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            За период: +{{ int(data?.users_in_period) }}
          </p>
        </StatWidget>

        <StatWidget title="Активные">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : int(data?.active_users) }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            {{ pct(data?.active_users_pct) }}% от всех
          </p>
        </StatWidget>

        <StatWidget title="Истекают подписки &lt;7 дней">
          <dl v-if="!loading && !error" class="stat-widget-split">
            <div>
              <dt>Всего</dt>
              <dd>{{ int(data?.expiring_subscriptions) }}</dd>
            </div>
            <div>
              <dt>Платные</dt>
              <dd>{{ int(data?.expiring_paid) }}</dd>
            </div>
          </dl>
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Доход">
          <dl v-if="!loading && !error" class="stat-widget-split">
            <div>
              <dt>За период</dt>
              <dd>{{ money(data?.revenue_period) }} ₽</dd>
            </div>
            <div>
              <dt>Всего</dt>
              <dd>{{ money(data?.revenue_total) }} ₽</dd>
            </div>
          </dl>
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Платежи">
          <dl v-if="!loading && !error" class="stat-widget-split">
            <div>
              <dt>Средний чек</dt>
              <dd>{{ money(data?.avg_check) }} ₽</dd>
            </div>
            <div>
              <dt>Количество</dt>
              <dd>{{ int(data?.payments_count) }}</dd>
            </div>
          </dl>
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Платящие">
          <dl v-if="!loading && !error" class="stat-widget-split">
            <div>
              <dt>Ср. доход / плательщик</dt>
              <dd>{{ money(data?.avg_revenue_per_paying_user) }} ₽</dd>
            </div>
            <div>
              <dt>Всего платящих</dt>
              <dd>{{ int(data?.paying_users_total) }}</dd>
            </div>
          </dl>
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Конверсия">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : `${pct(data?.conversion_pct)}%` }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            {{ int(data?.paying_users_total) }} из {{ int(data?.users_total) }}
          </p>
        </StatWidget>
      </div>
    </section>

    <section class="summary-charts" aria-label="Графики">
      <AdminLineChartPanel
        class="summary-chart-panel"
        title="Приток пользователей"
        unit-label="регистрации"
        :hint="usersHint"
        :aria-label="usersAriaLabel"
        :loading="chartsLoading"
        :error="chartsError"
        :has-data="usersHasData"
        y-title="Пользователей"
        y-grace="8%"
        :labels="usersLabels"
        :datasets="usersDatasets"
        :format-y-tick="formatCountTick"
        :get-tooltip-title="usersTooltipTitle"
        :get-tooltip-label="usersTooltipLabel"
      >
        <template #empty>
          <p class="empty-hint">Нет регистраций за выбранный период.</p>
        </template>
      </AdminLineChartPanel>

      <div class="summary-chart-panel summary-chart-panel--revenue">
        <h3 class="summary-chart-heading">Доход</h3>
        <p v-if="revenueHint" class="summary-chart-hint">{{ revenueHint }}</p>
        <StateNote
          v-if="chartsLoading && !revenueLabels.length"
          loading
          text="Загрузка…"
        />
        <p v-else-if="chartsError" class="msg-err">{{ chartsError }}</p>
        <p v-else-if="!revenueHasData" class="empty-hint">
          Нет платежей за выбранный период.
        </p>
        <AdminBarChart
          v-else
          preset="finance"
          :aria-label="revenueAriaLabel"
          :has-data="revenueHasData"
          :labels="revenueLabels"
          :datasets="revenueDatasets"
          value-axis-title="₽"
          :format-value-tick="formatMoneyTick"
          :get-tooltip-footer="revenueTooltipFooter"
          :category-max-ticks="revenueCategoryMaxTicks"
          :category-max-rotation="chartsBucket === 'month' ? 0 : 55"
        />
      </div>
    </section>
  </AdminStaffShell>
</template>

<style scoped>
.period-row {
  margin: 0 0 0.85rem;
}
.period-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.period-btn {
  margin: 0;
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--muted);
  background: color-mix(in srgb, var(--surface) 92%, black);
  transition:
    color 0.15s ease,
    background 0.15s ease,
    border-color 0.15s ease;
}
.period-btn:hover:not(.period-btn--active) {
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--card-border));
}
.period-btn--active {
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--accent) 55%, var(--card-border));
  background: color-mix(in srgb, var(--accent) 10%, var(--surface));
}

.widgets-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}
@media (max-width: 960px) {
  .widgets-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .widgets-grid {
    grid-template-columns: 1fr;
  }
}

.summary-charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  margin-top: 1.5rem;
  align-items: start;
}
@media (max-width: 960px) {
  .summary-charts {
    grid-template-columns: 1fr;
  }
}
.summary-chart-panel {
  min-width: 0;
}
.summary-chart-panel--revenue {
  padding: 1rem 1.1rem;
  border-radius: 10px;
  border: 1px solid var(--nav-border);
  background: var(--card-bg, var(--surface));
}
.summary-chart-heading {
  margin: 0 0 0.25rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-h);
}
.summary-chart-hint {
  margin: 0 0 0.65rem;
  font-size: 0.82rem;
  color: var(--muted);
}
.empty-hint {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.5;
}
.msg-err {
  margin: 0;
  color: var(--danger);
  font-size: 0.9rem;
}
</style>
