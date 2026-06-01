<script setup>
/**
 * Кнопка «Обновить» со встроенной подписью состояния загрузки.
 * Заменяет повторяющийся across-views паттерн
 *   <button class="btn-secondary" :disabled="loading" @click="load">
 *     {{ loading ? 'Обновление…' : 'Обновить' }}
 *   </button>
 *
 *   <AppRefreshButton :busy="loading" @click="load" />
 *   <AppRefreshButton :busy="loading || extraLoading" label="Обновить отчёт" @click="reload" />
 */
defineProps({
  busy: { type: Boolean, default: false },
  label: { type: String, default: 'Обновить' },
  busyLabel: { type: String, default: 'Обновление…' },
  variant: { type: String, default: 'secondary' },
})

defineEmits(['click'])
</script>

<template>
  <button
    type="button"
    :class="variant === 'primary' ? 'btn-primary' : 'btn-secondary'"
    :disabled="busy"
    @click="$emit('click')"
  >
    {{ busy ? busyLabel : label }}
  </button>
</template>
