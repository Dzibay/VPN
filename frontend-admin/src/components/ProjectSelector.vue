<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'
import {
  getCurrentProject,
  getStaffProfile,
  setCurrentProject,
  updateStaffProfile,
} from '../auth/staffSession.js'

const router = useRouter()
const projects = ref([])
const current = ref(getCurrentProject() || '')
const loading = ref(false)
const error = ref(null)

const profile = computed(() => getStaffProfile())
const isSuperAdmin = computed(() => profile.value?.role === 'super_admin')
const allowedIds = computed(() => {
  const ids = profile.value?.projects
  return Array.isArray(ids) && ids.length > 0 ? ids : null
})

const visibleProjects = computed(() => {
  if (isSuperAdmin.value) return projects.value
  if (!allowedIds.value) return []
  const allowed = new Set(allowedIds.value.map((id) => Number(id)))
  return projects.value.filter((p) => allowed.has(Number(p.id)))
})

function syncCurrentSelection() {
  if (isSuperAdmin.value) {
    const ok =
      current.value === '__all__'
      || visibleProjects.value.some((p) => p.slug === current.value)
    if (!ok) current.value = '__all__'
    setCurrentProject(current.value === '__all__' ? '__all__' : current.value)
    return
  }

  if (current.value === '__all__') current.value = ''

  const visible = visibleProjects.value
  if (!visible.length) {
    current.value = ''
    setCurrentProject(null)
    return
  }

  if (!visible.some((p) => p.slug === current.value)) {
    current.value = visible[0].slug
  }
  setCurrentProject(current.value)
}

async function load() {
  loading.value = true
  error.value = null
  try {
    try {
      const me = await apiFetch('/api/staff/auth/me', { withProject: false })
      if (me) updateStaffProfile(me)
    } catch (_) { /* profile из login достаточен */ }

    projects.value = await apiFetch('/api/admin/projects', { withProject: false })
    syncCurrentSelection()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(current, (v) => {
  setCurrentProject(v)
  router.replace({ path: router.currentRoute.value.fullPath, force: true }).catch(() => {})
  window.dispatchEvent(new CustomEvent('staff:project-changed', { detail: v }))
})

onMounted(load)
</script>

<template>
  <div v-if="isSuperAdmin || profile" class="project-selector">
    <label class="project-selector__label" for="admin-project-select">Проект</label>
    <select
      v-if="isSuperAdmin || visibleProjects.length"
      id="admin-project-select"
      v-model="current"
      class="project-selector__select"
      :disabled="loading"
      aria-label="Выбор проекта"
    >
      <option v-if="isSuperAdmin" value="__all__">Все проекты</option>
      <option
        v-for="p in visibleProjects"
        :key="p.id"
        :value="p.slug"
      >
        {{ p.name }}
      </option>
    </select>
    <span
      v-else-if="!loading"
      class="project-selector__empty"
    >Нет проектов</span>
    <small v-if="error" class="project-selector__err">{{ error }}</small>
  </div>
</template>

<style scoped>
.project-selector {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0;
  flex: 0 1 auto;
  min-width: 0;
  max-width: min(240px, 42vw);
  height: 36px;
  padding: 0 10px 0 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-sm);
}

.project-selector__label {
  flex: 0 0 auto;
  margin-right: 8px;
  color: var(--text-soft);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}

.project-selector__select {
  flex: 1 1 auto;
  min-width: 0;
  width: auto;
  max-width: 100%;
  padding: 0 18px 0 0;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2362708a' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0 center;
}

.project-selector__select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.project-selector__select:focus-visible {
  outline: none;
}

.project-selector__err {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  color: var(--danger);
  font-size: 11px;
  white-space: nowrap;
}

.project-selector__empty {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

@media (max-width: 560px) {
  .project-selector__label {
    display: none;
  }

  .project-selector {
    max-width: min(200px, 38vw);
    padding-left: 10px;
  }
}
</style>
