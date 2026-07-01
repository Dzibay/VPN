<script setup>
/**
 * Линейный Chart.js без оболочки панели (см. AdminLineChartPanel).
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chart from '../utils/chartSetup.js'
import { adminChartTheme, chartTooltipColors, rgba, resolveBackgroundCss } from '../utils/adminChartTheme.js'

/** @typedef {{ label: string; data: number[]; rgb: [number, number, number]; filled?: boolean; borderWidth?: number; hidden?: boolean }} LineSeries */

const props = defineProps({
  ariaLabel: { type: String, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  hasData: { type: Boolean, default: true },
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
  /** admin-chart-wrap--tall | admin-chart-wrap--finance */
  wrapClass: { type: String, default: 'admin-chart-wrap--tall' },
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
  const tipBgResolved = resolveBackgroundCss(theme.tooltipBg, theme.tooltipBg)
  const tipColors = chartTooltipColors(tipBgResolved, theme)
  const surfaceBg = theme.surfaceBg
  const n = props.labels.length

  const chartDatasets = props.datasets.map((ds, idx) => {
    const rgb = ds.rgb
    const filled = ds.filled !== false
    const bw = ds.borderWidth ?? (idx === 0 ? 2.75 : 2.25)
    return {
      label: ds.label,
      data: ds.data,
      hidden: ds.hidden === true,
      borderColor: rgba(rgb, idx === 0 ? 0.95 : 0.94),
      borderWidth: bw,
      tension: 0.35,
      cubicInterpolationMode: 'monotone',
      fill: filled,
      backgroundColor: filled
        ? (c) => {
            const chart = c.chart
            const { ctx: cctx, chartArea } = chart
            if (!chartArea) return rgba(rgb, 0.1)
            const g = cctx.createLinearGradient(
              0,
              chartArea.top,
              0,
              chartArea.bottom,
            )
            const topA = idx === 0 ? 0.28 : 0.2
            const midA = idx === 0 ? 0.07 : 0.06
            g.addColorStop(0, rgba(rgb, topA))
            g.addColorStop(idx === 0 ? 0.55 : 0.65, rgba(rgb, midA))
            g.addColorStop(1, rgba(rgb, 0))
            return g
          }
        : undefined,
      pointRadius: n > 100 ? 0 : n > 48 ? 2 : idx === 0 ? 3.5 : 3,
      pointHoverRadius: 6,
      pointBorderWidth: 2,
      pointBackgroundColor: surfaceBg,
      pointBorderColor: rgba(rgb, idx === 0 ? 0.9 : 0.88),
      pointHoverBorderColor: rgba(rgb, 1),
      pointHoverBackgroundColor: rgba(rgb, idx === 0 ? 0.25 : 0.2),
    }
  })

  chartInstance = new Chart(el, {
    type: 'line',
    data: {
      labels: [...props.labels],
      datasets: chartDatasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: {
        duration: 680,
        easing: 'easeOutQuart',
      },
      elements: {
        line: {
          borderJoinStyle: 'round',
          borderCapStyle: 'round',
        },
      },
      plugins: {
        staffChartMarkers: {
          markers: Array.isArray(props.eventMarkers) ? [...props.eventMarkers] : [],
        },
        legend: {
          position: 'top',
          align: 'start',
          labels: {
            color: theme.muted,
            font: { family: 'var(--sans)', size: 12, weight: '600' },
            padding: 14,
            usePointStyle: true,
            pointStyle: 'circle',
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
          itemSort: (a, b) =>
            Number(b?.parsed?.y ?? 0) - Number(a?.parsed?.y ?? 0),
          callbacks: {
            title(items) {
              const i = items[0]?.dataIndex
              if (i == null) return ''
              if (props.getTooltipTitle) return props.getTooltipTitle(i) ?? ''
              return props.labels[i] ?? ''
            },
            label(ctx) {
              if (props.getTooltipLabel) {
                const out = props.getTooltipLabel(ctx)
                if (out == null) return ''
                if (Array.isArray(out)) return out
                return out
              }
              const raw = ctx.parsed.y
              const v =
                props.formatYTick != null
                  ? props.formatYTick(raw)
                  : Number(raw).toLocaleString('ru-RU')
              return `${ctx.dataset.label}: ${v}`
            },
            afterBody(items) {
              if (!items?.length || !props.eventMarkers?.length) return []
              const i = items[0]?.dataIndex
              if (i == null) return []
              const lines = []
              for (const m of props.eventMarkers) {
                if (m.index === i && m.title) {
                  lines.push(
                    m.kind === 'today' ? m.title : `Событие: ${m.title}`,
                  )
                }
              }
              return lines
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: theme.muted,
            maxRotation: 40,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 22,
            font: { family: 'var(--sans)', size: 11 },
          },
          grid: {
            color: theme.grid,
            drawBorder: false,
            tickLength: 0,
          },
        },
        y: {
          beginAtZero: true,
          grace: props.yGrace,
          ticks: {
            color: theme.muted,
            font: { family: 'var(--mono)', size: 11 },
            padding: 8,
            callback(v) {
              return props.formatYTick != null
                ? props.formatYTick(Number(v))
                : Number(v).toLocaleString('ru-RU')
            },
          },
          grid: {
            color: theme.grid,
            drawBorder: false,
          },
          title: {
            display: Boolean(props.yTitle),
            text: props.yTitle,
            color: theme.muted,
            font: { family: 'var(--sans)', size: 11, weight: '600' },
            padding: { bottom: 4, top: 0 },
          },
        },
      },
    },
  })
}

watch(
  () => [
    props.loading,
    props.error,
    props.hasData,
    props.labels,
    props.datasets,
    props.yTitle,
    props.yGrace,
    props.eventMarkers,
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
  <div class="admin-chart-wrap" :class="wrapClass">
    <canvas ref="canvasEl" :aria-label="ariaLabel" />
  </div>
</template>
