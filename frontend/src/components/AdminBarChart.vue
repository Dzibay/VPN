<script setup>
/**
 * Общий столбчатый Chart.js: одинаковая высота/обёртка, как на странице «Финансы».
 * @typedef {{ label: string; data: number[]; rgb?: [number, number, number]; backgroundColor?: string; borderColor?: string; borderRadius?: number; maxBarThickness?: number; borderWidth?: number; stack?: string }} BarDatasetInput
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chart from '../utils/chartSetup.js'
import {
  adminChartTheme,
  chartTooltipColors,
  financeBarGridColor,
  financeBarTickColor,
  rgba,
  resolveBackgroundCss,
} from '../utils/adminChartTheme.js'

const props = defineProps({
  ariaLabel: { type: String, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  hasData: { type: Boolean, default: true },
  labels: { type: Array, default: () => [] },
  /** @type {import('vue').PropType<BarDatasetInput[]>} */
  datasets: { type: Array, default: () => [] },
  /** Вертикальные отметки на категориальной оси (плагин staffChartMarkers). */
  xMarkers: { type: Array, default: () => [] },
  /** Подписи над вершиной stack (плагин barStackTopLabels). */
  stackTopLabels: { type: Array, default: () => [] },
  /** Подписи по центру категории над столбцами (плагин categoryValueLabels). */
  categoryValueLabels: { type: Array, default: () => [] },
  /** «finance» — оси/легенда/плотность как на странице «Финансы». */
  preset: { type: String, default: '' },
  stacked: { type: Boolean, default: false },
  /** @type {import('vue').PropType<'x' | 'y'>} */
  indexAxis: { type: String, default: 'x' },
  yGrace: { type: String, default: '8%' },
  valueAxisTitle: { type: String, default: '' },
  valueAxisMin: { type: Number, default: undefined },
  /** @type {import('vue').PropType<(v: unknown) => string>} */
  formatValueTick: { type: Function, default: null },
  /** @type {import('vue').PropType<(items: import('chart.js').TooltipItem<'bar'>[]) => string | string[] | void>} */
  getTooltipFooter: { type: Function, default: null },
  /** @type {import('vue').PropType<(item: import('chart.js').TooltipItem<'bar'>) => boolean>} */
  tooltipFilter: { type: Function, default: null },
  tickColor: { type: String, default: '' },
  gridColor: { type: String, default: '' },
  /** Пусто — фон и подписи как у AdminLineChartPanel (--card-bg). */
  tooltipBg: { type: String, default: '' },
  /** «point» — группированные столбцы по умолчанию; «box» — как «Финансы». */
  legendStyle: { type: String, default: 'point' },
  barBorderRadius: { type: Number, default: 6 },
  barMaxThickness: { type: Number, default: null },
  categoryPercentage: { type: Number, default: null },
  barPercentage: { type: Number, default: null },
  categoryMaxTicks: { type: Number, default: null },
  categoryMaxRotation: { type: Number, default: null },
  categoryMinRotation: { type: Number, default: null },
})

const canvasEl = ref(null)

/** @type {Chart | null} */
let chartInstance = null

function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
}

function parsedBarValue(ctx) {
  return props.indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y
}

function drawChart() {
  const el = canvasEl.value
  if (
    !el ||
    props.loading ||
    props.error ||
    !props.hasData ||
    props.labels.length === 0 ||
    !props.datasets?.length
  ) {
    destroyChart()
    return
  }
  for (const ds of props.datasets) {
    if (!Array.isArray(ds.data) || ds.data.length !== props.labels.length) {
      destroyChart()
      return
    }
  }

  destroyChart()
  const theme = adminChartTheme()
  const fin = props.preset === 'finance'
  const tick =
    props.tickColor || (fin ? financeBarTickColor() : theme.muted)
  const grid =
    props.gridColor || (fin ? financeBarGridColor() : theme.grid)
  const tipBg = props.tooltipBg || theme.tooltipBg
  const tipBgResolved = resolveBackgroundCss(tipBg, theme.tooltipBg)
  const tipColors = chartTooltipColors(tipBgResolved, theme)

  const legendStyle = fin ? 'box' : props.legendStyle
  const barBorderRadius = fin ? 4 : props.barBorderRadius

  const defaultMaxThick =
    props.barMaxThickness ??
    (props.stacked ? 48 : props.indexAxis === 'y' ? 48 : 28)

  const borderWidthDefault = props.stacked ? 0 : 1

  const catPct =
    props.categoryPercentage ?? (fin || props.stacked ? 0.65 : 0.72)
  const barPct = props.barPercentage ?? 0.9

  const catMaxRot =
    props.categoryMaxRotation != null
      ? props.categoryMaxRotation
      : fin && props.indexAxis === 'x'
        ? 45
        : props.indexAxis === 'x'
          ? 40
          : 0

  const chartDatasets = props.datasets.map((ds, idx) => {
    const base = {
      label: ds.label,
      data: ds.data,
      borderSkipped: false,
      borderRadius: ds.borderRadius ?? barBorderRadius,
      maxBarThickness: ds.maxBarThickness ?? defaultMaxThick,
      categoryPercentage: catPct,
      barPercentage: barPct,
      ...(ds.stack ? { stack: ds.stack } : {}),
    }
    if (ds.backgroundColor) {
      return {
        ...base,
        backgroundColor: ds.backgroundColor,
        borderColor: ds.borderColor ?? ds.backgroundColor,
        borderWidth: ds.borderWidth ?? 0,
        hoverBackgroundColor: ds.hoverBackgroundColor,
        hoverBorderColor: ds.hoverBorderColor,
      }
    }
    const rgb = ds.rgb
    if (!rgb || !Array.isArray(rgb) || rgb.length < 3) {
      return {
        ...base,
        backgroundColor: rgba(theme.accent, 0.82),
        borderColor: rgba(theme.accent, 0.95),
        borderWidth: borderWidthDefault,
        hoverBackgroundColor: rgba(theme.accent, 0.95),
        hoverBorderColor: rgba(theme.accent, 1),
      }
    }
    return {
      ...base,
      backgroundColor: rgba(rgb, idx === 0 ? 0.82 : 0.75),
      borderColor: rgba(rgb, 0.95),
      borderWidth: borderWidthDefault,
      hoverBackgroundColor: rgba(rgb, 0.95),
      hoverBorderColor: rgba(rgb, 1),
    }
  })

  const valueAxisId = props.indexAxis === 'y' ? 'x' : 'y'
  const categoryAxisId = props.indexAxis === 'y' ? 'y' : 'x'

  const categoryTicks = {
    color: tick,
    font: { family: 'var(--sans)', size: 11 },
    ...(props.indexAxis === 'x'
      ? {
          maxRotation: catMaxRot,
          minRotation:
            props.categoryMinRotation != null ? props.categoryMinRotation : 0,
          autoSkip: true,
          maxTicksLimit:
            props.categoryMaxTicks != null ? props.categoryMaxTicks : 22,
        }
      : {
          maxRotation:
            props.categoryMaxRotation != null ? props.categoryMaxRotation : 0,
          minRotation:
            props.categoryMinRotation != null ? props.categoryMinRotation : 0,
        }),
  }

  const valueTicks = {
    color: tick,
    font: { family: 'var(--mono)', size: 11 },
    padding: 8,
    ...(props.formatValueTick ? {} : { precision: 0 }),
    callback(v) {
      if (props.formatValueTick) return props.formatValueTick(v)
      const n = Number(v)
      if (!Number.isFinite(n)) return ''
      return n.toLocaleString('ru-RU')
    },
  }

  /** @type {import('chart.js').ChartOptions<'bar'>} */
  const options = {
    indexAxis: props.indexAxis,
    responsive: true,
    maintainAspectRatio: false,
    layout: {
      padding: {
        top: Array.isArray(props.categoryValueLabels) && props.categoryValueLabels.length
          ? 18
          : 0,
      },
    },
    interaction: { mode: 'index', intersect: false },
    animation: {
      duration: 520,
      easing: 'easeOutQuart',
    },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        align: legendStyle === 'point' ? 'start' : 'center',
        labels: {
          color: tick,
          font: {
            family: 'var(--sans)',
            size: 12,
            weight: legendStyle === 'point' ? '600' : '400',
          },
          ...(legendStyle === 'point'
            ? {
                padding: 14,
                usePointStyle: true,
                pointStyle: 'rectRounded',
              }
            : {
                boxWidth: 14,
                boxHeight: 14,
              }),
        },
      },
      tooltip: {
        backgroundColor: tipBgResolved,
        titleColor: tipColors.titleColor,
        bodyColor: tipColors.bodyColor,
        footerColor: tipColors.footerColor,
        borderColor: tipColors.borderColor,
        borderWidth: 1,
        padding: 12,
        cornerRadius: 12,
        displayColors: true,
        boxPadding: 6,
        titleFont: { family: 'var(--sans)', size: 13, weight: '700' },
        bodyFont: { family: 'var(--mono)', size: 12 },
        ...(props.tooltipFilter ? { filter: props.tooltipFilter } : {}),
        itemSort: (a, b) =>
          Number(parsedBarValue(b)) - Number(parsedBarValue(a)),
        callbacks: {
          title(items) {
            const i = items[0]?.dataIndex
            if (i == null) return ''
            return props.labels[i] ?? ''
          },
          label(ctx) {
            const raw = parsedBarValue(ctx)
            const v = Number(raw).toLocaleString('ru-RU')
            return `${ctx.dataset.label}: ${v}`
          },
          ...(props.getTooltipFooter
            ? {
                footer(items) {
                  return props.getTooltipFooter(items)
                },
              }
            : {}),
        },
      },
      staffChartMarkers: {
        markers: Array.isArray(props.xMarkers) ? [...props.xMarkers] : [],
      },
      barStackTopLabels: {
        items: Array.isArray(props.stackTopLabels) ? [...props.stackTopLabels] : [],
      },
      categoryValueLabels: {
        items: Array.isArray(props.categoryValueLabels)
          ? [...props.categoryValueLabels]
          : [],
      },
    },
    scales: {
      [categoryAxisId]: {
        stacked: props.stacked,
        ticks: categoryTicks,
        grid: {
          color: grid,
          drawBorder: false,
          tickLength: 0,
        },
      },
      [valueAxisId]: {
        stacked: props.stacked,
        beginAtZero: true,
        ...(props.indexAxis === 'x' ? { grace: props.yGrace } : {}),
        ...(props.valueAxisMin != null && Number.isFinite(props.valueAxisMin)
          ? { min: props.valueAxisMin }
          : {}),
        ticks: valueTicks,
        grid: {
          color: grid,
          drawBorder: false,
        },
        title: {
          display: Boolean(props.valueAxisTitle),
          text: props.valueAxisTitle,
          color: tick,
          font: { family: 'var(--sans)', size: 11, weight: '600' },
          padding:
            props.indexAxis === 'y'
              ? { left: 4, right: 0 }
              : { bottom: 4, top: 0 },
        },
      },
    },
  }

  chartInstance = new Chart(el, {
    type: 'bar',
    data: {
      labels: [...props.labels],
      datasets: chartDatasets,
    },
    options,
  })
}

watch(
  () => [
    props.loading,
    props.error,
    props.hasData,
    props.labels,
    props.datasets,
    props.xMarkers,
    props.stackTopLabels,
    props.categoryValueLabels,
    props.preset,
    props.stacked,
    props.indexAxis,
    props.yGrace,
    props.valueAxisTitle,
    props.valueAxisMin,
    props.formatValueTick,
    props.getTooltipFooter,
    props.tooltipFilter,
    props.tickColor,
    props.gridColor,
    props.tooltipBg,
    props.legendStyle,
    props.barBorderRadius,
    props.barMaxThickness,
    props.categoryPercentage,
    props.barPercentage,
    props.categoryMaxTicks,
    props.categoryMaxRotation,
    props.categoryMinRotation,
  ],
  async () => {
    await nextTick()
    drawChart()
  },
  { deep: true, immediate: true, flush: 'post' },
)

onBeforeUnmount(() => {
  destroyChart()
})

defineExpose({ drawChart, destroyChart })
</script>

<template>
  <div class="admin-chart-wrap admin-chart-wrap--finance">
    <canvas ref="canvasEl" :aria-label="ariaLabel" />
  </div>
</template>
