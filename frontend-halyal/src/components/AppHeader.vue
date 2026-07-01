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
import { brandLogoPath, brandName } from '../brand/brandAssets.js'
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

const cabinetCtaTo = computed(() =>
  hasToken.value ? '/cabinet' : '/register',
)

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
    <RouterLink class="brand" to="/" :aria-label="brandName">
      <img
        class="brand-logo"
        :src="brandLogoPath"
        width="40"
        height="40"
        alt=""
        decoding="async"
      />
      <span class="brand-wordmark" aria-hidden="true">
        <span class="brand-wordmark__halyal">ХАЛЯЛЬ</span>
        <span class="brand-wordmark__vpn">VPN</span>
      </span>
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
          <RouterLink class="nav-link nav-accent nav-accent--filled" :to="cabinetCtaTo">
            Перейти в кабинет
          </RouterLink>
        </template>
        <template v-else-if="showUserLogout">
          <RouterLink class="nav-link nav-accent nav-accent--filled" to="/cabinet">
            Перейти в кабинет
          </RouterLink>
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
  container-type: inline-size;
  container-name: shell;
}

.shell--home {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 0.75rem 1rem;
  border-bottom: 1px solid rgba(27, 67, 50, 0.08);
  background: rgba(247, 243, 238, 0.88);
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

.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  text-decoration: none;
  min-width: 0;
}

.brand-logo {
  display: block;
  width: 2.5rem;
  height: 2.5rem;
  object-fit: contain;
  flex-shrink: 0;
}

.brand-wordmark {
  display: inline-flex;
  align-items: baseline;
  gap: 0.35rem;
  font-family: var(--heading);
  font-weight: 800;
  letter-spacing: 0.04em;
  line-height: 1;
}

.brand-wordmark__halyal {
  font-size: 1.05rem;
  color: var(--halyal-green);
}

.brand-wordmark__vpn {
  font-size: 1.05rem;
  color: var(--halyal-gold);
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
  color: var(--halyal-green);
}

.spacer {
  flex: 1;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}

.user-bar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
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

.nav-accent {
  color: var(--halyal-green);
}

.nav-accent--filled {
  color: #ffffff;
  background: var(--halyal-green);
  padding: 0.45rem 0.95rem;
  border-radius: 999px;
}

.nav-accent--filled:hover {
  color: #ffffff;
  background: var(--halyal-green-hover);
}

.nav-btn {
  border: none;
  background: transparent;
  cursor: pointer;
  font: inherit;
}

.nav-btn.ghost {
  color: var(--nav-link);
  font-weight: 600;
  font-size: 0.9rem;
  padding: 0.4rem 0.75rem;
  border-radius: 10px;
}

.nav-btn.ghost:hover {
  background: var(--nav-link-hover-bg);
  color: var(--text-h);
}

.support-bell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 10px;
  color: var(--nav-link);
  text-decoration: none;
  transition: background 0.2s ease, color 0.2s ease;
}

.support-bell:hover {
  color: var(--halyal-green);
  background: var(--nav-link-hover-bg);
}

.support-bell__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 1.1rem;
  height: 1.1rem;
  padding: 0 0.25rem;
  border-radius: 999px;
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1.1rem;
  text-align: center;
  color: #fff;
  background: #e53e3e;
}

@container shell (max-width: 640px) {
  .nav-link:not(.nav-accent--filled) {
    display: none;
  }
}
</style>
