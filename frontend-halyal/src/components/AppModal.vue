<script setup>
/**
 * Единая модалка админки/кабинета.
 *
 * Раньше разметка modal-backdrop/modal/modal-title и ~90 строк scoped-CSS
 * дублировались в каждом view с формами. Теперь:
 *   <AppModal v-if="open" title="Заголовок" :busy="saving" @close="close">
 *     <form class="modal-form" @submit.prevent="submit"> … </form>
 *   </AppModal>
 *
 * Берёт на себя: Teleport в body, закрытие по фону и Esc (с учётом :busy),
 * блокировку прокрутки страницы, доступность (role=dialog).
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  /** Максимальная ширина карточки (px или CSS-значение). */
  maxWidth: { type: [String, Number], default: 520 },
  /** Закрывать по клику на фон. */
  closeOnBackdrop: { type: Boolean, default: true },
  /** Идёт сохранение — блокирует закрытие по фону/Esc. */
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const cardStyle = {
  maxWidth: typeof props.maxWidth === 'number' ? `${props.maxWidth}px` : props.maxWidth,
}

const card = ref(null)

function requestClose() {
  if (props.busy) return
  emit('close')
}

function onBackdrop() {
  if (props.closeOnBackdrop) requestClose()
}

function onKeydown(e) {
  if (e.key === 'Escape') requestClose()
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.body.style.overflow = 'hidden'
  // Фокус на карточке для доступности и работы Esc.
  card.value?.focus?.()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" role="presentation" @click.self="onBackdrop">
      <div
        ref="card"
        class="modal"
        role="dialog"
        aria-modal="true"
        :aria-label="title || undefined"
        tabindex="-1"
        :style="cardStyle"
        @click.stop
      >
        <h2 v-if="title || $slots.title" class="modal-title">
          <slot name="title">{{ title }}</slot>
        </h2>
        <slot />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 12, 9, 0.55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1rem, 4vh, 2.5rem) 1rem;
  z-index: 50;
}

.modal {
  width: 100%;
  max-height: min(90dvh, 760px);
  overflow-y: auto;
  padding: 1.35rem 1.45rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg);
}

.modal:focus {
  outline: none;
}

.modal-title {
  margin: 0 0 0.85rem;
  font-size: 1.1rem;
  color: var(--text-h);
}
</style>
