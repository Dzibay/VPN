<script setup>
/**
 * Кнопки режима массового выбора для слота #actions в AppPager.
 */
defineProps({
  /** Режим выбора включён */
  active: { type: Boolean, default: false },
  selectedCount: { type: Number, default: 0 },
  deleting: { type: Boolean, default: false },
  /** «пользователей», «логов», «платежей» */
  entityLabel: { type: String, default: 'записей' },
})

defineEmits(['toggle', 'delete'])
</script>

<template>
  <button
    type="button"
    class="btn-secondary admin-bulk-bar__toggle"
    :class="{ 'admin-bulk-bar__toggle--active': active }"
    :aria-pressed="active"
    @click="$emit('toggle')"
  >
    {{ active ? 'Готово' : 'Выбрать' }}
  </button>
  <Transition name="admin-bulk-bar-delete">
    <button
      v-if="active && selectedCount > 0"
      type="button"
      class="btn-danger"
      :disabled="deleting"
      @click="$emit('delete')"
    >
      {{ deleting ? 'Удаление…' : `Удалить (${selectedCount})` }}
    </button>
  </Transition>
</template>

<style scoped>
.admin-bulk-bar__toggle--active {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  background: color-mix(in srgb, var(--accent) 12%, var(--card-bg));
  color: var(--text-h);
}

.admin-bulk-bar-delete-enter-active,
.admin-bulk-bar-delete-leave-active {
  transition:
    opacity 0.22s ease,
    transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.admin-bulk-bar-delete-enter-from,
.admin-bulk-bar-delete-leave-to {
  opacity: 0;
  transform: translateX(-0.35rem) scale(0.92);
}
</style>
