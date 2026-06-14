<script setup>
/**
 * Обёртка для горизонтального скролла таблиц в админке (карточка с рамкой и тенью).
 * Слот — содержимое, обычно <table class="table"> или class="data-table">.
 */
defineProps({
  /** Если задан — role="region" и подпись для скринридеров */
  ariaLabel: {
    type: String,
    default: undefined,
  },
  /** Режим массового выбора — подсветка обёртки и анимация колонки чекбоксов */
  bulkSelectActive: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <div
    class="admin-table-wrap"
    :class="{ 'admin-table-wrap--bulk-select': bulkSelectActive }"
    :role="ariaLabel ? 'region' : undefined"
    :aria-label="ariaLabel"
  >
    <slot />
  </div>
</template>

<style scoped>
.admin-table-wrap {
  overflow-x: auto;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
  transition:
    box-shadow 0.38s cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 0.32s ease;
}

.admin-table-wrap--bulk-select {
  border-color: color-mix(in srgb, var(--accent) 42%, var(--card-border));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent),
    0 8px 28px color-mix(in srgb, var(--accent) 12%, transparent),
    var(--shadow-sm);
}
</style>
