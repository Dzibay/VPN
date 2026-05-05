<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  options: {
    type: Array,
    default: () => [],
  },
  placeholder: {
    type: String,
    default: 'Выберите',
  },
  allLabel: {
    type: String,
    default: 'любой',
  },
})

const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const rootEl = ref(null)

const normalizedOptions = computed(() =>
  props.options.map((opt) => {
    if (typeof opt === 'string') {
      return { value: opt, label: opt }
    }
    const value = String(opt?.value ?? '')
    return {
      value,
      label: String(opt?.label ?? value),
    }
  }),
)

const selectedSet = computed(() => new Set((props.modelValue ?? []).map((v) => String(v))))

const triggerLabel = computed(() => {
  const selected = normalizedOptions.value.filter((opt) => selectedSet.value.has(opt.value))
  if (selected.length === 0) return props.allLabel
  if (selected.length <= 2) return selected.map((opt) => opt.label).join(', ')
  return `Выбрано: ${selected.length}`
})

function toggleOpen() {
  open.value = !open.value
}

function close() {
  open.value = false
}

function isChecked(value) {
  return selectedSet.value.has(String(value))
}

function toggleValue(value) {
  const str = String(value)
  const next = new Set(selectedSet.value)
  if (next.has(str)) next.delete(str)
  else next.add(str)
  emit('update:modelValue', Array.from(next))
}

function clearAll() {
  emit('update:modelValue', [])
}

function onPointerDown(e) {
  if (!open.value) return
  const root = rootEl.value
  if (!root) return
  if (!(e.target instanceof Node)) return
  if (!root.contains(e.target)) close()
}

onMounted(() => {
  window.addEventListener('pointerdown', onPointerDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', onPointerDown)
})
</script>

<template>
  <div ref="rootEl" class="msd">
    <button
      type="button"
      class="msd-trigger"
      :aria-expanded="open ? 'true' : 'false'"
      @click="toggleOpen"
    >
      <span class="msd-trigger-text">{{ triggerLabel }}</span>
      <span class="msd-caret" aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="msd-menu">
      <div class="msd-actions">
        <button type="button" class="msd-clear" @click="clearAll">{{ allLabel }}</button>
      </div>
      <div class="msd-list">
        <label v-for="opt in normalizedOptions" :key="opt.value" class="msd-item">
          <input
            type="checkbox"
            :checked="isChecked(opt.value)"
            @change="toggleValue(opt.value)"
          />
          <span>{{ opt.label }}</span>
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
.msd {
  position: relative;
  min-width: 11.5rem;
}

.msd-trigger {
  width: 100%;
  min-height: 2rem;
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  cursor: pointer;
}

.msd-trigger-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msd-caret {
  color: var(--muted);
}

.msd-menu {
  position: absolute;
  top: calc(100% + 0.3rem);
  left: 0;
  z-index: 20;
  width: 100%;
  min-width: 14rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  padding: 0.35rem;
}

.msd-actions {
  display: flex;
  justify-content: flex-end;
  padding: 0.2rem 0.2rem 0.35rem;
}

.msd-clear {
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--surface-glass);
  color: var(--text-h);
  font: inherit;
  font-size: 0.74rem;
  font-weight: 600;
  padding: 0.2rem 0.45rem;
  cursor: pointer;
}

.msd-list {
  max-height: 14rem;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.msd-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.25rem 0.3rem;
  border-radius: 8px;
  color: var(--text);
  font-weight: 500;
}

.msd-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 62%, transparent);
}
</style>
