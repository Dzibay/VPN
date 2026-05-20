<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchJson } from '../api/client.js'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  inputId: {
    type: String,
    default: '',
  },
  placeholder: {
    type: String,
    default: '',
  },
  minQueryLength: {
    type: Number,
    default: 3,
  },
})

const emit = defineEmits(['update:modelValue', 'select'])

const localText = ref(String(props.modelValue ?? ''))
const open = ref(false)
const loading = ref(false)
const fetchError = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, email: string | null, telegram_id: number | null, telegram_username: string | null }>>} */
const suggestions = ref([])
let debounceTimer = null
let blurTimer = null

watch(
  () => props.modelValue,
  (v) => {
    localText.value = String(v ?? '')
  },
)

function clearTimers() {
  if (debounceTimer != null) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  if (blurTimer != null) {
    clearTimeout(blurTimer)
    blurTimer = null
  }
}

onBeforeUnmount(() => {
  clearTimers()
})

async function runSearch() {
  const q = localText.value.trim()
  if (q.length < props.minQueryLength) {
    suggestions.value = []
    fetchError.value = null
    open.value = false
    return
  }
  loading.value = true
  fetchError.value = null
  try {
    const params = new URLSearchParams({ q, limit: '30' })
    const data = await fetchJson(`/api/users/search?${params.toString()}`)
    suggestions.value = Array.isArray(data) ? data : []
    open.value = q.length >= props.minQueryLength
  } catch (e) {
    fetchError.value = e.message || String(e)
    suggestions.value = []
    open.value = false
  } finally {
    loading.value = false
  }
}

function scheduleSearch() {
  clearTimers()
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    void runSearch()
  }, 320)
}

function onInputNative(e) {
  const v = e.target?.value ?? ''
  localText.value = v
  emit('update:modelValue', v)
  scheduleSearch()
}

function onFocus() {
  const q = localText.value.trim()
  if (q.length >= props.minQueryLength) {
    void runSearch()
  } else if (suggestions.value.length > 0) {
    open.value = true
  }
}

function onBlur() {
  blurTimer = setTimeout(() => {
    open.value = false
    blurTimer = null
  }, 180)
}

function onMouseDownOption() {
  if (blurTimer != null) {
    clearTimeout(blurTimer)
    blurTimer = null
  }
}

function parseSubmittedUserId(raw) {
  const s = String(raw ?? '').trim()
  if (!/^\d+$/.test(s)) return null
  const n = Number.parseInt(s, 10)
  if (!Number.isFinite(n) || n < 1) return null
  return n
}

function pickUser(row) {
  clearTimers()
  const id = String(row.id)
  localText.value = id
  emit('update:modelValue', id)
  emit('select', row)
  suggestions.value = []
  open.value = false
  fetchError.value = null
}

function onEnterKey(e) {
  e.preventDefault()
  clearTimers()
  const q = localText.value.trim()
  const userId = parseSubmittedUserId(q)
  if (userId != null) {
    const fromList = suggestions.value.find((r) => Number(r.id) === userId)
    pickUser(
      fromList ?? {
        id: userId,
        email: null,
        telegram_id: null,
        telegram_username: null,
      },
    )
    return
  }
  if (open.value && suggestions.value.length > 0) {
    pickUser(suggestions.value[0])
  }
}

/** Текст под #id в списке (без дублирования id). */
function formatRowMeta(row) {
  const parts = []
  if (row.email) parts.push(row.email)
  if (row.telegram_username) parts.push(`@${row.telegram_username}`)
  if (row.telegram_id != null) parts.push(`tg ${row.telegram_id}`)
  return parts.length ? parts.join(' · ') : '—'
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
        @input="onInputNative"
        @keydown.enter.prevent="onEnterKey"
        @focus="onFocus"
        @blur="onBlur"
      />
    </div>
    <p v-if="fetchError" class="suggest-err">{{ fetchError }}</p>
    <div v-show="open" class="suggest-panel" role="listbox">
      <p v-if="loading" class="suggest-muted">Поиск…</p>
      <p v-else-if="suggestions.length === 0" class="suggest-muted">Нет совпадений</p>
      <template v-else>
        <button
          v-for="row in suggestions"
          :key="row.id"
          type="button"
          class="suggest-option"
          role="option"
          @mousedown.prevent="onMouseDownOption"
          @click="pickUser(row)"
        >
          <span class="suggest-option-id">#{{ row.id }}</span>
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
  padding: 0.55rem 0.9rem 0.55rem 2.65rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-size: 0.95rem;
  line-height: 1.4;
  letter-spacing: 0.01em;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.staff-user-suggest-input::placeholder {
  color: var(--muted);
  font-size: 0.82rem;
  letter-spacing: 0;
}

.staff-user-suggest-input:hover {
  border-color: color-mix(in srgb, var(--text-h) 22%, var(--card-border));
}

.staff-user-suggest-input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--text-h) 38%, var(--card-border));
  background: color-mix(in srgb, var(--surface) 88%, var(--card-bg));
  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--text-h) 14%, transparent),
    0 1px 2px rgba(0, 0, 0, 0.06);
}

.suggest-wrap--open .staff-user-suggest-input {
  border-color: color-mix(in srgb, var(--text-h) 32%, var(--card-border));
}

.suggest-err {
  margin: 0.4rem 0 0;
  font-size: 0.8rem;
  color: var(--danger);
  line-height: 1.35;
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
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.12),
    0 0 0 1px color-mix(in srgb, var(--text-h) 6%, transparent);
  padding: 0.35rem 0;
}

.suggest-muted {
  margin: 0.55rem 0.9rem;
  font-size: 0.84rem;
  color: var(--muted);
  line-height: 1.4;
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
  transition: background 0.12s ease;
}

.suggest-option:first-of-type {
  border-top: none;
}

.suggest-option-id {
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  font-weight: 700;
  color: color-mix(in srgb, var(--text-h) 88%, var(--muted));
  letter-spacing: 0.02em;
}

.suggest-option-meta {
  font-size: 0.8rem;
  color: var(--muted);
  line-height: 1.35;
  word-break: break-word;
}

.suggest-option:hover,
.suggest-option:focus-visible {
  background: color-mix(in srgb, var(--surface) 65%, var(--card-bg));
  outline: none;
}
</style>
