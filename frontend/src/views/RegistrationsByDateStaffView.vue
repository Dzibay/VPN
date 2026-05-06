<script setup>
import { computed, onMounted, ref, toRefs } from 'vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import { fetchJson } from '../api/client.js'
import { mapStaffChartEventsToMarkers } from '../utils/chartStaffMarkersPlugin.js'
import {
  mskTodayIso,
  utcTodayIso,
  useUsersDailyStatsChart,
} from '../composables/useUsersDailyStatsChart.js'

/** @typedef {{ id: number; event_at: string; title: string; color: string; created_at: string }} ChartEventRow */

const chartEvents = ref(/** @type {ChartEventRow[]} */ ([]))
const eventsLoading = ref(false)
const eventsError = ref(null)
const eventsBusy = ref(false)
const newEventTitle = ref('')
const newEventColor = ref('#58D68D')
const newEventDatetimeLocal = ref('')

function formatChartEventDisplay(iso) {
  if (iso == null || iso === '') return '—'
  try {
    return (
      new Date(iso).toLocaleString('ru-RU', {
        timeZone: 'Europe/Moscow',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }) + ' МСК'
    )
  } catch {
    return String(iso)
  }
}

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
  totalUsers,
  totalWithTraffic,
  totalWithSubscriptionDevices,
  activeUsersWidget,
  pluralRuBuckets,
  bucketAxisLabel,
  chartAriaLabel,
  registrationChartLabels,
  registrationChartDatasets,
  registrationTooltipTitle,
  registrationTooltipLabel,
  undatedCount,
} = toRefs(chart)

const { setGranularity, load } = chart

const chartEventMarkers = computed(() =>
  mapStaffChartEventsToMarkers(
    chartPoints.value,
    granularity.value,
    chartEvents.value,
  ),
)

onMounted(() => {
  void load()
  void loadChartEvents()
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
            aria-label="Шаг временной шкалы: дни по UTC, часы по Москве"
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
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading"
            @click="load"
          >
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </template>

    <section class="stats" aria-live="polite">
      <p v-if="loading" class="stats-status muted">Загрузка…</p>
      <p v-else-if="error" class="stats-status stats-status--err">
        Не удалось загрузить сводку (подробности ниже).
      </p>
      <dl v-else class="stats-grid">
        <div class="stats-card">
          <dt class="stats-label">{{ bucketAxisLabel }}</dt>
          <dd class="stats-value">
            {{ chartPoints.length.toLocaleString('ru-RU') }}
            <span class="stats-unit">{{
              pluralRuBuckets(chartPoints.length, granularity)
            }}</span>
          </dd>
        </div>
        <div class="stats-card">
          <dt class="stats-label">Всего пользователей</dt>
          <dd class="stats-value">
            {{ totalUsers.toLocaleString('ru-RU') }}
          </dd>
        </div>
        <div v-if="granularity === 'day'" class="stats-card">
          <dt class="stats-label">С ненулевым трафиком</dt>
          <dd class="stats-value stats-value--traffic">
            {{ totalWithTraffic.toLocaleString('ru-RU') }}
          </dd>
        </div>
        <div v-if="granularity === 'day'" class="stats-card">
          <dt class="stats-label">Активные сегодня (UTC)</dt>
          <dd class="stats-value stats-value--active">
            {{ activeUsersWidget.today }}
          </dd>
        </div>
        <div class="stats-card">
          <dt class="stats-label">С записью устройства</dt>
          <dd class="stats-value stats-value--devices">
            {{ totalWithSubscriptionDevices.toLocaleString('ru-RU') }}
          </dd>
        </div>
      </dl>
    </section>

    <p v-if="granularity === 'hour'" class="stats-hint">
      Почасовой график за выбранный календарный день UTC (24 часа); время на оси — Москва (МСК). Накопительные регистрации и
      первые подключения устройств. Серии про трафик не показываются.
    </p>

    <AdminLineChartPanel
      :aria-label="chartAriaLabel"
      :loading="loading"
      :error="error"
      :has-data="chartPoints.length > 0"
      y-title="Пользователей"
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
              formatChartEventDisplay(ev.event_at)
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

.stats {
  margin-bottom: 1rem;
}

.stats-status {
  margin: 0;
  font-size: 0.92rem;
}

.stats-status--err {
  color: var(--danger);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr));
  gap: 0.75rem 1rem;
  margin: 0;
}

.stats-card {
  margin: 0;
  padding: 0.65rem 0.75rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
}

.stats-label {
  margin: 0 0 0.35rem;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.stats-value {
  margin: 0;
  font-size: 1.12rem;
  font-weight: 800;
  font-family: var(--heading, inherit);
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  line-height: 1.2;
}

.stats-value--traffic {
  color: #fb923c;
}

@media (prefers-color-scheme: light) {
  .stats-value--traffic {
    color: #ea580c;
  }
}

.stats-value--active {
  color: #38bdf8;
}

@media (prefers-color-scheme: light) {
  .stats-value--active {
    color: #0284c7;
  }
}

.stats-value--devices {
  color: #a78bfa;
}

@media (prefers-color-scheme: light) {
  .stats-value--devices {
    color: #7c3aed;
  }
}

.stats-unit {
  margin-left: 0.25rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: lowercase;
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
