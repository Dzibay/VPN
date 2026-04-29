<script setup>
/**
 * Одна кнопка «Действия» + выпадающая панель (Teleport в body), как в таблице серверов.
 * Слот по умолчанию: <template #default="{ close }">...</template>
 */
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'

const props = defineProps({
  /** Уникальный суффикс для id и aria-controls (например ref-42) */
  menuIdSuffix: {
    type: [String, Number],
    required: true,
  },
  triggerLabel: {
    type: String,
    default: 'Действия',
  },
  panelAriaLabel: {
    type: String,
    default: 'Действия',
  },
})

const open = ref(false)
const triggerEl = ref(null)
const panelEl = ref(null)
const floatStyle = ref({})

const panelId = () => `row-actions-menu-${props.menuIdSuffix}`

async function updatePosition() {
  const btn = triggerEl.value
  if (!(btn instanceof HTMLElement) || !open.value) return
  await nextTick()
  const r = btn.getBoundingClientRect()
  const gap = 6
  const menuMin = 216
  const w = Math.max(menuMin, r.width)
  let left = r.right - w
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8))
  const h = panelEl.value?.offsetHeight ?? 200
  let top = r.bottom + gap
  if (top + h > window.innerHeight - 8) {
    top = Math.max(8, r.top - gap - h)
  }
  floatStyle.value = {
    position: 'fixed',
    top: `${top}px`,
    left: `${left}px`,
    minWidth: `${w}px`,
    zIndex: 2000,
  }
}

function toggle(ev) {
  ev?.stopPropagation?.()
  open.value = !open.value
  if (open.value) {
    requestAnimationFrame(() => {
      void updatePosition()
    })
  }
}

function close() {
  open.value = false
}

function onDocClick(ev) {
  if (!(ev.target instanceof Node)) return
  const tr = triggerEl.value
  const pan = panelEl.value
  if (tr?.contains(ev.target)) return
  if (pan?.contains(ev.target)) return
  close()
}

function onEscape(e) {
  if (e.key === 'Escape') close()
}

function onScrollResize() {
  if (open.value) void updatePosition()
}

watch(open, async (v) => {
  if (v) {
    await nextTick()
    void updatePosition()
  }
})

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onEscape)
  document.addEventListener('scroll', onScrollResize, true)
  window.addEventListener('resize', onScrollResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onEscape)
  document.removeEventListener('scroll', onScrollResize, true)
  window.removeEventListener('resize', onScrollResize)
})

defineExpose({ close })
</script>

<template>
  <div class="row-actions-dropdown-root">
    <button
      ref="triggerEl"
      type="button"
      class="btn-dropdown-trigger btn-secondary btn-tiny"
      :aria-expanded="open"
      aria-haspopup="menu"
      :aria-controls="panelId()"
      @click.stop="toggle"
    >
      {{ triggerLabel }}
      <span class="btn-dropdown-chevron" aria-hidden="true">▾</span>
    </button>
    <Teleport to="body">
      <div
        v-if="open"
        :id="panelId()"
        ref="panelEl"
        class="dropdown-panel row-actions-dropdown-panel"
        :style="floatStyle"
        role="menu"
        :aria-label="panelAriaLabel"
      >
        <slot :close="close" />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.row-actions-dropdown-root {
  display: inline-flex;
}

.btn-dropdown-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  min-width: 6.75rem;
}

.btn-dropdown-chevron {
  font-size: 0.62rem;
  opacity: 0.75;
  line-height: 1;
}

.dropdown-panel {
  min-width: 13.5rem;
  padding: 0.4rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-md);
}

.row-actions-dropdown-panel {
  max-height: min(70vh, 28rem);
  overflow-y: auto;
}
</style>

<style>
/* Содержимое слота телепортируется в body — стили пунктов без scoped */
.row-actions-dropdown-panel .dropdown-item {
  display: flex;
  width: 100%;
  align-items: center;
  text-align: left;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0.5rem 0.65rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-h);
  cursor: pointer;
  text-decoration: none;
  box-sizing: border-box;
}

.row-actions-dropdown-panel .dropdown-item:hover:not(:disabled) {
  background: var(--surface);
}

.row-actions-dropdown-panel .dropdown-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.row-actions-dropdown-panel .dropdown-item--danger {
  color: var(--danger);
}

.row-actions-dropdown-panel .dropdown-sep {
  height: 1px;
  margin: 0.35rem 0.25rem;
  background: var(--border);
  border: none;
  padding: 0;
}
</style>
