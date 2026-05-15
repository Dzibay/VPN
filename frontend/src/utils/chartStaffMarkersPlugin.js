/**
 * Вертикальные отметки событий на линейном графике (ось X — категории).
 * Данные: options.plugins.staffChartMarkers.markers = [{ index, title, color }]
 */

/** @typedef {{ index: number; title: string; color: string; kind?: string }} ChartEventMarker */

function utcHourFloorMs(ms) {
  const d = new Date(ms)
  return Date.UTC(
    d.getUTCFullYear(),
    d.getUTCMonth(),
    d.getUTCDate(),
    d.getUTCHours(),
    0,
    0,
    0,
  )
}

function utcDayKeyFromEventIso(evIso) {
  const t = Date.parse(evIso)
  if (Number.isNaN(t)) return null
  const d = new Date(t)
  const y = d.getUTCFullYear()
  const mo = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
}

function utcHourIsoKeyFromEventIso(evIso) {
  const t = Date.parse(evIso)
  if (!Number.isFinite(t)) return null
  const ms = utcHourFloorMs(t)
  return new Date(ms).toISOString()
}

/**
 * X-пиксель центра точки данных по индексу (устойчиво при autoSkip на оси категорий).
 * @param {import('chart.js').Chart} chart
 * @param {number} dataIndex
 * @returns {number | null}
 */
function dataPointCenterX(chart, dataIndex) {
  const meta = chart.getDatasetMeta(0)
  const pt = meta?.data?.[dataIndex]
  const x = pt?.x
  return typeof x === 'number' && Number.isFinite(x) ? x : null
}

function mskCalendarTodayYmd() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' })
}

function utcTodayYmd() {
  const d = new Date()
  const y = d.getUTCFullYear()
  const mo = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
}

/**
 * Вертикальная отметка «сегодня» на линейном графике: UTC-день в режиме по дням;
 * в почасовом — только если выбран сегодняшний календарный день по МСК, тогда текущий час UTC.
 * @param {Array<{ iso: string }>} chartPoints
 * @param {'day'|'hour'} granularity
 * @param {string} hourDayMsk
 * @returns {ChartEventMarker | null}
 */
export function makeTodayLineChartMarker(chartPoints, granularity, hourDayMsk) {
  if (!Array.isArray(chartPoints) || chartPoints.length === 0) return null
  /** @type {ChartEventMarker} */
  const base = { title: '', color: '#34d399' }

  if (granularity === 'day') {
    const key = utcTodayYmd()
    const idx = chartPoints.findIndex(
      (p) => String(p?.iso ?? '').slice(0, 10) === key,
    )
    if (idx < 0) return null
    return { ...base, index: idx, title: 'Сегодня (UTC)', kind: 'today' }
  }

  if (granularity === 'hour') {
    const sel = String(hourDayMsk ?? '').trim().slice(0, 10)
    if (!sel || sel !== mskCalendarTodayYmd()) return null
    const nowKey = utcHourIsoKeyFromEventIso(new Date().toISOString())
    if (!nowKey) return null
    const idx = chartPoints.findIndex((p) => String(p?.iso ?? '') === nowKey)
    if (idx < 0) return null
    return { ...base, index: idx, title: 'Сейчас (UTC)', kind: 'today' }
  }

  return null
}

/**
 * Сопоставляет события индексам точек графика (день UTC или час по Москве — как у данных RPC).
 * event_at в ответе API приходит в московском ISO; сравнение через абсолютный момент (UTC).
 * @param {Array<{ iso: string }>} chartPoints
 * @param {'day'|'hour'} granularity
 * @param {Array<{ event_at: string; title: string; color: string }>} events
 * @returns {ChartEventMarker[]}
 */
export function mapStaffChartEventsToMarkers(chartPoints, granularity, events) {
  if (!Array.isArray(chartPoints) || !chartPoints.length) return []
  if (!Array.isArray(events) || !events.length) return []

  const out = /** @type {ChartEventMarker[]} */ ([])

  for (const ev of events) {
    let idx = -1

    if (granularity === 'hour') {
      const key = utcHourIsoKeyFromEventIso(ev.event_at)
      if (!key) continue
      idx = chartPoints.findIndex((p) => p.iso === key)
    } else {
      const key = utcDayKeyFromEventIso(ev.event_at)
      if (!key) continue
      idx = chartPoints.findIndex((p) => String(p.iso).slice(0, 10) === key)
    }

    if (idx >= 0) {
      const title = String(ev.title ?? '').trim()
      const color = String(ev.color ?? '#888888').trim()
      if (title) out.push({ index: idx, title, color })
    }
  }

  return out
}

export const staffChartMarkersPlugin = {
  id: 'staffChartMarkers',

  /** @param {import('chart.js').Chart} chart */
  afterDatasetsDraw(chart) {
    const markers =
      chart.options.plugins?.staffChartMarkers?.markers ?? /** @type {ChartEventMarker[]} */ (
        []
      )
    if (!markers.length) return

    const { ctx, chartArea, scales } = chart
    const xScale = scales.x
    if (!xScale || !chartArea) return

    const n = chart.data.labels?.length ?? 0
    if (!n) return

    /** @type {Map<number, ChartEventMarker[]>} */
    const groups = new Map()
    for (const m of markers) {
      if (
        typeof m.index !== 'number' ||
        m.index < 0 ||
        m.index >= n ||
        !m.color
      ) {
        continue
      }
      if (!groups.has(m.index)) groups.set(m.index, [])
      groups.get(m.index).push(m)
    }

    ctx.save()
    try {
      for (const [index, list] of groups) {
        let baseX = dataPointCenterX(chart, index)
        if (baseX == null) {
          baseX = xScale.getPixelForTick(index)
        }

        let step = 6
        const nextX = dataPointCenterX(chart, index + 1)
        const prevX = dataPointCenterX(chart, index - 1)
        if (nextX != null) {
          step = Math.abs(nextX - baseX)
        } else if (prevX != null) {
          step = Math.abs(baseX - prevX)
        }
        step = Math.min(10, Math.max(4, step / (list.length + 1)))

        list.forEach((m, k) => {
          const x = baseX + (k - (list.length - 1) / 2) * step
          ctx.beginPath()
          ctx.strokeStyle = m.color
          ctx.globalAlpha = 0.88
          ctx.lineWidth = 2
          ctx.setLineDash([4, 3])
          ctx.moveTo(x, chartArea.top)
          ctx.lineTo(x, chartArea.bottom)
          ctx.stroke()
        })
      }
    } finally {
      ctx.setLineDash([])
      ctx.globalAlpha = 1
      ctx.restore()
    }
  },
}
