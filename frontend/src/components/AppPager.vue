<script setup>
/**
 * Панель пагинации: подпись диапазона + кнопки «Назад/Вперёд».
 * Обычно используется вместе с useOffsetPagination.
 *
 *   <AppPager :range-label="rangeLabel" :can-prev="canPrev" :can-next="canNext"
 *             :loading="loading" @prev="prev" @next="next">
 *     <template #actions> … доп. кнопки (напр. «Удалить выбранные») … </template>
 *   </AppPager>
 */
defineProps({
  rangeLabel: { type: String, default: '' },
  canPrev: { type: Boolean, default: false },
  canNext: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  prevLabel: { type: String, default: 'Назад' },
  nextLabel: { type: String, default: 'Вперёд' },
})

defineEmits(['prev', 'next'])
</script>

<template>
  <div class="app-pager">
    <span class="muted app-pager__range">{{ rangeLabel }}</span>
    <div class="app-pager__btns">
      <slot name="actions" />
      <button type="button" class="btn-secondary" :disabled="loading || !canPrev" @click="$emit('prev')">
        {{ prevLabel }}
      </button>
      <button type="button" class="btn-secondary" :disabled="loading || !canNext" @click="$emit('next')">
        {{ nextLabel }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.app-pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.6rem;
}

.app-pager__range {
  font-size: 0.85rem;
}

.app-pager__btns {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
</style>
