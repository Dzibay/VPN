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
})
</script>

<template>
  <div
    class="admin-table-wrap"
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
}
</style>
