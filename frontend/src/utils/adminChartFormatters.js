/** Общие форматтеры осей и подсказок админских графиков. */

export function formatChartCountTick(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('ru-RU')
}

export function formatChartMoneyTick(v, { maxFractionDigits = 0 } = {}) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('ru-RU', { maximumFractionDigits: maxFractionDigits })
}

/** @param {import('chart.js').TooltipItem<'line'>} ctx */
export function chartLineCountTooltipLabel(ctx) {
  return `${ctx.dataset.label}: ${formatChartCountTick(ctx.parsed.y)}`
}

/** @param {import('chart.js').TooltipItem<'bar'>[]} items */
export function chartBarStackedMoneyTooltipFooter(items) {
  const first = items?.[0]
  if (!first) return ''
  const idx = first.dataIndex
  const chart = first.chart
  let sum = 0
  for (const ds of chart.data.datasets) {
    const v = Number(ds.data[idx])
    if (Number.isFinite(v)) sum += v
  }
  return `Всего: ${sum.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
}

/** @param {import('chart.js').TooltipItem<'bar'>[]} items */
export function chartBarMoneyTooltipFooter(items) {
  const first = items?.[0]
  if (!first) return ''
  const v = Number(first.raw)
  if (!Number.isFinite(v)) return ''
  return `Всего: ${v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
}

/** @param {import('chart.js').TooltipItem<'bar'>} item */
export function chartBarPositiveTooltipFilter(item) {
  return Number(item.raw) > 0
}
