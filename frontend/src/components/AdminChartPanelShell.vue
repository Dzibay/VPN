<script setup>
/**
 * Общая стеклянная оболочка админских графиков: заголовок, состояния, слот для canvas.
 */
defineProps({
  title: { type: String, default: '' },
  unitLabel: { type: String, default: '' },
  hint: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  hasData: { type: Boolean, default: true },
  /** Без нижнего отступа (в сетке из двух колонок). */
  flush: { type: Boolean, default: false },
})
</script>

<template>
  <div
    class="admin-chart-panel glass"
    :class="{ 'admin-chart-panel--flush': flush }"
  >
    <div v-if="title || unitLabel || $slots.head" class="chart-head">
      <slot name="head">
        <h3 v-if="title" class="chart-title">{{ title }}</h3>
        <span v-if="unitLabel" class="chart-unit">{{ unitLabel }}</span>
      </slot>
    </div>
    <p v-if="hint" class="chart-hint">{{ hint }}</p>

    <p v-if="error" class="banner-err">{{ error }}</p>
    <p v-else-if="loading" class="loading-line">Загрузка…</p>
    <template v-else-if="!hasData">
      <slot name="empty">
        <p class="empty-hint">Нет данных для графика.</p>
      </slot>
    </template>
    <slot v-else />
  </div>
</template>
