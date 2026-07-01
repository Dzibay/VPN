<script setup>
defineProps({
  label: { type: String, required: true },
  columnKey: { type: String, required: true },
  /** Текущий отсортированный столбец; null — сортировка не применялась */
  sortKey: {
    type: [String, null],
    default: null,
  },
  /** @type {'asc' | 'desc'} */
  sortDir: { type: String, default: 'asc' },
  align: {
    type: String,
    default: 'left',
    validator: (v) => v === 'left' || v === 'right',
  },
  sortable: { type: Boolean, default: true },
})

defineEmits(['sort'])
</script>

<template>
  <th
    class="admin-th"
    :class="{ 'admin-th--num': align === 'right' }"
    :aria-sort="
      sortable && sortKey != null && sortKey === columnKey
        ? sortDir === 'asc'
          ? 'ascending'
          : 'descending'
        : undefined
    "
  >
    <button
      v-if="sortable"
      type="button"
      class="admin-sort-btn"
      :title="`Сортировать по столбцу «${label}»`"
      @click="$emit('sort', columnKey)"
    >
      <span class="admin-sort-btn__label">{{ label }}</span>
      <span class="admin-sort-btn__icon" aria-hidden="true">
        <template v-if="sortKey != null && sortKey === columnKey">{{
          sortDir === 'asc' ? '↑' : '↓'
        }}</template>
        <template v-else>⇅</template>
      </span>
    </button>
    <span v-else class="admin-th__static">{{ label }}</span>
  </th>
</template>
