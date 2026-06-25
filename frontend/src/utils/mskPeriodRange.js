import { mskTodayIso, subtractCalendarDaysIso } from './mskDate.js'

const pad2 = (n) => String(n).padStart(2, '0')

export const ALL_TIME_FROM = '2020-01-01'

/** Пресеты страницы «Сводка». */
export const SUMMARY_PERIOD_PRESETS = [
  { key: 'day', label: 'День' },
  { key: 'week', label: 'Неделя' },
  { key: 'month', label: 'Месяц' },
  { key: 'quarter', label: 'Квартал' },
  { key: 'half_year', label: 'Полгода' },
  { key: 'year', label: 'Год' },
  { key: 'all', label: 'Всё время' },
]

/** Пресеты вкладки «Обзор» в финансах. */
export const FINANCE_PERIOD_PRESETS = [
  { key: 'month', label: 'Этот месяц' },
  { key: 'prev_month', label: 'Прошлый месяц' },
  { key: 'quarter', label: 'Квартал' },
  { key: 'year', label: 'Этот год' },
  { key: 'all', label: 'Всё время' },
  { key: 'custom', label: 'Период' },
]

export function mskParts() {
  const [y, m, d] = mskTodayIso().split('-').map(Number)
  return { y, m, d }
}

export function mskMonthStart(y, m) {
  return `${y}-${pad2(m)}-01`
}

export function mskShiftMonth(y, m, delta) {
  let ny = y
  let nm = m + delta
  while (nm <= 0) {
    nm += 12
    ny -= 1
  }
  while (nm > 12) {
    nm -= 12
    ny += 1
  }
  return { y: ny, m: nm }
}

export function mskLastDayOfPrevMonth(y, m) {
  const dt = new Date(Date.UTC(y, m - 1, 0))
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`
}

/**
 * Календарный диапазон Europe/Moscow для пресета.
 * @param {string} preset
 * @param {{ customFrom?: string, customTo?: string }} [opts]
 */
export function resolveMskPeriodRange(preset, opts = {}) {
  const today = mskTodayIso()
  const { y, m } = mskParts()

  switch (preset) {
    case 'day':
      return { from: today, to: today }
    case 'week':
      return { from: subtractCalendarDaysIso(today, 6), to: today }
    case 'month':
      return { from: mskMonthStart(y, m), to: today }
    case 'prev_month': {
      const py = m === 1 ? y - 1 : y
      const pm = m === 1 ? 12 : m - 1
      return { from: mskMonthStart(py, pm), to: mskLastDayOfPrevMonth(y, m) }
    }
    case 'quarter': {
      const qStart = Math.floor((m - 1) / 3) * 3 + 1
      return { from: mskMonthStart(y, qStart), to: today }
    }
    case 'half_year': {
      const { y: hy, m: hm } = mskShiftMonth(y, m, -6)
      return { from: mskMonthStart(hy, hm), to: today }
    }
    case 'all':
      return { from: ALL_TIME_FROM, to: today }
    case 'custom':
      return {
        from: opts.customFrom || mskMonthStart(y, 1),
        to: opts.customTo || today,
      }
    case 'year':
    default:
      return { from: mskMonthStart(y, 1), to: today }
  }
}

export function periodPresetLabel(presets, key) {
  return presets.find((p) => p.key === key)?.label ?? ''
}
