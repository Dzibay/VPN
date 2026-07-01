/**
 * Даты и время в UI.
 *
 * **Где считается МСК:** PostgreSQL RPC и Python (`Europe/Moscow`) для календарных
 * бакетов (`stats_date`, `hour_day`); моменты `datetime` в JSON API — ISO с offset Москвы
 * (`app.core.moscow_api_time`). В БД `timestamptz` хранится как UTC.
 *
 * **Фронт:** только подписи. `stats_date` (YYYY-MM-DD) — уже день по Москве из API;
 * не переводите его через `Date.UTC`. Для метрик по `traffic_date` (UTC-снимки) — `utcTodayIso`.
 */

export const MSK_TZ = 'Europe/Moscow'

/** Текущий календарный день Europe/Moscow (YYYY-MM-DD). */
export function mskTodayIso() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: MSK_TZ })
}

/** Текущий календарный месяц Europe/Moscow (YYYY-MM). */
export function mskMonthInputDefault() {
  return mskTodayIso().slice(0, 7)
}

/** Ключ YYYY-MM-DD для момента (API отдаёт datetime уже в МСК). */
export function mskDayKeyFromIso(iso) {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  return new Date(t).toLocaleDateString('sv-SE', { timeZone: MSK_TZ })
}

/** Подпись календарного дня (`subscription_until`, `stats_date`) — длинный месяц, МСК. */
export function formatMskCalendarDayLong(isoDay) {
  if (isoDay == null || isoDay === '') return '—'
  try {
    const s = String(isoDay).slice(0, 10)
    return new Date(`${s}T12:00:00+03:00`).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: MSK_TZ,
    })
  } catch {
    return String(isoDay)
  }
}

/** Подпись календарного дня из API (`stats_date` = день по Москве). */
export function formatMskCalendarDayShort(iso) {
  if (iso == null || iso === '') return '—'
  try {
    const s = String(iso).slice(0, 10)
    return new Date(`${s}T12:00:00+03:00`).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      timeZone: MSK_TZ,
    })
  } catch {
    return String(iso)
  }
}

/**
 * Datetime из API (ISO с offset Москвы) — ru-RU, всегда Europe/Moscow.
 * Для staff-таблиц, где нельзя полагаться на TZ браузера.
 */
export function formatMskApiDateTime(isoOrTs, opts = {}) {
  if (isoOrTs == null || isoOrTs === '') return '—'
  try {
    return new Date(isoOrTs).toLocaleString('ru-RU', {
      timeZone: MSK_TZ,
      dateStyle: 'short',
      timeStyle: 'short',
      ...opts,
    })
  } catch {
    return String(isoOrTs)
  }
}

/** Календарная дата из API (`date` или `datetime`) — ru-RU, Europe/Moscow. */
export function formatLocaleDateRu(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU', { timeZone: MSK_TZ })
  } catch {
    return String(d)
  }
}

/** Дата и время из API (уже с offset Москвы). */
export function formatMskDateTimeShort(isoOrTs) {
  if (isoOrTs == null || isoOrTs === '') return '—'
  try {
    return (
      new Date(isoOrTs).toLocaleString('ru-RU', {
        timeZone: MSK_TZ,
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }) + ' МСК'
    )
  } catch {
    return String(isoOrTs)
  }
}

/** Подпись часа для оси X (одни сутки). */
export function formatMskHourAxis(isoOrTs) {
  if (isoOrTs == null || isoOrTs === '') return '—'
  try {
    return (
      new Date(isoOrTs).toLocaleTimeString('ru-RU', {
        timeZone: MSK_TZ,
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }) + ' МСК'
    )
  } catch {
    return String(isoOrTs)
  }
}

/** Календарных дней от сегодня (МСК) до ``isoDay`` (0 — последний день доступа). */
export function mskCalendarDaysUntil(isoDay) {
  if (isoDay == null || isoDay === '') return null
  const end = String(isoDay).slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(end)) return null
  const today = mskTodayIso()
  const [y1, m1, d1] = today.split('-').map(Number)
  const [y2, m2, d2] = end.split('-').map(Number)
  const t1 = Date.UTC(y1, m1 - 1, d1)
  const t2 = Date.UTC(y2, m2 - 1, d2)
  return Math.round((t2 - t1) / 86_400_000)
}

function ruDayWord(n) {
  const abs = Math.abs(n)
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod10 === 1 && mod100 !== 11) return 'день'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'дня'
  return 'дней'
}

/** Подпись «осталось N дней» для ``subscription_until`` (календарь Москвы). */
export function formatMskSubscriptionDaysRemaining(isoDay) {
  const days = mskCalendarDaysUntil(isoDay)
  if (days == null) return null
  if (days < 0) {
    const ago = Math.abs(days)
    return `истекла ${ago} ${ruDayWord(ago)} назад`
  }
  if (days === 0) return 'истекает сегодня'
  const word = ruDayWord(days)
  if (days === 1) return `остался 1 ${word}`
  return `осталось ${days} ${word}`
}

/** Календарный день YYYY-MM-DD на ``days`` суток раньше (``days`` ≥ 1). */
export function subtractCalendarDaysIso(isoDay, days = 1) {
  const n = Math.max(1, Math.trunc(Number(days)) || 1)
  const s = String(isoDay).slice(0, 10)
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return s
  const t = Date.UTC(y, m - 1, d - n)
  const x = new Date(t)
  const yy = x.getUTCFullYear()
  const mo = String(x.getUTCMonth() + 1).padStart(2, '0')
  const day = String(x.getUTCDate()).padStart(2, '0')
  return `${yy}-${mo}-${day}`
}

/** Следующий календарный день YYYY-MM-DD (плотный ряд). */
export function addCalendarDayIso(isoDay) {
  const s = String(isoDay).slice(0, 10)
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return s
  const t = Date.UTC(y, m - 1, d + 1)
  const x = new Date(t)
  const yy = x.getUTCFullYear()
  const mo = String(x.getUTCMonth() + 1).padStart(2, '0')
  const day = String(x.getUTCDate()).padStart(2, '0')
  return `${yy}-${mo}-${day}`
}

/** Полночь часа UTC (мс) — для почасового ряда (`period_start_utc` из API). */
export function utcHourFloorMs(ms) {
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

/** ISO-ключ начала часа UTC для сопоставления с `period_start_utc`. */
export function utcHourIsoKeyFromInstant(iso) {
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return null
  return new Date(utcHourFloorMs(t)).toISOString()
}

/** Текущий календарный день UTC (метрики по `traffic_date`). */
export function utcTodayIso() {
  const d = new Date()
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Подпись UTC-календарного дня (трафик). */
export function formatUtcCalendarDayShort(iso) {
  if (iso == null || iso === '') return '—'
  try {
    const s = String(iso).slice(0, 10)
    return new Date(`${s}T12:00:00Z`).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return String(iso)
  }
}
