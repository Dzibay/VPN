<script setup>
import { computed, useSlots } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  /** Текст <h1> */
  title: { type: String, required: true },
  /** Куда ведёт ссылка «назад», если не задан слот #back */
  backTo: { type: [String, Object], default: '/' },
  /** Подпись ссылки «назад» по умолчанию */
  backLabel: { type: String, default: '← На главную' },
  /** aria-label у <nav class="admin-tabs">, когда передан слот #tabs */
  tabsAriaLabel: { type: String, default: 'Разделы админки' },
})

const slots = useSlots()
const hasTabs = computed(() => Boolean(slots.tabs))
</script>

<template>
  <header class="head">
    <slot name="back">
      <RouterLink class="back" :to="backTo">{{ backLabel }}</RouterLink>
    </slot>
    <h1 class="page-title">{{ title }}</h1>
    <nav v-if="hasTabs" class="admin-tabs" :aria-label="tabsAriaLabel">
      <slot name="tabs" />
    </nav>
    <slot />
  </header>
</template>

<style scoped>
.head {
  margin-bottom: 1rem;
}

.head :deep(.back) {
  display: inline-block;
  margin-bottom: 0.5rem;
  color: var(--muted);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.2s ease;
}

.head :deep(.back:hover) {
  color: var(--accent);
}

.page-title {
  font-size: 1.65rem;
  margin: 0 0 0.65rem;
  letter-spacing: -0.02em;
  color: var(--text-h);
}

.admin-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}

/* Табы внутри nav оформляются классами на RouterLink — как на странице «Данные» */
:deep(.tab) {
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 600;
  text-decoration: none;
  color: var(--muted);
  border: 1px solid var(--card-border);
  background: var(--surface);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

:deep(.tab:hover) {
  color: var(--accent);
  border-color: var(--accent-border);
}

:deep(.tab-active) {
  color: var(--on-accent);
  background: var(--accent);
  border-color: var(--accent);
}

:deep(.tab-active:hover) {
  color: var(--on-accent);
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}
</style>
