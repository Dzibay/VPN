<script setup>
import { onMounted, toRefs } from 'vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import {
  utcTodayIso,
  useUsersDailyStatsChart,
} from '../composables/useUsersDailyStatsChart.js'

const chart = useUsersDailyStatsChart()
const {
  granularity,
  hourDayUtc,
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

onMounted(() => {
  void load()
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
            aria-label="Шаг временной шкалы UTC"
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
            <span class="hour-day-label-text">День (UTC)</span>
            <input
              v-model="hourDayUtc"
              class="hour-day-input"
              type="date"
              :max="utcTodayIso()"
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
      Почасовой график за выбранный календарный день UTC (24 часа): накопительные регистрации и
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
</style>
