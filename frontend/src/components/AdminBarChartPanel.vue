<script setup>
/**
 * Панель со столбчатым графиком: заголовок + общий компонент AdminBarChart.
 */
import AdminBarChart from './AdminBarChart.vue'

/** @typedef {{ label: string; data: number[]; rgb: [number, number, number] }} BarSeries */

defineProps({
  ariaLabel: { type: String, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  hasData: { type: Boolean, required: true },
  title: { type: String, default: '' },
  unitLabel: { type: String, default: '' },
  hint: { type: String, default: '' },
  labels: { type: Array, default: () => [] },
  /** @type {import('vue').PropType<BarSeries[]>} */
  datasets: { type: Array, default: () => [] },
  /** Вертикальные отметки на оси X (плагин staffChartMarkers). */
  xMarkers: { type: Array, default: () => [] },
  yTitle: { type: String, default: '' },
  yGrace: { type: String, default: '8%' },
  stacked: { type: Boolean, default: false },
  /** @type {import('vue').PropType<(items: import('chart.js').TooltipItem<'bar'>[]) => string | string[] | void>} */
  getTooltipFooter: { type: Function, default: null },
  /** @type {import('vue').PropType<(item: import('chart.js').TooltipItem<'bar'>) => boolean>} */
  tooltipFilter: { type: Function, default: null },
})
</script>

<template>
  <div class="admin-bar-chart-panel glass">
    <div v-if="title || unitLabel" class="chart-head">
      <h3 v-if="title" class="chart-title">{{ title }}</h3>
      <span v-if="unitLabel" class="chart-unit">{{ unitLabel }}</span>
    </div>
    <p v-if="hint" class="chart-hint">{{ hint }}</p>

    <p v-if="error" class="banner-err">{{ error }}</p>
    <p v-else-if="loading" class="loading-line">Загрузка…</p>
    <template v-else-if="!hasData">
      <p class="empty-hint">Нет данных для графика.</p>
    </template>
    <AdminBarChart
      v-else
      preset="finance"
      :aria-label="ariaLabel"
      :loading="false"
      :error="null"
      :has-data="hasData"
      :labels="labels"
      :datasets="datasets"
      :x-markers="xMarkers"
      :value-axis-title="yTitle"
      :y-grace="yGrace"
      :stacked="stacked"
      :get-tooltip-footer="getTooltipFooter"
      :tooltip-filter="tooltipFilter"
    />
  </div>
</template>

<style scoped>
.admin-bar-chart-panel {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
}

.chart-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}

.chart-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}

.chart-unit {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.chart-hint {
  margin: 0 0 0.85rem;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.5;
  max-width: 52rem;
}

.banner-err {
  padding: 0.85rem 1.1rem;
  border-radius: 14px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 0.9rem;
  margin: 0;
}

.loading-line {
  color: var(--muted);
  font-size: 0.92rem;
  margin: 0;
}

.empty-hint {
  padding: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.5;
  margin: 0;
}
</style>
