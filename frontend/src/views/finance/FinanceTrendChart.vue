<script setup>
/**
 * Динамика по месяцам: сгруппированные столбцы «Чистая выручка» и «Расходы»
 * плюс линия «Чистая прибыль» (mixed bar+line Chart.js).
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
  revenueNet: { type: Array, default: () => [] },
  expenses: { type: Array, default: () => [] },
  profit: { type: Array, default: () => [] },
})

const REVENUE_RGB = [56, 214, 141]
const EXPENSE_RGB = [239, 68, 68]
const PROFIT_RGB = [56, 189, 248]

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

  chartInstance = new Chart(el, {
    type: 'bar',
    data: {
      labels: [...props.labels],
      datasets: [
        {
          type: 'bar',
          label: 'Чистая выручка',
          data: [...props.revenueNet],
          backgroundColor: rgba(REVENUE_RGB, 0.82),
          borderColor: rgba(REVENUE_RGB, 0.95),
          borderWidth: 0,
          borderRadius: 4,
          maxBarThickness: 38,
          categoryPercentage: 0.7,
          barPercentage: 0.92,
          order: 2,
        },
        {
          type: 'bar',
          label: 'Расходы',
          data: [...props.expenses],
          backgroundColor: rgba(EXPENSE_RGB, 0.72),
          borderColor: rgba(EXPENSE_RGB, 0.9),
          borderWidth: 0,
          borderRadius: 4,
          maxBarThickness: 38,
          categoryPercentage: 0.7,
          barPercentage: 0.92,
          order: 2,
        },
        {
          type: 'line',
          label: 'Чистая прибыль',
          data: [...props.profit],
          borderColor: rgba(PROFIT_RGB, 0.98),
          borderWidth: 2.75,
          tension: 0.35,
          cubicInterpolationMode: 'monotone',
          fill: false,
          pointRadius: props.labels.length > 24 ? 0 : 3.5,
          pointHoverRadius: 6,
          pointBackgroundColor: theme.surfaceBg,
          pointBorderColor: rgba(PROFIT_RGB, 0.95),
          pointBorderWidth: 2,
          order: 0,
        },
      ],
    },
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
      scales: {
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
      },
    },
  })
}

watch(
  () => [props.labels, props.revenueNet, props.expenses, props.profit, props.hasData],
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
