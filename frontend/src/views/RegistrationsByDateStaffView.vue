<script setup>
import { computed, onMounted, ref, toRefs, watch } from 'vue'
import AdminBarChartPanel from '../components/AdminBarChartPanel.vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import { fetchJson } from '../api/client.js'
import { mapStaffChartEventsToMarkers } from '../utils/chartStaffMarkersPlugin.js'
import { useUsersDailyStatsChart } from '../composables/useUsersDailyStatsChart.js'
import { chartSeriesRgb, rgba } from '../utils/adminChartTheme.js'
import {
  formatMskCalendarDayShort,
  formatMskDateTimeShort,
  mskMonthInputDefault,
  mskTodayIso,
} from '../utils/mskDate.js'

/** @typedef {{ id: number; event_at: string; title: string; color: string; created_at: string }} ChartEventRow */

const chartEvents = ref(/** @type {ChartEventRow[]} */ ([]))
const eventsLoading = ref(false)
const eventsError = ref(null)
const eventsBusy = ref(false)
const newEventTitle = ref('')
const newEventColor = ref('#58D68D')
const newEventDatetimeLocal = ref('')

function localDatetimeToIsoUtc(localStr) {
  if (localStr == null || String(localStr).trim() === '') return null
  const d = new Date(localStr)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

async function loadChartEvents() {
  eventsLoading.value = true
  eventsError.value = null
  try {
    const data = await fetchJson('/api/staff/chart-events')
    chartEvents.value = Array.isArray(data) ? data : []
  } catch (e) {
    eventsError.value = e.message || String(e)
    chartEvents.value = []
  } finally {
    eventsLoading.value = false
  }
}

async function addChartEvent() {
  const title = newEventTitle.value.trim()
  const iso = localDatetimeToIsoUtc(newEventDatetimeLocal.value)
  if (!title || !iso) {
    eventsError.value = 'Укажите дату и время события и название.'
    return
  }
  let color = String(newEventColor.value || '').trim().toUpperCase()
  if (!/^#[0-9A-F]{6}$/.test(color)) {
    eventsError.value = 'Цвет должен быть в формате #RRGGBB.'
    return
  }
  eventsBusy.value = true
  eventsError.value = null
  try {
    await fetchJson('/api/staff/chart-events', {
      method: 'POST',
      body: JSON.stringify({
        event_at: iso,
        title,
        color,
      }),
    })
    newEventTitle.value = ''
    await loadChartEvents()
  } catch (e) {
    eventsError.value = e.message || String(e)
  } finally {
    eventsBusy.value = false
  }
}

async function removeChartEvent(id) {
  eventsBusy.value = true
  eventsError.value = null
  try {
    await fetchJson(`/api/staff/chart-events/${id}`, { method: 'DELETE' })
    await loadChartEvents()
  } catch (e) {
    eventsError.value = e.message || String(e)
  } finally {
    eventsBusy.value = false
  }
}

const chart = useUsersDailyStatsChart()
const {
  granularity,
  hourDayMsk,
  loading,
  error,
  chartPoints,
  chartAriaLabel,
  chartYTitle,
  chartPercentMode,
  formatChartYTick,
  registrationChartLabels,
  registrationChartDatasets,
  registrationTooltipTitle,
  registrationTooltipLabel,
  undatedCount,
} = toRefs(chart)

const { setGranularity, load } = chart

const payExpMonth = ref(mskMonthInputDefault())
/** @type {import('vue').Ref<{ min: string | null; max: string | null }>} */
const payExpMonthBounds = ref({ min: null, max: null })

function clampPayExpMonth() {
  const { min, max } = payExpMonthBounds.value
  if (!min || !max) return
  if (payExpMonth.value < min) payExpMonth.value = min
  if (payExpMonth.value > max) payExpMonth.value = max
}

const chartEventMarkers = computed(() =>
  mapStaffChartEventsToMarkers(
    chartPoints.value,
    granularity.value,
    chartEvents.value,
  ),
)

/**
 * @typedef {{
 *   stats_date: string
 *   payments_count: number
 *   payments_first_count: number
 *   payments_repeat_count: number
 *   subscription_expiring_has_payment_count: number
 *   subscription_expiring_total_count: number
 *   subscription_expiring_active_today_count: number
 *   subscription_expiring_active_on_day_count: number
 *   subscription_expiring_has_traffic_count: number
 *   subscription_expiring_no_traffic_count: number
 * }} PayExpRow
 */

const payExpRows = ref(/** @type {PayExpRow[]} */ ([]))
const payExpLoading = ref(false)
const payExpError = ref(null)

const payExpXMarkers = computed(() => {
  const today = mskTodayIso()
  if (String(today).slice(0, 7) !== payExpMonth.value) return []
  const idx = payExpRows.value.findIndex(
    (r) => String(r.stats_date ?? '').slice(0, 10) === today,
  )
  if (idx < 0) return []
  return [
    {
      index: idx,
      title: 'Сегодня (МСК)',
      color: chartSeriesRgb.todayMarker,
      kind: 'today',
    },
  ]
})

/** Как на графике «Финансы»: один столбец, скругление только снаружи у стека. */
const PAY_EXP_BAR_STYLE = /** @type {const} */ ({
  borderRadius: 4,
  maxBarThickness: 48,
})

const payExpLabels = computed(() =>
  payExpRows.value.map((r) =>
    formatMskCalendarDayShort(String(r.stats_date).slice(0, 10)),
  ),
)

const payExpAriaLabel =
  'По дням МСК: два столбца — оплаты (первая и повторная) и окончания подписки (без трафика, с трафиком, активные в день окончания, активные сегодня)'

const payExpHint =
  'В каждом дне два столбца: слева оплаты, справа окончания подписки. Над столбцами по центру дня — число окончаний у пользователей с оплатой: голубое для сегодня и будущих дней, серое для прошедших.'

const payExpCategoryBlue = rgba(chartSeriesRgb.active, 0.95)
const payExpCategoryGray = rgba(chartSeriesRgb.expiryGray, 0.92)

const payExpCategoryValueLabels = computed(() => {
  const today = mskTodayIso()
  const rows = payExpRows.value
  return [
    {
      values: rows.map(
        (r) => Number(r.subscription_expiring_has_payment_count) || 0,
      ),
      colors: rows.map((r) => {
        const day = String(r.stats_date).slice(0, 10)
        return day < today ? payExpCategoryGray : payExpCategoryBlue
      }),
    },
  ]
})

/** Нижний слой стека → верхний. Два stack: pay | exp — без суммирования разных метрик в один столбец. */
const payExpDatasets = computed(() => {
  const rows = payExpRows.value
  const { borderRadius, maxBarThickness } = PAY_EXP_BAR_STYLE
  return [
    {
      label: 'Оплаты: первая',
      stack: 'pay',
      data: rows.map((r) => Number(r.payments_first_count) || 0),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.payment]),
      borderRadius,
      maxBarThickness,
    },
    {
      label: 'Оплаты: повторная',
      stack: 'pay',
      data: rows.map((r) => Number(r.payments_repeat_count) || 0),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.persistent]),
      borderRadius,
      maxBarThickness,
    },
    {
      label: 'Окончание: без трафика',
      stack: 'exp',
      data: rows.map((r) => Number(r.subscription_expiring_no_traffic_count) || 0),
      backgroundColor: rgba(chartSeriesRgb.expiryGray, 0.45),
      borderColor: rgba(chartSeriesRgb.expiryGray, 0.68),
      borderWidth: 0,
      hoverBackgroundColor: rgba(chartSeriesRgb.expiryGray, 0.58),
      hoverBorderColor: rgba(chartSeriesRgb.expiryGray, 0.88),
      borderRadius,
      maxBarThickness,
    },
    {
      label: 'Окончание: с трафиком',
      stack: 'exp',
      data: rows.map((r) => Number(r.subscription_expiring_has_traffic_count) || 0),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.traffic]),
      borderRadius,
      maxBarThickness,
    },
    {
      label: 'Окончание: активные в день окончания',
      stack: 'exp',
      data: rows.map((r) => Number(r.subscription_expiring_active_on_day_count) || 0),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.active]),
      borderRadius,
      maxBarThickness,
    },
    {
      label: 'Окончание: активные сегодня (МСК)',
      stack: 'exp',
      data: rows.map((r) => Number(r.subscription_expiring_active_today_count) || 0),
      rgb: /** @type {[number, number, number]} */ ([...chartSeriesRgb.activePay]),
      borderRadius,
      maxBarThickness,
    },
  ]
})

/** @param {import('chart.js').TooltipItem<'bar'>[]} items */
function payExpTooltipFooter(items) {
  const first = items?.[0]
  if (!first?.chart) return ''
  const idx = first.dataIndex
  const row = payExpRows.value[idx]
  if (!row) return ''
  const payTotal = Number(row.payments_count) || 0
  const expTotal = Number(row.subscription_expiring_total_count) || 0
  return [
    `Оплаты за день: ${payTotal.toLocaleString('ru-RU')}`,
    `Окончания подписки: ${expTotal.toLocaleString('ru-RU')}`,
  ]
}

/** @param {import('chart.js').TooltipItem<'bar'>} item */
function payExpTooltipFilter(item) {
  return Number(item.raw) > 0
}

async function loadPayExpBars() {
  payExpLoading.value = true
  payExpError.value = null
  try {
    const data = await fetchJson(
      `/api/users/daily-payments-expiry-bars?month=${encodeURIComponent(payExpMonth.value)}`,
    )
    payExpRows.value = Array.isArray(data.rows) ? data.rows : []
    const min =
      typeof data.month_min === 'string' && data.month_min ? data.month_min : null
    const max =
      typeof data.month_max === 'string' && data.month_max ? data.month_max : null
    payExpMonthBounds.value = { min, max }
    clampPayExpMonth()
  } catch (e) {
    payExpError.value = e.message || String(e)
    payExpRows.value = []
  } finally {
    payExpLoading.value = false
  }
}

async function refreshAllCharts() {
  await load()
  await loadPayExpBars()
}

onMounted(() => {
  void load()
  void loadChartEvents()
  void loadPayExpBars()
})

watch(payExpMonth, () => {
  void loadPayExpBars()
})
</script>

<template>
  <AdminStaffShell title="Статистика по периодам">
    <template #headerExtras>
      <div class="head-row">
        <div class="head-text">
          <h2 class="section-heading">Статистика по периодам</h2>
        </div>
        <div class="head-actions">
          <div
            class="granularity-toggle"
            role="group"
            aria-label="Шаг временной шкалы: дни по Москве (регистрации), часы по Москве"
          >
            <button
              type="button"
              class="granularity-btn"
              :class="{ 'granularity-btn--active': granularity === 'day' }"
              :disabled="loading"
              @click="setGranularity('day')"
            >
              По дням
            </button>
            <button
              type="button"
              class="granularity-btn"
              :class="{ 'granularity-btn--active': granularity === 'hour' }"
              :disabled="loading"
              @click="setGranularity('hour')"
            >
              По часам
            </button>
          </div>
          <div
            v-if="granularity === 'day'"
            class="granularity-toggle percent-toggle"
            role="group"
            aria-label="Единицы на графике: абсолютные числа или доля от регистраций"
          >
            <button
              type="button"
              class="granularity-btn"
              :class="{ 'granularity-btn--active': !chartPercentMode }"
              :disabled="loading"
              @click="chartPercentMode = false"
            >
              Числа
            </button>
            <button
              type="button"
              class="granularity-btn"
              :class="{ 'granularity-btn--active': chartPercentMode }"
              :disabled="loading"
              title="Все серии — в % от накопленных регистраций за день; линия «Всего пользователей» скрыта"
              @click="chartPercentMode = true"
            >
              В %
            </button>
          </div>
          <label v-if="granularity === 'hour'" class="hour-day-field">
            <span class="hour-day-label-text">День (МСК)</span>
            <input
              v-model="hourDayMsk"
              class="hour-day-input"
              type="date"
              :max="mskTodayIso()"
              required
            />
          </label>
          <AppRefreshButton :busy="loading || payExpLoading" @click="refreshAllCharts" />
        </div>
      </div>
    </template>

    <AdminLineChartPanel
      :aria-label="chartAriaLabel"
      :loading="loading"
      :error="error"
      :has-data="chartPoints.length > 0"
      :y-title="chartYTitle"
      :format-y-tick="formatChartYTick"
      :y-grace="chartPercentMode ? '2%' : '8%'"
      :labels="registrationChartLabels"
      :datasets="registrationChartDatasets"
      :event-markers="chartEventMarkers"
      :get-tooltip-title="registrationTooltipTitle"
      :get-tooltip-label="registrationTooltipLabel"
    >
      <template #empty>
        <p
          v-if="chartPoints.length === 0 && undatedCount > 0"
          class="empty-hint"
        >
          Нет ни одной известной даты регистрации — только пользователи без
          даты:
          <strong>{{ undatedCount.toLocaleString('ru-RU') }}</strong>
          . Добавить их к точкам по дням нельзя — появится график после появления
          записей с датой или временем.
        </p>
        <p v-else class="empty-hint">Нет данных для графика.</p>
      </template>
    </AdminLineChartPanel>

    <section class="chart-events glass" aria-labelledby="chart-events-heading">
      <h3 id="chart-events-heading" class="chart-events-title">
        События на шкале
      </h3>

      <form class="chart-events-form" @submit.prevent="addChartEvent">
        <label class="cef-field">
          <span class="cef-label">Когда</span>
          <input
            v-model="newEventDatetimeLocal"
            class="cef-input"
            type="datetime-local"
            required
          />
        </label>
        <label class="cef-field cef-field-grow">
          <span class="cef-label">Название</span>
          <input
            v-model="newEventTitle"
            class="cef-input"
            type="text"
            maxlength="500"
            autocomplete="off"
            placeholder="Например: Релиз приложения"
            required
          />
        </label>
        <label class="cef-field cef-field-color">
          <span class="cef-label">Цвет</span>
          <input
            v-model="newEventColor"
            class="cef-color"
            type="color"
            aria-label="Цвет события"
          />
        </label>
        <button
          type="submit"
          class="btn-secondary"
          :disabled="eventsBusy || eventsLoading"
        >
          {{ eventsBusy ? 'Сохранение…' : 'Добавить' }}
        </button>
      </form>

      <p v-if="eventsLoading" class="events-status muted">Загрузка событий…</p>
      <p v-else-if="eventsError" class="events-status events-status--err">
        {{ eventsError }}
      </p>
      <ul v-else class="chart-events-list">
        <li v-if="chartEvents.length === 0" class="chart-events-empty muted">
          Пока нет событий — добавьте первое выше.
        </li>
        <li
          v-for="ev in chartEvents"
          :key="ev.id"
          class="chart-events-item"
          :style="{ borderLeftColor: ev.color }"
        >
          <div class="chart-events-item-main">
            <time class="chart-events-time mono-inline" :datetime="ev.event_at">{{
              formatMskDateTimeShort(ev.event_at)
            }}</time>
            <span class="chart-events-dot" :style="{ background: ev.color }" aria-hidden="true" />
            <span class="chart-events-caption">{{ ev.title }}</span>
          </div>
          <button
            type="button"
            class="btn-ghost chart-events-remove"
            :disabled="eventsBusy"
            title="Удалить событие"
            @click="removeChartEvent(ev.id)"
          >
            Удалить
          </button>
        </li>
      </ul>
    </section>

    <div class="payments-expiry-wrap">
      <div class="payments-expiry-toolbar">
        <label class="pay-exp-month-label">
          <input
            v-model="payExpMonth"
            type="month"
            class="pay-exp-month-input"
            :min="payExpMonthBounds.min || undefined"
            :max="payExpMonthBounds.max || undefined"
            :disabled="payExpLoading || !payExpMonthBounds.min"
          />
        </label>
      </div>
      <AdminBarChartPanel
        :aria-label="payExpAriaLabel"
        :loading="payExpLoading"
        :error="payExpError"
        :has-data="payExpRows.length > 0"
        title="Оплаты и окончания подписки"
        unit-label="МСК"
        :hint="payExpHint"
        :labels="payExpLabels"
        :datasets="payExpDatasets"
        :x-markers="payExpXMarkers"
        :category-value-labels="payExpCategoryValueLabels"
        stacked
        :get-tooltip-footer="payExpTooltipFooter"
        :tooltip-filter="payExpTooltipFilter"
        y-title="Количество"
      />
    </div>
  </AdminStaffShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem 1rem;
}

.head-text {
  min-width: min(100%, 42rem);
}

.section-heading {
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-h);
}

.section-sub {
  margin: 0;
  max-width: 46rem;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
}

.mono-inline {
  font-family: var(--mono);
  font-size: 0.78rem;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.granularity-toggle {
  display: inline-flex;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  overflow: hidden;
  background: var(--surface);
}

.granularity-btn {
  margin: 0;
  padding: 0.45rem 0.75rem;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
}

.granularity-btn:hover:not(:disabled) {
  color: var(--text-h);
  background: rgba(127, 127, 127, 0.08);
}

.granularity-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.granularity-btn--active {
  color: var(--text-h);
  background: rgba(88, 214, 141, 0.14);
}

.hour-day-field {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}

.hour-day-label-text {
  white-space: nowrap;
}

.hour-day-input {
  padding: 0.35rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-size: 0.85rem;
}

.stats-hint {
  margin: 0.35rem 0 0;
  font-size: 0.76rem;
  line-height: 1.4;
  color: var(--muted);
}

.empty-hint {
  margin: 0;
  padding: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.5;
}

.chart-events {
  margin-top: 1.25rem;
  padding: 1rem 1.1rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
}

.payments-expiry-wrap {
  margin-top: 1.25rem;
}

.payments-expiry-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-bottom: 0.65rem;
}

.pay-exp-month-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-h);
}

.pay-exp-month-label-text {
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 0.72rem;
}

.pay-exp-month-input {
  font: inherit;
  font-size: 0.88rem;
  padding: 0.35rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
}

.pay-exp-month-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chart-events-title {
  margin: 0 0 0.35rem;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-h);
}

.chart-events-sub {
  margin: 0 0 1rem;
  font-size: 0.78rem;
  line-height: 1.45;
}

.chart-events-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.65rem 0.85rem;
  margin-bottom: 1rem;
}

.cef-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
}

.cef-field-grow {
  flex: 1 1 12rem;
  min-width: min(100%, 14rem);
}

.cef-field-color {
  flex: 0 0 auto;
}

.cef-label {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 0.68rem;
}

.cef-input {
  padding: 0.4rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-size: 0.85rem;
}

.cef-color {
  width: 2.75rem;
  height: 2.1rem;
  padding: 0;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  cursor: pointer;
  background: transparent;
}

.events-status {
  margin: 0 0 0.75rem;
  font-size: 0.88rem;
}

.events-status--err {
  color: var(--danger);
}

.chart-events-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.chart-events-empty {
  margin: 0;
  font-size: 0.88rem;
}

.chart-events-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
  padding: 0.55rem 0.65rem 0.55rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  border-left-width: 4px;
  background: var(--surface);
}

.chart-events-item-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.55rem;
  min-width: 0;
}

.chart-events-time {
  font-size: 0.78rem;
  color: var(--muted);
  white-space: nowrap;
}

.chart-events-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  flex-shrink: 0;
}

.chart-events-caption {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-h);
  word-break: break-word;
}

.chart-events-remove {
  font-size: 0.78rem;
}

.btn-ghost {
  margin: 0;
  padding: 0.3rem 0.55rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.btn-ghost:hover:not(:disabled) {
  color: var(--danger);
  background: rgba(248, 113, 113, 0.1);
}

.btn-ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
