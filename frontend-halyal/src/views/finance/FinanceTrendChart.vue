<script setup>
/**
 * Динамика по месяцам: сгруппированные столбцы + линия на левой оси и опциональная
 * линия на правой оси (mixed bar+line Chart.js). Используется в двух режимах:
 *  - кассовый: бары «Чистая выручка»/«Расходы» + линия «Чистая прибыль»;
 *  - начисление: бары «Заработано»/«Расходы» + правая линия «Заморожено» (остаток обязательств).
 *
 * @typedef {{ label: string; data: number[]; rgb: [number, number, number] }} Series
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chart from '../../utils/chartSetup.js'
import {
  adminChartTheme,
  chartTooltipColors,
  financeBarGridColor,
  financeBarTickColor,
  rgba,
  resolveBackgroundCss,
} from '../../utils/adminChartTheme.js'

const props = defineProps({
  ariaLabel: { type: String, required: true },
  hasData: { type: Boolean, default: true },
  labels: { type: Array, default: () => [] },
  /** @type {import('vue').PropType<Series[]>} Столбцы (1–2). */
  bars: { type: Array, default: () => [] },
  /** @type {import('vue').PropType<Series | null>} Линия на левой оси (та же шкала, что и столбцы). */
  line: { type: Object, default: null },
  /** @type {import('vue').PropType<Series | null>} Линия на правой оси (отдельная шкала, напр. остаток обязательств). */
  secondary: { type: Object, default: null },
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

function fmtMoney(v, opts = {}) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('ru-RU', {
    minimumFractionDigits: opts.frac ?? 0,
    maximumFractionDigits: opts.frac ?? 0,
  })
}

function drawChart() {
  const el = canvasEl.value
  if (!el || !props.hasData || props.labels.length === 0) {
    destroyChart()
    return
  }
  destroyChart()
  const theme = adminChartTheme()
  const tick = financeBarTickColor()
  const grid = financeBarGridColor()
  const tipBgResolved = resolveBackgroundCss(theme.tooltipBg, theme.tooltipBg)
  const tipColors = chartTooltipColors(tipBgResolved, theme)
  const n = props.labels.length

  const datasets = []
  for (const b of props.bars) {
    datasets.push({
      type: 'bar',
      label: b.label,
      data: [...b.data],
      backgroundColor: rgba(b.rgb, 0.78),
      borderColor: rgba(b.rgb, 0.92),
      borderWidth: 0,
      borderRadius: 4,
      maxBarThickness: 38,
      categoryPercentage: 0.7,
      barPercentage: 0.92,
      yAxisID: 'y',
      order: 2,
    })
  }
  if (props.line) {
    datasets.push({
      type: 'line',
      label: props.line.label,
      data: [...props.line.data],
      borderColor: rgba(props.line.rgb, 0.98),
      borderWidth: 2.75,
      tension: 0.35,
      cubicInterpolationMode: 'monotone',
      fill: false,
      pointRadius: n > 24 ? 0 : 3.5,
      pointHoverRadius: 6,
      pointBackgroundColor: theme.surfaceBg,
      pointBorderColor: rgba(props.line.rgb, 0.95),
      pointBorderWidth: 2,
      yAxisID: 'y',
      order: 0,
    })
  }
  if (props.secondary) {
    datasets.push({
      type: 'line',
      label: props.secondary.label,
      data: [...props.secondary.data],
      borderColor: rgba(props.secondary.rgb, 0.98),
      borderWidth: 2.5,
      borderDash: [6, 4],
      tension: 0.35,
      cubicInterpolationMode: 'monotone',
      fill: true,
      backgroundColor: (c) => {
        const chart = c.chart
        const { ctx: cctx, chartArea } = chart
        if (!chartArea) return rgba(props.secondary.rgb, 0.08)
        const g = cctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
        g.addColorStop(0, rgba(props.secondary.rgb, 0.18))
        g.addColorStop(1, rgba(props.secondary.rgb, 0))
        return g
      },
      pointRadius: n > 24 ? 0 : 3,
      pointHoverRadius: 6,
      pointBackgroundColor: theme.surfaceBg,
      pointBorderColor: rgba(props.secondary.rgb, 0.95),
      pointBorderWidth: 2,
      yAxisID: 'y1',
      order: 1,
    })
  }

  const scales = {
    x: {
      ticks: {
        color: tick,
        font: { family: 'var(--sans)', size: 11 },
        maxRotation: 45,
        autoSkip: true,
        maxTicksLimit: 18,
      },
      grid: { color: grid, drawBorder: false, tickLength: 0 },
    },
    y: {
      beginAtZero: true,
      grace: '8%',
      ticks: {
        color: tick,
        font: { family: 'var(--mono)', size: 11 },
        padding: 8,
        callback: (v) => fmtMoney(v),
      },
      grid: { color: grid, drawBorder: false },
      title: {
        display: true,
        text: '₽',
        color: tick,
        font: { family: 'var(--sans)', size: 11, weight: '600' },
      },
    },
  }
  if (props.secondary) {
    scales.y1 = {
      position: 'right',
      beginAtZero: true,
      grace: '8%',
      ticks: {
        color: rgba(props.secondary.rgb, 0.95),
        font: { family: 'var(--mono)', size: 11 },
        padding: 8,
        callback: (v) => fmtMoney(v),
      },
      grid: { drawOnChartArea: false, drawBorder: false },
      title: {
        display: true,
        text: props.secondary.label,
        color: rgba(props.secondary.rgb, 0.95),
        font: { family: 'var(--sans)', size: 11, weight: '600' },
      },
    }
  }

  chartInstance = new Chart(el, {
    type: 'bar',
    data: { labels: [...props.labels], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 560, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          position: 'top',
          align: 'start',
          labels: {
            color: tick,
            font: { family: 'var(--sans)', size: 12, weight: '600' },
            padding: 14,
            usePointStyle: true,
            pointStyle: 'rectRounded',
          },
        },
        tooltip: {
          backgroundColor: tipBgResolved,
          titleColor: tipColors.titleColor,
          bodyColor: tipColors.bodyColor,
          borderColor: tipColors.borderColor,
          borderWidth: 1,
          padding: 12,
          cornerRadius: 12,
          displayColors: true,
          boxPadding: 6,
          titleFont: { family: 'var(--sans)', size: 13, weight: '700' },
          bodyFont: { family: 'var(--mono)', size: 12 },
          callbacks: {
            label(ctx) {
              const v = Number(ctx.parsed.y)
              return `${ctx.dataset.label}: ${fmtMoney(v, { frac: 2 })} ₽`
            },
          },
        },
      },
      scales,
    },
  })
}

watch(
  () => [props.labels, props.bars, props.line, props.secondary, props.hasData],
  async () => {
    await nextTick()
    drawChart()
  },
  { deep: true, immediate: true, flush: 'post' },
)

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <div class="admin-chart-wrap admin-chart-wrap--finance">
    <canvas ref="canvasEl" :aria-label="ariaLabel" />
  </div>
</template>
