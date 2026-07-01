<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Headphones } from 'lucide-vue-next'
import {
  refreshClientSupportUnread,
  startClientSupportUnreadPolling,
  stopClientSupportUnreadPolling,
  useClientSupportUnread,
} from '../composables/useClientSupportUnread.js'
import { brandLogoPath, brandName, isHalyalBrand } from '../brand/brandAssets.js'
import {
  clearSession,
  getAccessToken,
  getSessionRole,
} from '../auth/session.js'

const SUPPORT_BADGE_POLL_MS = 30000

const router = useRouter()
const route = useRoute()

const hasToken = ref(false)
const { unreadCount: clientSupportUnread } = useClientSupportUnread()

const supportBadgeCount = computed(() => {
  if (showClientSupportBell.value) return clientSupportUnread.value
  return 0
})

function refreshSessions() {
  hasToken.value = Boolean(getAccessToken())
}

const isHome = computed(() => route.name === 'home')

const showGuestAuthLinks = computed(
  () => !hasToken.value && route.name !== 'cabinet',
)

// На публичном сайте показываем колокольчик поддержки только клиентам (user).
// staff-роли (admin/manager) работают в отдельной админ-панели — тут им не место.
const showClientSupportBell = computed(
  () => hasToken.value && getSessionRole() === 'user',
)

const showSupportBell = showClientSupportBell

const supportBellTo = computed(() => ({ name: 'cabinet-support' }))

const supportBadgeLabel = computed(() => {
  const n = supportBadgeCount.value
  if (n < 1) return ''
  return n > 99 ? '99+' : String(n)
})

const supportBellAriaLabel = computed(() => {
  const n = supportBadgeCount.value
  return n > 0
    ? `Поддержка: ${n} новых ответов`
    : 'Поддержка: новых ответов нет'
})

const supportBellTitle = computed(() => {
  const n = supportBadgeCount.value
  return n > 0 ? `Поддержка: ${n} новых ответов` : 'Поддержка'
})

const homeNavLinks = [
  { href: '#benefits', label: 'Преимущества' },
  { href: '#pricing', label: 'Тарифы' },
  { href: '#how', label: 'Устройства' },
  { href: '#faq', label: 'FAQ' },
  { href: '#faq', label: 'Поддержка' },
]

const showUserLogout = computed(() => Boolean(hasToken.value))

/** Wordmark: header-logo.png (светлая тема), header-logo-white.png (tёмная). Только Подорожник. */
const SITE_LOGO_WORDMARK = '/images/home/header-logo.png'
const SITE_LOGO_WORDMARK_DARK = '/images/home/header-logo-white.png'

const headerWordmarkOk = ref(!isHalyalBrand)

function logout() {
  clearSession()
  refreshSessions()
  stopSupportBadgePolling()
  if (route.path.startsWith('/cabinet')) {
    router.push('/login')
  } else {
    router.push('/')
  }
}

function startSupportBadgePolling() {
  stopSupportBadgePolling()
  if (!showClientSupportBell.value) return
  startClientSupportUnreadPolling(SUPPORT_BADGE_POLL_MS)
}

function stopSupportBadgePolling() {
  stopClientSupportUnreadPolling()
}

watch(showSupportBell, (enabled) => {
  if (enabled) startSupportBadgePolling()
  else stopSupportBadgePolling()
})

onMounted(() => {
  refreshSessions()
  if (showSupportBell.value) startSupportBadgePolling()
})

onBeforeUnmount(stopSupportBadgePolling)

router.afterEach(() => {
  refreshSessions()
  if (showSupportBell.value) void refreshClientSupportUnread()
})
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
      <picture v-if="headerWordmarkOk">
        <source
          :srcset="SITE_LOGO_WORDMARK_DARK"
          media="(prefers-color-scheme: dark)"
        />
        <img
          class="brand-wordmark"
          :src="SITE_LOGO_WORDMARK"
          width="220"
          height="48"
          :alt="brandName"
          decoding="async"
          @error="headerWordmarkOk = false"
        />
      </picture>
      <template v-else>
        <img
          class="brand-logo"
          :src="brandLogoPath"
          width="40"
          height="40"
          alt=""
          decoding="async"
        />
        <span class="brand-text">{{ brandName }}</span>
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
      <RouterLink
        v-if="showSupportBell"
        class="support-bell"
        :class="{ 'support-bell--active': supportBadgeCount > 0 }"
        :to="supportBellTo"
        :aria-label="supportBellAriaLabel"
        :title="supportBellTitle"
      >
        <Headphones :size="18" :stroke-width="2" aria-hidden="true" />
        <span
          v-if="supportBadgeCount > 0"
          class="support-bell__badge"
        >{{ supportBadgeLabel }}</span>
      </RouterLink>
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

/* На главной — фон шапки согласован с системной темой (как :root). */
.shell--home {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 0.75rem 1rem;
  border-bottom: 1px solid var(--nav-border);
  background: var(--nav-bg);
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
  color: var(--nav-link);
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 600;
  padding: 0.35rem 0.15rem;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.home-nav__link:hover {
  color: var(--accent);
}

.shell--home .brand-text {
  color: var(--text-h);
}

.shell--home .nav-link {
  color: var(--nav-link);
}

.shell--home .nav-link:hover {
  color: var(--text-h);
  background: var(--nav-link-hover-bg);
}

.shell--home .nav-accent {
  color: var(--accent);
}

.shell--home .nav-accent:hover {
  color: var(--accent-hover);
  background: var(--accent-soft);
}

@media (prefers-color-scheme: light) {
  .shell--home {
    border-bottom: 1px solid #e5e7eb;
    background: rgba(255, 255, 255, 0.92);
  }

  .home-nav__link {
    color: #4b5563;
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

.support-bell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.35rem;
  height: 2.35rem;
  border-radius: 10px;
  color: var(--nav-link);
  text-decoration: none;
  border: 1px solid transparent;
  transition:
    color 0.2s ease,
    background 0.2s ease,
    border-color 0.2s ease;
}

.support-bell:hover {
  color: var(--text-h);
  background: var(--nav-link-hover-bg);
  border-color: var(--card-border);
}

.support-bell--active {
  color: var(--accent);
}

.support-bell--active:hover {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.support-bell__badge {
  position: absolute;
  top: 0.12rem;
  right: 0.08rem;
  min-width: 1.05rem;
  height: 1.05rem;
  padding: 0 0.22rem;
  border-radius: 999px;
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1.05rem;
  text-align: center;
  color: #fff;
  background: var(--danger);
  border: 1px solid color-mix(in srgb, var(--danger) 70%, #000 30%);
  pointer-events: none;
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
