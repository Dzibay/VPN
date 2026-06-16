/**
 * Подписи по центру категории над столбцами (над вершиной самого высокого бара дня).
 * options.plugins.categoryValueLabels.items = [{ values, color?, colors? }]
 */

/** @typedef {{ values: number[]; color?: string; colors?: string[] }} CategoryValueLabelItem */

export const categoryValueLabelsPlugin = {
  id: 'categoryValueLabels',

  /** @param {import('chart.js').Chart} chart */
  afterDatasetsDraw(chart) {
    const items =
      chart.options.plugins?.categoryValueLabels?.items ??
      /** @type {CategoryValueLabelItem[]} */ ([])
    if (!items.length) return

    const { ctx, chartArea, data, scales } = chart
    if (!chartArea || !data.labels?.length || !data.datasets?.length) return

    const xScale = scales.x
    if (!xScale) return

    const n = data.labels.length
    const defaultColor = 'rgba(148, 163, 184, 0.88)'

    ctx.save()
    try {
      for (const item of items) {
        const values = item.values
        if (!Array.isArray(values) || values.length !== n) continue
        const colors = Array.isArray(item.colors) ? item.colors : null

        ctx.font = '600 11px var(--mono, ui-monospace, monospace)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'

        for (let dataIndex = 0; dataIndex < n; dataIndex += 1) {
          const val = Number(values[dataIndex])
          if (!Number.isFinite(val) || val <= 0) continue

          const centerX = xScale.getPixelForValue(dataIndex)
          if (!Number.isFinite(centerX)) continue

          let topY = Infinity
          for (let di = 0; di < data.datasets.length; di += 1) {
            const meta = chart.getDatasetMeta(di)
            if (meta.hidden) continue
            const el = meta.data[dataIndex]
            if (!el || el.hidden) continue
            if (typeof el.y !== 'number' || !Number.isFinite(el.y)) continue
            if (el.y < topY) topY = el.y
          }

          const y =
            Number.isFinite(topY) && topY !== Infinity
              ? Math.max(chartArea.top + 10, topY - 4)
              : Math.max(chartArea.top + 10, chartArea.bottom - 20)

          ctx.fillStyle =
            (colors && colors[dataIndex]) || item.color || defaultColor
          ctx.fillText(val.toLocaleString('ru-RU'), centerX, y)
        }
      }
    } finally {
      ctx.restore()
    }
  },
}
