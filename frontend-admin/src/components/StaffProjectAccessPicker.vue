<script setup>
import { computed } from 'vue'

const props = defineProps({
  projects: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})

const model = defineModel({ type: Array, default: () => [] })

const selected = computed({
  get() {
    return new Set((model.value || []).map((id) => Number(id)))
  },
  set(next) {
    model.value = [...next].sort((a, b) => a - b)
  },
})

function toggle(projectId, checked) {
  const next = new Set(selected.value)
  const id = Number(projectId)
  if (checked) next.add(id)
  else next.delete(id)
  selected.value = next
}

function isChecked(projectId) {
  return selected.value.has(Number(projectId))
}
</script>

<template>
  <div class="project-access">
    <p v-if="!projects.length" class="project-access__empty">Нет проектов в системе</p>
    <ul v-else class="project-access__list">
      <li v-for="p in projects" :key="p.id">
        <label class="project-access__item">
          <input
            type="checkbox"
            :checked="isChecked(p.id)"
            :disabled="disabled"
            @change="toggle(p.id, $event.target.checked)"
          />
          <span class="project-access__name">{{ p.name }}</span>
          <span class="project-access__slug">{{ p.slug }}</span>
        </label>
      </li>
    </ul>
    <p v-if="projects.length" class="project-access__hint">
      Выбрано: {{ model.length }}
    </p>
  </div>
</template>

<style scoped>
.project-access__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.project-access__item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-raised);
  cursor: pointer;
}

.project-access__item input {
  flex: 0 0 auto;
}

.project-access__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.project-access__slug {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  font-family: monospace;
}

.project-access__hint,
.project-access__empty {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
