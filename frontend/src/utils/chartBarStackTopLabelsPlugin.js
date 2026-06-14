/**
 * Подписи над вершиной выбранного stack в grouped/stacked bar chart.
 * options.plugins.barStackTopLabels.items = [{ stack, values, color? }]
 */

/** @typedef {{ stack: string; values: number[]; color?: string }} BarStackTopLabelItem */

export const barStackTopLabelsPlugin = {
  id: 'barStackTopLabels',

  /** @param {import('chart.js').Chart} chart */
  afterDatasetsDraw(chart) {
    const items =
      chart.options.plugins?.barStackTopLabels?.items ??
      /** @type {BarStackTopLabelItem[]} */ ([])
    if (!items.length) return

    const { ctx, chartArea, data } = chart
    if (!chartArea || !data.datasets?.length) return

    const n = data.labels?.length ?? 0
    if (!n) return

    ctx.save()
    try {
      for (const item of items) {
        const stackId = String(item.stack ?? '').trim()
        if (!stackId) continue
        const values = item.values
        if (!Array.isArray(values) || values.length !== n) continue

        const datasetIndices = data.datasets
          .map((ds, i) => ({ stack: ds.stack ?? 'stack0', i }))
          .filter(({ stack }) => stack === stackId)
          .map(({ i }) => i)
        if (!datasetIndices.length) continue

        ctx.font = '600 11px var(--mono, ui-monospace, monospace)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'

        for (let dataIndex = 0; dataIndex < n; dataIndex += 1) {
          const val = Number(values[dataIndex])
          if (!Number.isFinite(val) || val <= 0) continue

          let topY = Infinity
          let centerX = null

          for (const di of datasetIndices) {
            const meta = chart.getDatasetMeta(di)
            if (meta.hidden) continue
            const el = meta.data[dataIndex]
            if (!el || el.hidden) continue
            if (typeof el.y !== 'number' || !Number.isFinite(el.y)) continue
            if (el.y < topY) {
              topY = el.y
              centerX = el.x
            }
          }

          if (centerX == null || !Number.isFinite(topY)) continue

          const y = Math.max(chartArea.top + 10, topY - 4)
          const color = item.color || 'rgba(200, 228, 210, 0.92)'
          ctx.fillStyle = color
          ctx.fillText(val.toLocaleString('ru-RU'), centerX, y)
        }
      }
    } finally {
      ctx.restore()
    }
  },
}
