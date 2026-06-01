<script setup>
/**
 * Карточка-показатель для дашбордов админки (число + подписи).
 * Стили — в styles/admin-ui.css (.stat-widget*), чтобы их можно было
 * использовать и внутри слота (значение/мета/дельта/split).
 *
 *   <StatWidget title="Пользователи" aria-label="Число пользователей">
 *     <p class="stat-widget-value">{{ total }}</p>
 *     <p class="stat-widget-meta">Сегодня: {{ today }}</p>
 *   </StatWidget>
 */
defineProps({
  title: { type: String, default: '' },
})
</script>

<template>
  <div class="stat-widget">
    <h3 v-if="title || $slots.title" class="stat-widget-title">
      <slot name="title">{{ title }}</slot>
    </h3>
    <slot />
  </div>
</template>
