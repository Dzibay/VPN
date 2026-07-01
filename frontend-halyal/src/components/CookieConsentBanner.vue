<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { acceptCookieConsent, hasCookieConsent } from '../cookies/consent.js'

const visible = ref(false)

onMounted(() => {
  visible.value = !hasCookieConsent()
})

function accept() {
  acceptCookieConsent()
  visible.value = false
}
</script>

<template>
  <Transition name="cookie-banner">
    <aside
      v-if="visible"
      class="cookie-banner"
      role="dialog"
      aria-labelledby="cookie-banner-title"
      aria-describedby="cookie-banner-desc"
      aria-live="polite"
    >
      <div class="cookie-banner__inner">
        <p
          id="cookie-banner-title"
          class="cookie-banner__title"
        >
          Мы используем cookies
        </p>
        <p
          id="cookie-banner-desc"
          class="cookie-banner__text"
        >
          Сайт использует cookies и аналогичные технологии для работы сервиса,
          сохранения настроек, аналитики и безопасности. Продолжая пользоваться
          сайтом, вы соглашаетесь с их использованием.
          <RouterLink
            class="cookie-banner__link"
            to="/cookies"
          >
            Политика cookies
          </RouterLink>
        </p>
        <div class="cookie-banner__actions">
          <button
            type="button"
            class="btn-primary cookie-banner__accept"
            @click="accept"
          >
            Принять
          </button>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.cookie-banner {
  position: fixed;
  inset-inline: 0;
  bottom: 0;
  z-index: 200;
  padding: 0.75rem 0.85rem calc(0.75rem + env(safe-area-inset-bottom, 0px));
  pointer-events: none;
}

.cookie-banner__inner {
  pointer-events: auto;
  max-width: 42rem;
  margin: 0 auto;
  padding: 1rem 1.1rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--card-bg) 92%, transparent);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-md);
  display: grid;
  gap: 0.55rem;
}

@media (min-width: 640px) {
  .cookie-banner__inner {
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
    align-items: center;
    column-gap: 1rem;
    row-gap: 0.35rem;
  }

  .cookie-banner__title {
    grid-column: 1;
    grid-row: 1;
  }

  .cookie-banner__text {
    grid-column: 1;
    grid-row: 2;
  }

  .cookie-banner__actions {
    grid-column: 2;
    grid-row: 1 / span 2;
    align-self: center;
  }
}

.cookie-banner__title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-h);
  line-height: 1.3;
}

.cookie-banner__text {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--muted);
}

.cookie-banner__link {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
}

.cookie-banner__link:hover {
  color: var(--accent-hover);
}

.cookie-banner__actions {
  display: flex;
  justify-content: flex-end;
}

.cookie-banner__accept {
  width: 100%;
  min-width: 7.5rem;
}

@media (min-width: 640px) {
  .cookie-banner__accept {
    width: auto;
  }
}

.cookie-banner-enter-active,
.cookie-banner-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}

.cookie-banner-enter-from,
.cookie-banner-leave-to {
  opacity: 0;
  transform: translateY(0.75rem);
}
</style>
