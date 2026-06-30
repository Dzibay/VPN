<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  /** @type {Array<{ id: number, token: string, owner_kind?: string, owner_user_id?: number | null }>} */
  items: {
    type: Array,
    default: () => [],
  },
  inputId: {
    type: String,
    default: '',
  },
  placeholder: {
    type: String,
    default: 'Поиск по токену, id или источнику',
  },
  minQueryLength: {
    type: Number,
    default: 1,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue', 'select', 'clear'])

const localText = ref('')
const open = ref(false)
let blurTimer = null

watch(
  () => [props.modelValue, props.items],
  () => syncTextFromValue(),
  { immediate: true, deep: true },
)

function syncTextFromValue() {
  const id = Number(props.modelValue)
  if (!Number.isFinite(id) || id < 1) {
    if (!localText.value.trim()) localText.value = ''
    return
  }
  const row = props.items.find((r) => Number(r.id) === id)
  localText.value = row ? formatRowLabel(row) : `#${id}`
}

function clearTimers() {
  if (blurTimer != null) {
    clearTimeout(blurTimer)
    blurTimer = null
  }
}

onBeforeUnmount(clearTimers)

function formatRowLabel(row) {
  const source =
    row.owner_kind === 'user' && row.owner_user_id != null
      ? `user ${row.owner_user_id}`
      : row.owner_kind
  return `#${row.id} · ${row.token} (${source})`
}

function formatRowMeta(row) {
  if (row.owner_kind === 'user' && row.owner_user_id != null) {
    return `user id ${row.owner_user_id}`
  }
  return String(row.owner_kind ?? '—')
}

const suggestions = computed(() => {
  const q = localText.value.trim().toLowerCase()
  if (q.length < props.minQueryLength) return []
  return props.items
    .filter((row) => {
      const token = String(row.token ?? '').toLowerCase()
      const id = String(row.id ?? '')
      const kind = String(row.owner_kind ?? '').toLowerCase()
      const uid = row.owner_user_id != null ? String(row.owner_user_id) : ''
      return (
        token.includes(q) ||
        id.includes(q) ||
        kind.includes(q) ||
        uid.includes(q)
      )
    })
    .slice(0, 30)
})

function onInputNative(e) {
  const v = e.target?.value ?? ''
  localText.value = v
  emit('update:modelValue', '')
  open.value = v.trim().length >= props.minQueryLength
}

function onFocus() {
  if (localText.value.trim().length >= props.minQueryLength) {
    open.value = true
  }
}

function onBlur() {
  blurTimer = setTimeout(() => {
    open.value = false
    blurTimer = null
    syncTextFromValue()
  }, 180)
}

function onMouseDownOption() {
  if (blurTimer != null) {
    clearTimeout(blurTimer)
    blurTimer = null
  }
}

function pickRow(row) {
  clearTimers()
  localText.value = formatRowLabel(row)
  emit('update:modelValue', String(row.id))
  emit('select', row)
  open.value = false
}

function onEnterKey(e) {
  e.preventDefault()
  const q = localText.value.trim()
  if (/^\d+$/.test(q)) {
    const id = Number.parseInt(q, 10)
    const row = props.items.find((r) => Number(r.id) === id)
    if (row) {
      pickRow(row)
      return
    }
  }
  if (suggestions.value.length > 0) {
    pickRow(suggestions.value[0])
  }
}

function clearSelection() {
  clearTimers()
  localText.value = ''
  emit('update:modelValue', '')
  emit('clear')
  open.value = false
}
</script>

<template>
  <div
    class="suggest-wrap"
    :class="{ 'suggest-wrap--open': open }"
    @keydown.escape.prevent="open = false"
  >
    <div class="suggest-input-shell">
      <span class="suggest-input-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="11" cy="11" r="7" />
          <path d="M16 16l5 5" />
        </svg>
      </span>
      <input
        :id="inputId || undefined"
        :value="localText"
        type="text"
        inputmode="search"
        autocomplete="off"
        class="staff-user-suggest-input"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="onInputNative"
        @keydown.enter.prevent="onEnterKey"
        @focus="onFocus"
        @blur="onBlur"
      />
      <button
        v-if="modelValue || localText"
        type="button"
        class="suggest-clear"
        aria-label="Сбросить"
        :disabled="disabled"
        @mousedown.prevent
        @click="clearSelection"
      >
        ×
      </button>
    </div>
    <div v-show="open" class="suggest-panel" role="listbox">
      <p v-if="suggestions.length === 0" class="suggest-muted">Нет совпадений</p>
      <template v-else>
        <button
          v-for="row in suggestions"
          :key="row.id"
          type="button"
          class="suggest-option"
          role="option"
          @mousedown.prevent="onMouseDownOption"
          @click="pickRow(row)"
        >
          <span class="suggest-option-id">#{{ row.id }} · {{ row.token }}</span>
          <span class="suggest-option-meta">{{ formatRowMeta(row) }}</span>
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.suggest-wrap {
  position: relative;
  width: 100%;
  min-width: 0;
}

.suggest-wrap--open {
  z-index: 5;
}

.suggest-input-shell {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.suggest-input-icon {
  position: absolute;
  left: 0.85rem;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  color: var(--muted);
  pointer-events: none;
  opacity: 0.85;
}

.staff-user-suggest-input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  min-height: 2.75rem;
  padding: 0.55rem 2.2rem 0.55rem 2.65rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-size: 0.95rem;
  line-height: 1.4;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.staff-user-suggest-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.staff-user-suggest-input::placeholder {
  color: var(--muted);
  font-size: 0.82rem;
}

.staff-user-suggest-input:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--text-h) 22%, var(--card-border));
}

.staff-user-suggest-input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--text-h) 38%, var(--card-border));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--text-h) 14%, transparent);
}

.suggest-wrap--open .staff-user-suggest-input {
  border-color: color-mix(in srgb, var(--text-h) 32%, var(--card-border));
}

.suggest-clear {
  position: absolute;
  right: 0.45rem;
  top: 50%;
  transform: translateY(-50%);
  width: 1.65rem;
  height: 1.65rem;
  border: none;
  border-radius: 999px;
  background: var(--card-bg);
  color: var(--muted);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}

.suggest-clear:hover:not(:disabled) {
  color: var(--text-h);
  background: var(--surface);
}

.suggest-panel {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 6px);
  z-index: 30;
  max-height: 260px;
  overflow-y: auto;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
  padding: 0.35rem 0;
}

.suggest-muted {
  margin: 0.55rem 0.9rem;
  font-size: 0.84rem;
  color: var(--muted);
}

.suggest-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.15rem;
  width: 100%;
  text-align: left;
  padding: 0.55rem 0.9rem;
  border: none;
  border-top: 1px solid color-mix(in srgb, var(--card-border) 70%, transparent);
  background: transparent;
  color: var(--text-h);
  font: inherit;
  cursor: pointer;
}

.suggest-option:first-of-type {
  border-top: none;
}

.suggest-option-id {
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  font-weight: 700;
}

.suggest-option-meta {
  font-size: 0.8rem;
  color: var(--muted);
}

.suggest-option:hover,
.suggest-option:focus-visible {
  background: color-mix(in srgb, var(--surface) 65%, var(--card-bg));
  outline: none;
}
</style>
