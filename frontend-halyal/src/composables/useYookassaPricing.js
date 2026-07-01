import { computed, ref } from 'vue'
import { fetchJson } from '../api/client.js'

/** @typedef {{ months: number, price: number, name: string }} YookassaTariff */

/** @typedef {{
 *   id: number;
 *   months: number;
 *   name: string;
 *   tagline: string;
 *   monthlyHighlight: string;
 *   totalPrice: string;
 *   periodShort: string;
 *   compareAtTotal: string | null;
 *   savingsLabel: string | null;
 *   discountPercent: number | null;
 *   paymentHint: string | null;
 *   totalPeriodLabel: string | null;
 *   displayName: string;
 *   periodBadge: string;
 *   ribbonLabel: string;
 *   popular: boolean;
 *   ctaGuest: string;
 * }} LandingPlanRow */

/** @param {number} amount */
export function formatRub(amount) {
  const n = Math.round(Number(amount))
  if (!Number.isFinite(n)) return '—'
  return `${n.toLocaleString('ru-RU')} ₽`
}

/** @param {number} months */
export function formatPeriod(months) {
  if (months === 1) return '1 месяц'
  if (months === 3) return '3 месяца'
  if (months === 6) return '6 месяцев'
  if (months === 12) return '1 год'
  return `${months} мес.`
}

/** @param {YookassaTariff} tariff */
export function monthlyPriceRub(tariff) {
  return Math.round(tariff.price / tariff.months)
}

/** @param {YookassaTariff} tariff @param {number | null} baseMonthly */
export function savingsRub(tariff, baseMonthly) {
  if (!baseMonthly || tariff.months <= 1) return null
  const full = baseMonthly * tariff.months
  const save = full - tariff.price
  return save > 0 ? save : null
}

/** @param {number} save */
function savingsLabel(save) {
  return `Экономия ${formatRub(save)} по сравнению с ежемесячной оплатой`
}

/** @param {number} months @param {number} price */
function totalPeriodLabel(months, price) {
  if (months === 1) return null
  if (months === 6) return `${formatRub(price)} за 6 месяцев`
  if (months === 12) return `${formatRub(price)} за 12 месяцев`
  return `${formatRub(price)} за ${formatPeriod(months).toLowerCase()}`
}

/** @param {number | null} save @param {number | null} base @param {number} months */
function discountPercent(save, base, months) {
  if (!save || !base || months <= 1) return null
  const full = base * months
  return Math.round((save / full) * 100)
}

/** @param {YookassaTariff[]} tariffs */
export function baseMonthlyFromTariffs(tariffs) {
  const one = tariffs.find((t) => t.months === 1)
  return one?.price ?? tariffs[0]?.price ?? null
}

/**
 * @param {YookassaTariff[]} tariffs
 * @param {number[]} monthsList
 * @param {Record<number, {
 *   displayName: string;
 *   periodBadge: string;
 *   tagline: string;
 *   popular?: boolean;
 *   ctaGuest: string;
 *   periodShort?: string;
 *   ribbonLabel?: string;
 * }>} metaByMonths
 * @returns {LandingPlanRow[]}
 */
export function buildLandingPlans(tariffs, monthsList, metaByMonths) {
  const base = baseMonthlyFromTariffs(tariffs)
  const byMonths = new Map(tariffs.map((t) => [t.months, t]))

  return monthsList
    .map((months) => {
      const tariff = byMonths.get(months)
      const meta = metaByMonths[months]
      if (!tariff || !meta) return null

      const monthly = monthlyPriceRub(tariff)
      const save = savingsRub(tariff, base)

      return {
        id: months,
        months,
        name: formatPeriod(months),
        displayName: meta.displayName ?? formatPeriod(months),
        periodBadge: meta.periodBadge ?? formatPeriod(months),
        tagline: meta.tagline,
        monthlyHighlight: formatRub(monthly),
        totalPrice: formatRub(tariff.price),
        periodShort:
          meta.periodShort ??
          (months === 1 ? 'за 30 дней' : 'единый платёж'),
        compareAtTotal:
          save != null && base != null ? formatRub(base * months) : null,
        savingsLabel: save != null ? savingsLabel(save) : null,
        discountPercent: discountPercent(save, base, months),
        paymentHint:
          months === 1
            ? `${formatRub(tariff.price)} при оплате каждый месяц`
            : null,
        totalPeriodLabel: totalPeriodLabel(months, tariff.price),
        popular: Boolean(meta.popular),
        ribbonLabel: meta.ribbonLabel ?? 'Выгоднее всего',
        ctaGuest: meta.ctaGuest,
      }
    })
    .filter(Boolean)
}

/**
 * Тарифы с API (источник — project_tariffs текущего проекта).
 * @param {string} [fetchPath='/api/payments/tariffs']
 */
export function useYookassaPricing(fetchPath = '/api/payments/tariffs') {
  const loading = ref(true)
  const error = ref(null)
  /** @type {import('vue').Ref<YookassaTariff[]>} */
  const tariffs = ref([])

  async function load() {
    loading.value = true
    error.value = null
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 20_000)
    try {
      const data = await fetchJson(fetchPath, { signal: controller.signal })
      const list = [...(data?.tariffs ?? [])]
      tariffs.value = list.sort((a, b) => a.months - b.months)
    } catch (e) {
      if (e?.name === 'AbortError') {
        error.value = 'Сервер не ответил вовремя. Попробуйте через минуту.'
      } else {
        error.value = e?.message || String(e)
      }
      tariffs.value = []
    } finally {
      clearTimeout(timeoutId)
      loading.value = false
    }
  }

  const baseMonthlyPrice = computed(() => baseMonthlyFromTariffs(tariffs.value))

  return {
    loading,
    error,
    tariffs,
    baseMonthlyPrice,
    load,
    formatRub,
    formatPeriod,
    monthlyPriceRub,
    savingsRub,
    buildLandingPlans,
  }
}
