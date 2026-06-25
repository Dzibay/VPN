import { computed, ref, watch } from 'vue'
import { mskTodayIso } from '../utils/mskDate.js'
import { mskMonthStart, mskParts, periodPresetLabel, resolveMskPeriodRange } from '../utils/mskPeriodRange.js'

/**
 * @param {Array<{ key: string, label: string }>} presets
 * @param {string} [defaultKey]
 */
export function useMskPeriodRange(presets, defaultKey = 'month') {
  const periodPreset = ref(defaultKey)
  const customFrom = ref('')
  const customTo = ref('')

  const computedRange = computed(() =>
    resolveMskPeriodRange(periodPreset.value, {
      customFrom: customFrom.value,
      customTo: customTo.value,
    }),
  )

  const periodLabel = computed(() => periodPresetLabel(presets, periodPreset.value))

  const hasCustomRange = computed(() => presets.some((p) => p.key === 'custom'))

  watch(periodPreset, (p) => {
    if (p !== 'custom') return
    const { y } = mskParts()
    if (!customFrom.value) customFrom.value = mskMonthStart(y, 1)
    if (!customTo.value) customTo.value = mskTodayIso()
  })

  return {
    periodPreset,
    customFrom,
    customTo,
    computedRange,
    periodLabel,
    hasCustomRange,
  }
}
