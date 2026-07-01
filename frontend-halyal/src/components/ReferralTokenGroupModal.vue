<script setup>
import { computed, ref, watch } from 'vue'
import AppModal from './AppModal.vue'

const GROUP_COLORS = [
  '#58d68d',
  '#38bdf8',
  '#a78bfa',
  '#f472b6',
  '#fb923c',
  '#facc15',
  '#34d399',
  '#818cf8',
]

const props = defineProps({
  open: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
  /** @type {{ id?: number, name?: string, color?: string, link_ids?: number[] } | null} */
  editingGroup: { type: Object, default: null },
  /** @type {Array<{ id: number, token: string, owner_kind?: string }>} */
  availableLinks: { type: Array, default: () => [] },
  /** Предвыбранные токены при создании группы (например из bulk-выбора в таблице) */
  initialLinkIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'submit'])

const formName = ref('')
const formColor = ref(GROUP_COLORS[0])
const selectedLinkIds = ref([])
const tokenFilter = ref('')

const isEdit = computed(() => props.editingGroup?.id != null)

const modalTitle = computed(() =>
  isEdit.value ? 'Редактировать группу' : 'Новая группа токенов',
)

const filteredLinks = computed(() => {
  const q = tokenFilter.value.trim().toLowerCase()
  const list = props.availableLinks ?? []
  if (!q) return list
  return list.filter((r) => {
    const token = String(r.token ?? '').toLowerCase()
    const id = String(r.id ?? '')
    const kind = String(r.owner_kind ?? '').toLowerCase()
    return token.includes(q) || id.includes(q) || kind.includes(q)
  })
})

const allFilteredSelected = computed(() => {
  const ids = filteredLinks.value.map((r) => r.id)
  return ids.length > 0 && ids.every((id) => selectedLinkIds.value.includes(id))
})

function resetForm() {
  formName.value = props.editingGroup?.name ?? ''
  formColor.value = props.editingGroup?.color ?? GROUP_COLORS[0]
  if (props.editingGroup?.id != null) {
    selectedLinkIds.value = [...(props.editingGroup?.link_ids ?? [])]
  } else {
    selectedLinkIds.value = [...(props.initialLinkIds ?? [])]
  }
  tokenFilter.value = ''
}

watch(
  () =>
    [
      props.open,
      props.editingGroup?.id,
      props.editingGroup?.name,
      (props.initialLinkIds ?? []).join(','),
    ].join(':'),
  () => {
    if (props.open) resetForm()
  },
  { immediate: true },
)

function toggleLinkId(id) {
  const set = new Set(selectedLinkIds.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selectedLinkIds.value = [...set]
}

function toggleSelectAllFiltered() {
  const ids = filteredLinks.value.map((r) => r.id)
  if (allFilteredSelected.value) {
    const remove = new Set(ids)
    selectedLinkIds.value = selectedLinkIds.value.filter((id) => !remove.has(id))
  } else {
    const set = new Set(selectedLinkIds.value)
    ids.forEach((id) => set.add(id))
    selectedLinkIds.value = [...set]
  }
}

function onSubmit() {
  const name = formName.value.trim()
  if (!name) return
  emit('submit', {
    name,
    color: formColor.value,
    link_ids: [...selectedLinkIds.value],
  })
}
</script>

<template>
  <AppModal
    v-if="open"
    :title="modalTitle"
    :max-width="520"
    :busy="busy"
    @close="emit('close')"
  >
    <form class="modal-form group-modal" @submit.prevent="onSubmit">
      <label class="field">
        <span>Название группы</span>
        <input
          v-model="formName"
          type="text"
          class="input-like"
          maxlength="128"
          placeholder="Например: Telegram-каналы"
          autocomplete="off"
          required
        />
      </label>

      <div class="field">
        <span class="field-label">Цвет</span>
        <div class="color-swatches" role="radiogroup" aria-label="Цвет группы">
          <button
            v-for="c in GROUP_COLORS"
            :key="c"
            type="button"
            class="color-swatch"
            :class="{ 'color-swatch--active': formColor === c }"
            :style="{ '--swatch': c }"
            :aria-pressed="formColor === c"
            :title="c"
            @click="formColor = c"
          />
        </div>
      </div>

      <div class="field token-picker">
        <div class="token-picker__head">
          <span class="field-label">Токены в группе</span>
          <span class="token-picker__count">{{ selectedLinkIds.length }} выбрано</span>
        </div>
        <input
          v-model="tokenFilter"
          type="search"
          class="input-like"
          placeholder="Поиск по токену или id…"
          autocomplete="off"
        />
        <label class="token-picker__select-all">
          <input
            type="checkbox"
            :checked="allFilteredSelected"
            :disabled="filteredLinks.length === 0"
            @change="toggleSelectAllFiltered"
          />
          <span>Выбрать все в списке</span>
        </label>
        <div class="token-picker__list" role="listbox" aria-multiselectable="true">
          <label
            v-for="r in filteredLinks"
            :key="r.id"
            class="token-picker__item"
            :class="{ 'token-picker__item--on': selectedLinkIds.includes(r.id) }"
          >
            <input
              type="checkbox"
              :checked="selectedLinkIds.includes(r.id)"
              @change="toggleLinkId(r.id)"
            />
            <span class="token-picker__token mono">{{ r.token }}</span>
            <span class="token-picker__meta">#{{ r.id }}</span>
          </label>
          <p v-if="filteredLinks.length === 0" class="token-picker__empty muted">
            Нет токенов по фильтру
          </p>
        </div>
      </div>

      <p v-if="error" class="form-err">{{ error }}</p>

      <div class="modal-actions">
        <button type="button" class="btn-secondary" :disabled="busy" @click="emit('close')">
          Отмена
        </button>
        <button type="submit" class="btn-primary" :disabled="busy || !formName.trim()">
          {{ busy ? 'Сохранение…' : isEdit ? 'Сохранить' : 'Создать группу' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>

<style scoped>
.group-modal {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.field-label {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-h);
  margin-bottom: 0.35rem;
}
.color-swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.color-swatch {
  width: 2rem;
  height: 2rem;
  border-radius: 999px;
  border: 2px solid transparent;
  background: var(--swatch);
  cursor: pointer;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease,
    border-color 0.15s ease;
}
.color-swatch:hover {
  transform: scale(1.08);
}
.color-swatch--active {
  border-color: var(--text-h);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--swatch) 35%, transparent);
}
.token-picker__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}
.token-picker__count {
  font-size: 0.78rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.token-picker__select-all {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0.5rem 0 0.35rem;
  font-size: 0.82rem;
  cursor: pointer;
}
.token-picker__list {
  max-height: 14rem;
  overflow: auto;
  border: 1px solid var(--card-border);
  border-radius: 12px;
  background: var(--surface);
  padding: 0.35rem;
}
.token-picker__item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.55rem;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.token-picker__item:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.token-picker__item--on {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.token-picker__token {
  font-size: 0.78rem;
  word-break: break-all;
}
.token-picker__meta {
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.token-picker__empty {
  margin: 0.75rem;
  font-size: 0.82rem;
  text-align: center;
}
.mono {
  font-family: ui-monospace, monospace;
}
</style>
