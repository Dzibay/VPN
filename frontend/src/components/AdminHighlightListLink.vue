<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  ADMIN_HIGHLIGHT_LIST_KEYS,
  ADMIN_HIGHLIGHT_LIST_PRESETS,
  adminUserAnalyticsPath,
} from './adminHighlightListLinkPresets.js'

const props = defineProps({
  /** users — аналитика пользователя; referrals — список с подсветкой строки */
  list: {
    type: String,
    required: true,
    validator: (v) => ADMIN_HIGHLIGHT_LIST_KEYS.includes(v),
  },
  highlight: {
    type: [String, Number],
    required: true,
  },
  title: { type: String, default: '' },
  ariaLabel: { type: String, default: '' },
  /** Не всплывать клик до строки таблицы (выбор строки) */
  stopPropagation: { type: Boolean, default: false },
  panel: { type: Boolean, default: false },
})

const preset = computed(() => ADMIN_HIGHLIGHT_LIST_PRESETS[props.list])
const linkTitle = computed(() => props.title || preset.value.title)
const linkAriaLabel = computed(() => props.ariaLabel || preset.value.ariaLabel)
const linkTo = computed(() => {
  if (preset.value.routeKind === 'userAnalytics') {
    return adminUserAnalyticsPath(props.highlight)
  }
  return {
    path: preset.value.path,
    query: { highlight: String(props.highlight) },
  }
})

function onClick(event) {
  if (props.stopPropagation) event.stopPropagation()
}
</script>

<template>
  <RouterLink
    class="admin-highlight-list-link"
    :class="{ 'admin-highlight-list-link--panel': panel }"
    :to="linkTo"
    :title="linkTitle"
    :aria-label="linkAriaLabel"
    @click="onClick"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" x2="21" y1="14" y2="3" />
    </svg>
  </RouterLink>
</template>

<style scoped>
.admin-highlight-list-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 0.1rem;
  padding: 0.12rem;
  border-radius: 6px;
  color: var(--accent);
  line-height: 0;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}
.admin-highlight-list-link:hover {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--text-h);
}
.admin-highlight-list-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.admin-highlight-list-link--panel {
  margin-left: 0;
}
</style>
