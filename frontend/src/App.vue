<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { clearAdminToken, getAdminToken } from './auth/session.js'

const router = useRouter()
const hasAdminToken = ref(false)

function refreshAdminSession() {
  hasAdminToken.value = Boolean(getAdminToken())
}

function logout() {
  clearAdminToken()
  refreshAdminSession()
  router.push('/')
}

onMounted(refreshAdminSession)
router.afterEach(refreshAdminSession)
</script>

<template>
  <div class="app">
    <nav class="nav" aria-label="Основная навигация">
      <RouterLink class="nav-link" to="/">Главная</RouterLink>
      <RouterLink
        v-if="hasAdminToken"
        class="nav-link"
        to="/admin/users"
      >
        Пользователи
      </RouterLink>
      <span class="nav-spacer" />
      <RouterLink
        v-if="!hasAdminToken"
        class="nav-link nav-admin"
        to="/admin/login"
      >
        Вход в админку
      </RouterLink>
      <button
        v-if="hasAdminToken"
        type="button"
        class="nav-btn"
        @click="logout"
      >
        Выход
      </button>
    </nav>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid var(--nav-border);
  background: var(--nav-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
}

.nav-spacer {
  flex: 1;
  min-width: 0.5rem;
}

.nav-admin {
  font-size: 0.9rem;
}

.nav-btn {
  font: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  padding: 0.45rem 0.85rem;
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

.nav-link {
  color: var(--nav-link);
  text-decoration: none;
  font-weight: 600;
  padding: 0.45rem 0.85rem;
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

.main {
  flex: 1;
  padding: 0;
  width: 100%;
}
</style>
