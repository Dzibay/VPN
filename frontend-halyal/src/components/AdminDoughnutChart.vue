<script setup>
/**
 * Кольцевой график (doughnut) для структуры: подписи + значения + цвета на сегментах.
 * @typedef {{ label: string; value: number; color: string }} DoughnutSlice
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chart from '../utils/chartSetup.js'
import {
  adminChartTheme,
  chartTooltipColors,
  resolveBackgroundCss,
} from '../utils/adminChartTheme.js'

const props = defineProps({
  ariaLabel: { type: String, required: true },
  hasData: { type: Boolean, default: true },
  /** @type {import('vue').PropType<DoughnutSlice[]>} */
  slices: { type: Array, default: () => [] },
  /** Подпись значения в подсказке (по умолчанию ru-RU с ₽). */
  formatValue: { type: Function, default: null },
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

function fmt(v) {
  if (props.formatValue) return props.formatValue(v)
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return `${n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
}

function drawChart() {
  const el = canvasEl.value
  if (!el || !props.hasData || !props.slices?.length) {
    destroyChart()
    return
  }
  destroyChart()
  const theme = adminChartTheme()
  const tipBgResolved = resolveBackgroundCss(theme.tooltipBg, theme.tooltipBg)
  const tipColors = chartTooltipColors(tipBgResolved, theme)

  const labels = props.slices.map((s) => s.label)
  const data = props.slices.map((s) => Number(s.value) || 0)
  const colors = props.slices.map((s) => s.color || theme.muted)

  chartInstance = new Chart(el, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: colors.map((c) => `${c}cc`),
          borderColor: theme.surfaceBg,
          borderWidth: 2,
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      animation: { duration: 520, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: theme.muted,
            font: { family: 'var(--sans)', size: 12, weight: '600' },
            padding: 12,
            usePointStyle: true,
            pointStyle: 'rectRounded',
            boxWidth: 12,
            boxHeight: 12,
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
          titleFont: { family: 'var(--sans)', size: 13, weight: '700' },
          bodyFont: { family: 'var(--mono)', size: 12 },
          callbacks: {
            label(ctx) {
              const total = ctx.dataset.data.reduce(
                (a, b) => a + (Number(b) || 0),
                0,
              )
              const v = Number(ctx.parsed) || 0
              const pct = total > 0 ? ((v / total) * 100).toFixed(1) : '0'
              return `${ctx.label}: ${fmt(v)} (${pct}%)`
            },
          },
        },
      },
    },
  })
}

watch(
  () => [props.slices, props.hasData],
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
  <div class="admin-doughnut-wrap">
    <canvas ref="canvasEl" :aria-label="ariaLabel" />
  </div>
</template>

<style scoped>
.admin-doughnut-wrap {
  position: relative;
  width: 100%;
  height: 280px;
}
</style>
