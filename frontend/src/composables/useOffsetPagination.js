import { computed, ref, toValue } from 'vue'

/**
 * Offset/limit-пагинация для серверных списков админки.
 *
 * Раньше offset/limit/canPrev/canNext/rangeLabel и кнопки «Назад/Вперёд»
 * копировались в 6 view. Теперь:
 *
 *   const { offset, limit, canPrev, canNext, rangeLabel, prev, next, reset } =
 *     useOffsetPagination({ total: () => expTotal.value, count: () => expenses.value.length, onChange: loadExpenses })
 *
 * @param {object} opts
 * @param {number} [opts.limit=100] — размер страницы.
 * @param {import('vue').MaybeRefOrGetter<number>} opts.total — всего записей на сервере.
 * @param {import('vue').MaybeRefOrGetter<number>} opts.count — записей на текущей странице.
 * @param {() => unknown} [opts.onChange] — вызывается после смены offset (обычно загрузка страницы).
 */
export function useOffsetPagination({ limit = 100, total, count, onChange } = {}) {
  const offset = ref(0)
  const limitRef = ref(limit)

  const totalValue = () => Number(toValue(total)) || 0
  const countValue = () => Number(toValue(count)) || 0

  const canPrev = computed(() => offset.value > 0)
  const canNext = computed(() => offset.value + countValue() < totalValue())

  const rangeLabel = computed(() => {
    const t = totalValue()
    if (t === 0) return '0 записей'
    const from = offset.value + 1
    const to = offset.value + countValue()
    return `${from}–${to} из ${t}`
  })

  function prev() {
    if (!canPrev.value) return
    offset.value = Math.max(0, offset.value - limitRef.value)
    onChange?.()
  }

  function next() {
    if (!canNext.value) return
    offset.value += limitRef.value
    onChange?.()
  }

  /** Сброс на первую страницу (после создания записи, смены фильтра и т.п.). */
  function reset() {
    offset.value = 0
  }

  return { offset, limit: limitRef, canPrev, canNext, rangeLabel, prev, next, reset }
}
