<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  clearAdminToken,
  clearUserToken,
  getAdminToken,
  getUserToken,
} from '../auth/session.js'

const router = useRouter()
const route = useRoute()

const hasAdminToken = ref(false)
const hasUserToken = ref(false)

function refreshSessions() {
  hasAdminToken.value = Boolean(getAdminToken())
  hasUserToken.value = Boolean(getUserToken())
}

/** На главной всегда «Вход» и «Регистрация»; в кабинете и при JWT на других страницах — «Выйти». */
const showGuestAuthLinks = computed(
  () =>
    route.name === 'home' ||
    (route.name !== 'cabinet' && !hasUserToken.value),
)

const showUserLogout = computed(
  () =>
    route.name === 'cabinet' ||
    (route.name !== 'home' && hasUserToken.value),
)

function logoutUser() {
  clearUserToken()
  refreshSessions()
  if (route.path.startsWith('/cabinet')) {
    router.push('/login')
  } else {
    router.push('/')
  }
}

function logoutAdmin() {
  clearAdminToken()
  refreshSessions()
  router.push('/')
}

onMounted(refreshSessions)
router.afterEach(refreshSessions)
</script>

<template>
  <header class="shell" aria-label="Шапка сайта">
    <RouterLink class="brand" to="/">
      <span class="brand-mark" aria-hidden="true" />
      <span class="brand-text">VPN</span>
    </RouterLink>

    <span class="spacer" aria-hidden="true" />

    <div class="toolbar">
      <nav class="user-bar" aria-label="Аккаунт">
        <template v-if="showGuestAuthLinks">
          <RouterLink class="nav-link" to="/login">Вход</RouterLink>
          <RouterLink class="nav-link nav-accent" to="/register">
            Регистрация
          </RouterLink>
        </template>
        <template v-else-if="showUserLogout">
          <button type="button" class="nav-btn ghost" @click="logoutUser">
            Выйти
          </button>
        </template>
      </nav>

      <nav
        v-if="hasAdminToken"
        class="group-admin"
        aria-label="Администрирование"
      >
        <span class="admin-label">Админка</span>
        <RouterLink
          class="nav-link"
          :class="{
            'router-link-active':
              route.name === 'admin-data' || route.name === 'admin-user-analytics',
          }"
          to="/admin"
        >
          Данные
        </RouterLink>
        <RouterLink
          class="nav-link"
          :class="{ 'router-link-active': route.name === 'admin-analytics' }"
          to="/admin/analytics"
        >
          Аналитика
        </RouterLink>
        <button type="button" class="nav-btn" @click="logoutAdmin">
          Выход из админки
        </button>
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
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
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

.brand-mark {
  width: 2rem;
  height: 2rem;
  border-radius: 10px;
  background: linear-gradient(
    135deg,
    var(--accent) 0%,
    var(--accent-hover) 100%
  );
  box-shadow: 0 4px 14px rgba(139, 92, 246, 0.35);
}

.group-admin {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.15rem 0.15rem 0.35rem;
  border-radius: 12px;
  background: rgba(139, 92, 246, 0.1);
  border: 1px solid var(--accent-border);
}

.admin-label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  padding: 0 0.35rem 0 0.5rem;
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
