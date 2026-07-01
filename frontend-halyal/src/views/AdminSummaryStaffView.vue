<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminChartsGrid from '../components/AdminChartsGrid.vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminBarChartPanel from '../components/AdminBarChartPanel.vue'
import AdminPeriodPresets from '../components/AdminPeriodPresets.vue'
import StatWidget from '../components/StatWidget.vue'
import StatWidgetSplit from '../components/StatWidgetSplit.vue'
import StateNote from '../components/StateNote.vue'
import { fetchJson } from '../api/client.js'
import { useAdminSummaryCharts } from '../composables/useAdminSummaryCharts.js'
import { useMskPeriodRange } from '../composables/useMskPeriodRange.js'
import { SUMMARY_PERIOD_PRESETS } from '../utils/mskPeriodRange.js'

const { periodPreset, computedRange, periodLabel } = useMskPeriodRange(
  SUMMARY_PERIOD_PRESETS,
  'month',
)

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const data = ref(null)

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

const charts = useAdminSummaryCharts(
  computedRange,
  computed(() => periodPreset.value === 'all'),
)

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
      <AdminPeriodPresets
        v-model="periodPreset"
        :presets="SUMMARY_PERIOD_PRESETS"
        :aria-label="`Период: ${periodLabel}`"
      />
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
          <StatWidgetSplit
            v-if="!loading && !error"
            :items="[
              { label: 'Всего', value: int(data?.expiring_subscriptions) },
              { label: 'Платные', value: int(data?.expiring_paid) },
            ]"
          />
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Доход">
          <StatWidgetSplit
            v-if="!loading && !error"
            :items="[
              { label: 'За период', value: `${money(data?.revenue_period)} ₽` },
              { label: 'Всего', value: `${money(data?.revenue_total)} ₽` },
            ]"
          />
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Платежи за период">
          <StatWidgetSplit
            v-if="!loading && !error"
            :items="[
              { label: 'Средний чек', value: `${money(data?.avg_check)} ₽` },
              { label: 'Количество', value: int(data?.payments_count) },
            ]"
          />
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Платящие за период">
          <StatWidgetSplit
            v-if="!loading && !error"
            :items="[
              { label: 'Всего', value: int(data?.paying_users_in_period) },
              { label: 'LTV', value: `${money(data?.ltv_period)} ₽` },
            ]"
          />
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </StatWidget>

        <StatWidget title="Конверсия в оплату">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : `${pct(data?.conversion_pct)}%` }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            доля платящих от всех пользователей
          </p>
        </StatWidget>

        <StatWidget title="Платежей на плательщика">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : pct(data?.payments_per_paying_user) }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            среднее число платежей на одного платящего за период
          </p>
        </StatWidget>

        <StatWidget title="Удержание платящих">
          <StatWidgetSplit
            v-if="!loading && !error"
            :items="[
              { label: 'Удержание', value: `${pct(data?.renewal_pct)}%` },
              { label: 'Возвратность', value: `${pct(data?.return_pct)}%` },
            ]"
          />
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            по notify_payment · окончаний: {{ int(data?.renewal_eligible) }} · досрочно
            {{ int(data?.renewed_early) }} · в день окончания
            {{ int(data?.renewed_on_expiry) }} · вернулись {{ int(data?.returned_after_expiry) }}
          </p>
        </StatWidget>
      </div>
    </section>

    <AdminChartsGrid>
      <AdminLineChartPanel
        flush
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

      <AdminBarChartPanel
        flush
        title="Доход"
        :hint="revenueHint"
        :aria-label="revenueAriaLabel"
        :loading="chartsLoading"
        :error="chartsError"
        :has-data="revenueHasData"
        :labels="revenueLabels"
        :datasets="revenueDatasets"
        y-title="₽"
        :format-value-tick="formatMoneyTick"
        :get-tooltip-footer="revenueTooltipFooter"
        :category-max-ticks="revenueCategoryMaxTicks"
        :category-max-rotation="chartsBucket === 'month' ? 0 : 55"
      >
        <template #empty>
          <p class="empty-hint">Нет платежей за выбранный период.</p>
        </template>
      </AdminBarChartPanel>
    </AdminChartsGrid>
  </AdminStaffShell>
</template>
