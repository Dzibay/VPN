<script setup>
import { computed, useAttrs } from 'vue'
import { RouterLink } from 'vue-router'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: (v) =>
      ['primary', 'secondary', 'accent', 'pay', 'telegram'].includes(v),
  },
  block: { type: Boolean, default: false },
  stacked: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
  href: { type: String, default: undefined },
  to: { type: [String, Object], default: undefined },
  target: { type: String, default: undefined },
  rel: { type: String, default: undefined },
})

const emit = defineEmits(['click'])
const attrs = useAttrs()

const isAnchor = computed(() => typeof props.href === 'string' && props.href.length > 0)
const isRouterLink = computed(
  () => props.to != null && props.to !== '',
)

const tag = computed(() => {
  if (isAnchor.value) return 'a'
  if (isRouterLink.value) return RouterLink
  return 'button'
})

const rootClass = computed(() => [
  'app-action-btn',
  `app-action-btn--${props.variant}`,
  {
    'app-action-btn--block': props.block,
    'app-action-btn--stacked': props.stacked,
  },
  attrs.class,
])

const passthroughAttrs = computed(() => {
  const { class: _class, ...rest } = attrs
  return rest
})

function onClick(event) {
  if (props.disabled) {
    event.preventDefault()
    return
  }
  emit('click', event)
}
</script>

<template>
  <component
    :is="tag"
    :class="rootClass"
    :href="isAnchor ? href : undefined"
    :to="isRouterLink ? to : undefined"
    :type="!isAnchor && !isRouterLink ? type : undefined"
    :disabled="!isAnchor && !isRouterLink ? disabled : undefined"
    :aria-disabled="(isAnchor || isRouterLink) && disabled ? 'true' : undefined"
    :tabindex="(isAnchor || isRouterLink) && disabled ? -1 : undefined"
    :target="target"
    :rel="rel"
    v-bind="passthroughAttrs"
    @click="onClick"
  >
    <span
      v-if="$slots.icon"
      class="app-action-btn__icon"
    ><slot name="icon" /></span>
    <span
      v-if="$slots.default"
      class="app-action-btn__label"
    ><slot /></span>
  </component>
</template>

<style scoped>
.app-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  box-sizing: border-box;
  margin: 0;
  padding: 0.5rem 1rem;
  min-height: 2.625rem;
  border-radius: var(--radius);
  border: 1px solid transparent;
  font-family: inherit;
  font-size: 0.88rem;
  font-weight: 600;
  line-height: 1.3;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  transition:
    filter 0.15s ease,
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease,
    opacity 0.15s ease,
    box-shadow 0.15s ease;
}

.app-action-btn--block {
  width: 100%;
  max-width: 100%;
}

.app-action-btn--stacked {
  border-radius: 0;
  border-width: 0;
  box-shadow: none;
}

.app-action-btn__icon {
  flex-shrink: 0;
  display: inline-flex;
  color: currentColor;
  opacity: 0.95;
}

.app-action-btn__label {
  min-width: 0;
}

.app-action-btn--primary {
  color: var(--on-accent);
  background: linear-gradient(
    135deg,
    var(--brand-mint) 0%,
    var(--brand-teal) 100%
  );
  border-color: transparent;
  box-shadow: var(--shadow-sm);
}

.app-action-btn--primary:hover:not(:disabled):not([aria-disabled='true']) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-md);
}

.app-action-btn--secondary {
  color: var(--text-h);
  background: var(--surface-glass);
  border-color: var(--card-border);
}

.app-action-btn--secondary:hover:not(:disabled):not([aria-disabled='true']) {
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.app-action-btn--accent {
  color: var(--on-accent);
  background: color-mix(in srgb, var(--accent) 78%, #050a08 22%);
  border-color: color-mix(in srgb, var(--accent-border) 75%, #020403 25%);
}

.app-action-btn--accent:hover:not(:disabled):not([aria-disabled='true']) {
  filter: brightness(1.04);
  background: color-mix(in srgb, var(--accent-hover) 80%, #050a08 20%);
}

.app-action-btn--pay {
  color: #dbeafe;
  background: linear-gradient(
    168deg,
    rgba(99, 102, 234, 0.38) 0%,
    rgba(45, 179, 157, 0.14) 42%,
    rgba(15, 23, 42, 0.92) 100%
  );
  box-shadow: inset 0 1px 0 0 var(--nav-border);
}

.app-action-btn--pay:hover:not(:disabled):not([aria-disabled='true']) {
  filter: brightness(1.07);
  color: #f0f9ff;
}

.app-action-btn--telegram {
  color: #fff;
  background: #229ed9;
  border-color: transparent;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
}

.app-action-btn--telegram:hover:not(:disabled):not([aria-disabled='true']) {
  filter: brightness(1.06);
  background: #1f8fc7;
  box-shadow: 0 2px 8px rgba(34, 158, 217, 0.35);
}

.app-action-btn:disabled,
.app-action-btn[aria-disabled='true'] {
  opacity: 0.45;
  cursor: not-allowed;
  filter: none;
}

.app-action-btn--telegram:disabled,
.app-action-btn--telegram[aria-disabled='true'] {
  opacity: 0.65;
}

.app-action-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.app-action-btn--stacked:focus-visible {
  position: relative;
  z-index: 1;
  box-shadow: inset 0 0 0 2px rgba(0, 0, 0, 0.35), var(--focus-ring);
}

.app-action-btn--pay:focus-visible {
  box-shadow:
    inset 0 1px 0 0 var(--nav-border),
    inset 0 0 0 2px rgba(129, 140, 248, 0.65);
}

.app-action-btn--telegram:focus-visible {
  box-shadow:
    0 0 0 2px var(--card-bg),
    0 0 0 4px #229ed9;
}

@media (prefers-color-scheme: light) {
  .app-action-btn--primary {
    background: linear-gradient(
      135deg,
      var(--accent) 0%,
      var(--accent-muted) 100%
    );
  }

  .app-action-btn--accent {
    background: var(--accent);
    border-color: var(--accent-border);
  }

  .app-action-btn--accent:hover:not(:disabled):not([aria-disabled='true']) {
    background: var(--accent-hover);
    filter: none;
  }

  .app-action-btn--pay {
    color: #1e3a5f;
    background: linear-gradient(
      168deg,
      rgba(99, 102, 234, 0.2) 0%,
      rgba(45, 179, 157, 0.12) 45%,
      rgba(248, 250, 252, 0.98) 100%
    );
    box-shadow: inset 0 1px 0 0 rgba(29, 154, 92, 0.18);
  }

  .app-action-btn--pay:hover:not(:disabled):not([aria-disabled='true']) {
    color: #0f172a;
    filter: brightness(1.02);
  }

  .app-action-btn--pay:focus-visible {
    box-shadow:
      inset 0 1px 0 0 rgba(29, 154, 92, 0.18),
      inset 0 0 0 2px rgba(99, 102, 234, 0.45);
  }
}
</style>
