<script setup>
/**
 * Строчная заметка о состоянии списка/сводки: «Загрузка…» или «Нет данных».
 * Заменяет повторяющийся across-views паттерн <p class="muted">Загрузка…</p>.
 *
 *   <StateNote v-if="loading && !items.length" loading />
 *   <StateNote v-else-if="!items.length" text="Нет данных за период" />
 *   <StateNote loading text="Загрузка сводки…" />
 *
 * Текст можно задать пропом text или содержимым слота; по умолчанию —
 * «Загрузка…» для loading и «Нет данных» иначе.
 */
defineProps({
  loading: { type: Boolean, default: false },
  text: { type: String, default: '' },
})
</script>

<template>
  <p class="state-note muted" :class="{ 'state-note--loading': loading }">
    <slot>{{ text || (loading ? 'Загрузка…' : 'Нет данных') }}</slot>
  </p>
</template>

<style scoped>
.state-note {
  margin: 0.4rem 0;
  font-size: 0.9rem;
  line-height: 1.5;
}
</style>
