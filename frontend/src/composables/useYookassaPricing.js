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
 *   popular: boolean;
 *   ctaGuest: string;
 * }} LandingPlanRow */

const MONTHS_DATIVE = {
  3: 'трём',
  6: 'шести',
  12: 'двенадцати',
}

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

/** @param {number} months @param {number} save @param {number} baseMonthly */
function savingsLabel(months, save, baseMonthly) {
  const dative = MONTHS_DATIVE[months] ?? String(months)
  return `Экономия ${formatRub(save)} к ${dative} месяцам по ${formatRub(baseMonthly)}`
}

/** @param {YookassaTariff[]} tariffs */
export function baseMonthlyFromTariffs(tariffs) {
  const one = tariffs.find((t) => t.months === 1)
  return one?.price ?? tariffs[0]?.price ?? null
}

/**
 * @param {YookassaTariff[]} tariffs
 * @param {number[]} monthsList
 * @param {Record<number, { tagline: string, popular?: boolean, ctaGuest: string, periodShort?: string }>} metaByMonths
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
        tagline: meta.tagline,
        monthlyHighlight: formatRub(monthly),
        totalPrice: formatRub(tariff.price),
        periodShort:
          meta.periodShort ??
          (months === 1 ? 'за 30 дней' : 'единый платёж'),
        compareAtTotal:
          save != null && base != null ? formatRub(base * months) : null,
        savingsLabel:
          save != null && base != null
            ? savingsLabel(months, save, base)
            : null,
        popular: Boolean(meta.popular),
        ctaGuest: meta.ctaGuest,
      }
    })
    .filter(Boolean)
}

/**
 * Тарифы ЮKassa с публичного API (источник — backend/app/data/yookassa_tariffs.json).
 * @param {string} [fetchPath='/api/public/yookassa-tariffs']
 */
export function useYookassaPricing(fetchPath = '/api/public/yookassa-tariffs') {
  const loading = ref(true)
  const error = ref(null)
  /** @type {import('vue').Ref<YookassaTariff[]>} */
  const tariffs = ref([])

  async function load() {
    loading.value = true
    error.value = null
    try {
      const data = await fetchJson(fetchPath)
      const list = [...(data?.tariffs ?? [])]
      tariffs.value = list.sort((a, b) => a.months - b.months)
    } catch (e) {
      error.value = e?.message || String(e)
      tariffs.value = []
    } finally {
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
