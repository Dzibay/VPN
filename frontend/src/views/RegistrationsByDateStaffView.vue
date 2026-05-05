<script setup>
import { onMounted } from 'vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import { useUsersDailyStatsChart } from '../composables/useUsersDailyStatsChart.js'

const {
  loading,
  error,
  load,
  undatedCount,
  chartPoints,
  totalUsers,
  totalWithTraffic,
  totalWithSubscriptionDevices,
  activeUsersWidget,
  pluralRuDays,
  registrationChartLabels,
  registrationChartDatasets,
  registrationTooltipTitle,
  registrationTooltipLabel,
} = useUsersDailyStatsChart()

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="Статистика по дням">
    <template #headerExtras>
      <div class="head-row">
        <div class="head-text">
          <h2 class="section-heading">Статистика по дням</h2>
        </div>
        <div class="head-actions">
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
          <dt class="stats-label">Дней на графике</dt>
          <dd class="stats-value">
            {{ chartPoints.length.toLocaleString('ru-RU') }}
            <span class="stats-unit">{{ pluralRuDays(chartPoints.length) }}</span>
          </dd>
        </div>
        <div class="stats-card">
          <dt class="stats-label">Всего пользователей</dt>
          <dd class="stats-value">
            {{ totalUsers.toLocaleString('ru-RU') }}
          </dd>
        </div>
        <div class="stats-card">
          <dt class="stats-label">С ненулевым трафиком</dt>
          <dd class="stats-value stats-value--traffic">
            {{ totalWithTraffic.toLocaleString('ru-RU') }}
          </dd>
        </div>
        <div class="stats-card">
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

    <AdminLineChartPanel
      aria-label="По дням UTC: накопление регистраций и клиентов с устройствами, активные по трафику"
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
          записей с датой.
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
  gap: 0.5rem;
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
