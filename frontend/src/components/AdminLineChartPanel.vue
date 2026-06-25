<script setup>
/**
 * Панель с линейным графиком: AdminChartPanelShell + AdminLineChart.
 */
import AdminChartPanelShell from './AdminChartPanelShell.vue'
import AdminLineChart from './AdminLineChart.vue'

/** @typedef {{ label: string; data: number[]; rgb: [number, number, number]; filled?: boolean; borderWidth?: number; hidden?: boolean }} LineSeries */

defineProps({
  ariaLabel: { type: String, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  hasData: { type: Boolean, required: true },
  title: { type: String, default: '' },
  unitLabel: { type: String, default: '' },
  hint: { type: String, default: '' },
  labels: { type: Array, default: () => [] },
  /** @type {import('vue').PropType<LineSeries[]>} */
  datasets: { type: Array, default: () => [] },
  yTitle: { type: String, default: '' },
  yGrace: { type: String, default: '8%' },
  getTooltipTitle: { type: Function, default: null },
  getTooltipLabel: { type: Function, default: null },
  formatYTick: { type: Function, default: null },
  /** @type {import('vue').PropType<Array<{ index: number; title: string; color: string; kind?: string }>>} */
  eventMarkers: { type: Array, default: () => [] },
  flush: { type: Boolean, default: false },
})
</script>

<template>
  <AdminChartPanelShell
    :title="title"
    :unit-label="unitLabel"
    :hint="hint"
    :loading="loading"
    :error="error"
    :has-data="hasData"
    :flush="flush"
  >
    <template #empty>
      <slot name="empty">
        <p class="empty-hint">Нет данных для графика.</p>
      </slot>
    </template>
    <AdminLineChart
      :aria-label="ariaLabel"
      :labels="labels"
      :datasets="datasets"
      :y-title="yTitle"
      :y-grace="yGrace"
      :get-tooltip-title="getTooltipTitle"
      :get-tooltip-label="getTooltipLabel"
      :format-y-tick="formatYTick"
      :event-markers="eventMarkers"
    />
  </AdminChartPanelShell>
</template>
