<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import AdminNavTabs from './AdminNavTabs.vue'
import AdminPageHeader from './AdminPageHeader.vue'
import AdminPageShell from './AdminPageShell.vue'
import { getSessionRole } from '../auth/session.js'
import { adminNavAriaLabelForRole } from '../admin/adminNavConfig.js'

const props = defineProps({
  title: { type: String, required: true },
  shellClass: { type: String, default: '' },
  /** Пусто — из роли (админка / менеджер). */
  tabsAriaLabel: { type: String, default: '' },
  /**
   * Ссылка «назад». Не задано — для admin: /admin/summary, для manager: /cabinet.
   * Для страницы «Управление данными» задайте back-to="/".
   */
  backTo: { type: [String, Object], default: undefined },
  backLabel: { type: String, default: undefined },
})

const aria = computed(() => {
  const raw = (props.tabsAriaLabel || '').trim()
  if (raw) return raw
  return adminNavAriaLabelForRole(getSessionRole())
})

const resolvedBackTo = computed(() => {
  if (props.backTo !== undefined && props.backTo !== null && props.backTo !== '')
    return props.backTo
  return getSessionRole() === 'admin' ? '/dashboard' : '/cabinet'
})

const resolvedBackLabel = computed(() => {
  if (props.backLabel != null && props.backLabel !== '') return props.backLabel
  return getSessionRole() === 'admin'
    ? '← Управление данными'
    : '← Личный кабинет'
})
</script>

<template>
  <AdminPageShell :class="shellClass">
    <AdminPageHeader :title="title" :tabs-aria-label="aria">
      <template #back>
        <slot name="back">
          <RouterLink class="back" :to="resolvedBackTo">
            {{ resolvedBackLabel }}
          </RouterLink>
        </slot>
      </template>
      <template #tabs>
        <AdminNavTabs />
      </template>
      <slot name="headerExtras" />
    </AdminPageHeader>
    <slot />
  </AdminPageShell>
</template>
