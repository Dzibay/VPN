<script setup>
/**
 * Панель со столбчатым графиком: AdminChartPanelShell + AdminBarChart.
 */
import AdminBarChart from './AdminBarChart.vue'
import AdminChartPanelShell from './AdminChartPanelShell.vue'

/** @typedef {{ label: string; data: number[]; rgb?: [number, number, number]; backgroundColor?: string; borderColor?: string; borderRadius?: number; maxBarThickness?: number; borderWidth?: number; stack?: string }} BarSeries */

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
  xMarkers: { type: Array, default: () => [] },
  stackTopLabels: { type: Array, default: () => [] },
  categoryValueLabels: { type: Array, default: () => [] },
  yTitle: { type: String, default: '' },
  yGrace: { type: String, default: '8%' },
  stacked: { type: Boolean, default: false },
  preset: { type: String, default: 'finance' },
  indexAxis: { type: String, default: 'x' },
  valueAxisMin: { type: Number, default: undefined },
  formatValueTick: { type: Function, default: null },
  getTooltipFooter: { type: Function, default: null },
  tooltipFilter: { type: Function, default: null },
  categoryMaxTicks: { type: Number, default: null },
  categoryMaxRotation: { type: Number, default: null },
  categoryMinRotation: { type: Number, default: null },
  legendStyle: { type: String, default: 'point' },
  selectedCategoryIndex: { type: Number, default: -1 },
  flush: { type: Boolean, default: false },
})

defineEmits(['categoryClick'])
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
    <AdminBarChart
      :preset="preset"
      :aria-label="ariaLabel"
      :has-data="hasData"
      :labels="labels"
      :datasets="datasets"
      :x-markers="xMarkers"
      :stack-top-labels="stackTopLabels"
      :category-value-labels="categoryValueLabels"
      :value-axis-title="yTitle"
      :y-grace="yGrace"
      :stacked="stacked"
      :index-axis="indexAxis"
      :value-axis-min="valueAxisMin"
      :format-value-tick="formatValueTick"
      :get-tooltip-footer="getTooltipFooter"
      :tooltip-filter="tooltipFilter"
      :category-max-ticks="categoryMaxTicks"
      :category-max-rotation="categoryMaxRotation"
      :category-min-rotation="categoryMinRotation"
      :legend-style="legendStyle"
      :selected-category-index="selectedCategoryIndex"
      @category-click="$emit('categoryClick', $event)"
    />
  </AdminChartPanelShell>
</template>
