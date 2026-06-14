import { computed, reactive, toValue, watch } from 'vue'

/**
 * Режим массового выбора строк админ-таблицы (только admin).
 * Возвращает reactive-объект — свойства доступны в шаблоне без .value.
 *
 * @param {object} opts
 * @param {import('vue').MaybeRefOrGetter<number[]>} opts.rowIdsOnPage — id строк текущей страницы
 * @param {import('vue').MaybeRefOrGetter<boolean>} [opts.enabled=true] — показывать ли bulk UI (роль admin)
 */
export function useAdminTableBulkSelect({ rowIdsOnPage, enabled = true } = {}) {
  const enabledFlag = computed(() => Boolean(toValue(enabled)))

  const bulk = reactive({
    selectionMode: false,
    selectedIds: /** @type {number[]} */ ([]),
    deleting: false,

    get canBulkSelect() {
      return enabledFlag.value
    },
    get selectedCount() {
      return bulk.selectedIds.length
    },
    get allSelectedOnPage() {
      const ids = toValue(rowIdsOnPage) ?? []
      if (!ids.length) return false
      return ids.every((id) => bulk.selectedIds.includes(Number(id)))
    },

    exitSelectionMode() {
      bulk.selectionMode = false
      bulk.selectedIds = []
    },
    enterSelectionMode() {
      if (!bulk.canBulkSelect) return
      bulk.selectionMode = true
    },
    toggleSelectionMode() {
      if (bulk.selectionMode) bulk.exitSelectionMode()
      else bulk.enterSelectionMode()
    },
    toggleSelectAllOnPage() {
      const ids = (toValue(rowIdsOnPage) ?? []).map((id) => Number(id))
      if (!ids.length) return
      if (bulk.allSelectedOnPage) {
        const remove = new Set(ids)
        bulk.selectedIds = bulk.selectedIds.filter((id) => !remove.has(id))
        return
      }
      bulk.selectedIds = Array.from(new Set([...bulk.selectedIds, ...ids]))
    },
    toggleRow(id) {
      const n = Number(id)
      if (!Number.isFinite(n)) return
      const idx = bulk.selectedIds.indexOf(n)
      if (idx >= 0) bulk.selectedIds.splice(idx, 1)
      else bulk.selectedIds.push(n)
    },
    isRowSelected(id) {
      return bulk.selectedIds.includes(Number(id))
    },
  })

  watch(
    () => toValue(rowIdsOnPage) ?? [],
    (ids) => {
      const keep = new Set(ids.map((id) => Number(id)))
      bulk.selectedIds = bulk.selectedIds.filter((id) => keep.has(id))
    },
  )

  return bulk
}
