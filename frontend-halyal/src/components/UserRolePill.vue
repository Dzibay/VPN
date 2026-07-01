<script setup>
import { computed } from 'vue'
import { accountRoleLabel, normalizeAccountRole } from '../utils/accountRole.js'

const props = defineProps({
  /** account_role из API: client | manager | admin или пусто */
  role: {
    type: String,
    default: undefined,
  },
})

const slug = computed(() => normalizeAccountRole(props.role))
const label = computed(() => accountRoleLabel(slug.value))
</script>

<template>
  <span class="user-role-pill" :data-role="slug" :title="slug">{{ label }}</span>
</template>

<style scoped>
.user-role-pill {
  display: inline-block;
  padding: 0.12rem 0.45rem;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: none;
  letter-spacing: 0.02em;
  background: var(--surface);
  border: 1px solid var(--card-border);
  color: var(--text-h);
}

.user-role-pill[data-role='admin'] {
  border-color: #c4b5fd;
}

.user-role-pill[data-role='manager'] {
  border-color: #fdba74;
}
</style>
