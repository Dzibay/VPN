<script setup>
import { RouterLink } from 'vue-router'

defineProps({
  /** Маршрут личного кабинета (по умолчанию как на странице скачивания клиента). */
  to: {
    type: [String, Object],
    default: '/cabinet',
  },
  label: {
    type: String,
    default: 'Личный кабинет',
  },
})
</script>

<template>
  <RouterLink
    class="cabinet-back-link"
    :to="to"
  ><span
    class="cabinet-back-link__arrow"
    aria-hidden="true"
  >←</span> {{ label }}</RouterLink>
</template>

<style scoped>
.cabinet-back-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  width: 100%;
  max-width: 26rem;
  box-sizing: border-box;
  padding: 0;
  margin: 0;
  border: none;
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 0.9rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: color 0.2s ease;
}

.cabinet-back-link:hover {
  color: var(--accent);
}

.cabinet-back-link__arrow {
  font-size: 1em;
  line-height: 1;
}
</style>
