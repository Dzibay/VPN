<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  clearSession,
  getAccessToken,
} from '../auth/session.js'

const router = useRouter()
const route = useRoute()

const hasToken = ref(false)

function refreshSessions() {
  hasToken.value = Boolean(getAccessToken())
}

const isHome = computed(() => route.name === 'home')

const showGuestAuthLinks = computed(
  () => !hasToken.value && route.name !== 'cabinet',
)

const homeNavLinks = [
  { href: '#benefits', label: 'Преимущества' },
  { href: '#pricing', label: 'Тарифы' },
  { href: '#how', label: 'Устройства' },
  { href: '#faq', label: 'FAQ' },
  { href: '#faq', label: 'Поддержка' },
]

const showUserLogout = computed(() => Boolean(hasToken.value))

/** Горизонтальный логотип сайта: frontend/public/images/home/header-logo.png */
const SITE_LOGO_WORDMARK = '/images/home/header-logo.png'

const headerWordmarkOk = ref(true)

function logout() {
  clearSession()
  refreshSessions()
  if (route.path.startsWith('/cabinet') || route.path.startsWith('/admin')) {
    router.push('/login')
  } else {
    router.push('/')
  }
}

onMounted(refreshSessions)
router.afterEach(refreshSessions)
</script>

<template>
  <header
    class="shell"
    :class="{ 'shell--home': route.name === 'home' }"
    aria-label="Шапка сайта"
  >
    <RouterLink
      class="brand"
      :class="{ 'brand--wordmark': headerWordmarkOk }"
      to="/"
    >
      <img
        v-if="headerWordmarkOk"
        class="brand-wordmark"
        :src="SITE_LOGO_WORDMARK"
        width="220"
        height="48"
        alt="Подорожник VPN"
        decoding="async"
        @error="headerWordmarkOk = false"
      />
      <template v-else>
        <img
          class="brand-logo"
          src="/icons/podorozhnik-logo.png"
          width="40"
          height="40"
          alt=""
          decoding="async"
        />
        <span class="brand-text">Подорожник VPN</span>
      </template>
    </RouterLink>

    <nav
      v-if="isHome"
      class="home-nav"
      aria-label="Разделы главной страницы"
    >
      <a
        v-for="link in homeNavLinks"
        :key="link.label"
        class="home-nav__link"
        :href="link.href"
      >{{ link.label }}</a>
    </nav>

    <span class="spacer" aria-hidden="true" />

    <div class="toolbar">
      <nav class="user-bar" aria-label="Аккаунт">
        <template v-if="showGuestAuthLinks">
          <RouterLink class="nav-link" to="/login">Войти</RouterLink>
          <RouterLink class="nav-link nav-accent" to="/register">
            Создать аккаунт
          </RouterLink>
        </template>
        <template v-else-if="showUserLogout">
          <button type="button" class="nav-btn ghost" @click="logout">
            Выйти
          </button>
        </template>
      </nav>
    </div>
  </header>
</template>

<style scoped>
.shell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid var(--nav-border);
  background: var(--nav-bg);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--shadow-sm);
  /* Запросы по ширине шапки (viewport), не по user-bar — иначе цикл из‑за скрытой «Регистрация». */
  container-type: inline-size;
  container-name: shell;
}

/* На главной иначе видна «линия» между шапкой и героем с градиентом. */
.shell--home {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 0.75rem 1rem;
  border-bottom: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: none;
}

.shell--home .brand {
  grid-column: 1;
  justify-self: start;
  min-width: 0;
}

.shell--home .home-nav {
  grid-column: 2;
  justify-self: center;
}

.shell--home .spacer {
  display: none;
}

.shell--home .toolbar {
  grid-column: 3;
  justify-self: end;
  margin-left: 0;
}

.home-nav {
  display: none;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.15rem 1.1rem;
  min-width: 0;
}

@media (min-width: 900px) {
  .home-nav {
    display: flex;
  }
}

.home-nav__link {
  color: #4b5563;
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 600;
  padding: 0.35rem 0.15rem;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.home-nav__link:hover {
  color: #1d9a5c;
}

.shell--home .brand-text {
  color: #111827;
}

.shell--home .nav-link {
  color: #4b5563;
}

.shell--home .nav-link:hover {
  color: #111827;
  background: rgba(29, 154, 92, 0.08);
}

.shell--home .nav-accent {
  color: #1d9a5c;
}

.shell--home .nav-accent:hover {
  color: #18804d;
  background: rgba(29, 154, 92, 0.1);
}

.spacer {
  flex: 1;
  min-width: 0.5rem;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.65rem 0.85rem;
  margin-left: auto;
}

.user-bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
  min-width: 0;
}

/* Узкая шапка (телефон): только «Вход»; ширина контейнера не зависит от содержимого user-bar. */
@container shell (max-width: 560px) {
  .nav-accent {
    display: none;
  }

  .toolbar {
    gap: 0.45rem 0.55rem;
  }

  .brand {
    gap: 0.35rem;
  }

  .brand-text {
    font-size: 0.98rem;
  }

  .nav-link {
    padding: 0.35rem 0.55rem;
    font-size: 0.85rem;
  }

  .nav-btn {
    padding: 0.35rem 0.55rem;
    font-size: 0.82rem;
  }
}

@media (max-width: 560px) {
  .shell {
    padding: 0.5rem 0.75rem;
    gap: 0.45rem 0.55rem;
  }
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
  color: var(--text-h);
  font-family: var(--heading);
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.02em;
}

.brand--wordmark {
  gap: 0;
}

.brand-wordmark {
  display: block;
  height: clamp(2.25rem, 4.5vw, 2.85rem);
  width: auto;
  max-width: min(13.75rem, 52vw);
  object-fit: contain;
  object-position: left center;
}

.brand-logo {
  display: block;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  object-fit: contain;
  box-shadow: 0 1px 3px
    color-mix(in srgb, var(--accent) 16%, transparent);
  flex-shrink: 0;
}

.nav-link {
  color: var(--nav-link);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.9rem;
  padding: 0.4rem 0.75rem;
  border-radius: 10px;
  transition:
    background 0.2s ease,
    color 0.2s ease;
}

.nav-link:hover {
  color: var(--text-h);
  background: var(--nav-link-hover-bg);
}

.nav-link.router-link-active {
  color: var(--accent);
  background: var(--accent-soft);
}

.nav-accent {
  color: var(--accent);
}

.nav-btn {
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.4rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface-glass);
  color: var(--nav-link);
  cursor: pointer;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease;
}

.nav-btn:hover {
  color: var(--text-h);
  background: var(--nav-link-hover-bg);
  border-color: var(--accent-border);
}

.nav-btn.ghost {
  background: transparent;
  border-color: transparent;
}

.nav-btn.ghost:hover {
  background: var(--danger-soft);
  border-color: rgba(225, 29, 72, 0.25);
  color: var(--danger);
}

@media (prefers-color-scheme: dark) {
  .nav-btn.ghost:hover {
    color: var(--danger);
  }
}
</style>
