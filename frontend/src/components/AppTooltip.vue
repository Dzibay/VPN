<script setup>
import { ref } from 'vue'

defineProps({
  /** Текст подсказки */
  text: {
    type: String,
    required: true,
  },
  /** Положение относительно триггера */
  placement: {
    type: String,
    default: 'top',
    validator: (v) => v === 'top' || v === 'bottom',
  },
})

const visible = ref(false)
</script>

<template>
  <span
    class="app-tooltip"
    @mouseenter="visible = true"
    @mouseleave="visible = false"
  >
    <span class="app-tooltip__trigger"><slot /></span>
    <Transition name="app-tooltip-fade">
      <span
        v-if="visible"
        class="app-tooltip__bubble"
        :class="{
          'app-tooltip__bubble--bottom': placement === 'bottom',
        }"
        role="tooltip"
      >
        {{ text }}
      </span>
    </Transition>
  </span>
</template>

<style scoped>
.app-tooltip {
  position: relative;
  display: inline-block;
  vertical-align: baseline;
}

.app-tooltip__trigger {
  display: inline;
}

.app-tooltip__bubble {
  position: absolute;
  left: 50%;
  z-index: 100;
  min-width: 10rem;
  max-width: min(17.5rem, calc(100vw - 1.5rem));
  padding: 0.5rem 0.7rem;
  border-radius: var(--radius);
  font-family: var(--sans);
  font-size: 0.82rem;
  font-weight: 500;
  line-height: 1.45;
  letter-spacing: 0.01em;
  color: var(--text);
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-md);
  pointer-events: none;
  word-wrap: break-word;
}

.app-tooltip__bubble--bottom {
  top: calc(100% + 0.5rem);
  bottom: auto;
  transform: translateX(-50%);
}

.app-tooltip__bubble:not(.app-tooltip__bubble--bottom) {
  bottom: calc(100% + 0.5rem);
  transform: translateX(-50%);
}

.app-tooltip-fade-enter-active,
.app-tooltip-fade-leave-active {
  transition: opacity 0.14s ease;
}

.app-tooltip-fade-enter-from,
.app-tooltip-fade-leave-to {
  opacity: 0;
}
</style>
