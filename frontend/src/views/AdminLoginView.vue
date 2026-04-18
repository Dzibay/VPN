<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RouterLink } from 'vue-router'
import { fetchJson } from '../api/client.js'
import {
  getAdminToken,
  invalidateAuthStatusCache,
  isAdminAuthRequired,
  setAdminToken,
} from '../auth/session.js'

const route = useRoute()
const router = useRouter()

const password = ref('')
const submitting = ref(false)
const error = ref(null)
const checking = ref(true)

async function checkAuthMode() {
  checking.value = true
  invalidateAuthStatusCache()
  try {
    const required = await isAdminAuthRequired(() =>
      fetchJson('/api/auth/status'),
    )
    if (!required) {
      const redirect =
        typeof route.query.redirect === 'string'
          ? route.query.redirect
          : '/admin'
      router.replace(redirect || '/admin')
      return
    }
    if (getAdminToken()) {
      const redirect =
        typeof route.query.redirect === 'string'
          ? route.query.redirect
          : '/admin'
      router.replace(redirect || '/admin')
    }
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    checking.value = false
  }
}

async function submit() {
  submitting.value = true
  error.value = null
  try {
    const data = await fetchJson('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password: password.value }),
    })
    setAdminToken(data.access_token)
    const redirect =
      typeof route.query.redirect === 'string'
        ? route.query.redirect
        : '/admin'
    router.replace(redirect || '/admin')
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    submitting.value = false
  }
}

onMounted(checkAuthMode)
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <h1>Вход в админку</h1>
      <p class="sub">Пароль задаётся на сервере в ADMIN_PANEL_PASSWORD</p>
    </header>

    <div v-if="checking" class="card card-pad">Проверка…</div>

    <form v-else class="card card-pad form" @submit.prevent="submit">
      <label class="field">
        <span class="label">Пароль</span>
        <input
          v-model="password"
          class="input"
          type="password"
          name="password"
          autocomplete="current-password"
          required
        />
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <button class="btn-primary btn-block" type="submit" :disabled="submitting">
        {{ submitting ? 'Вход…' : 'Войти' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.page {
  max-width: 420px;
  margin: 0 auto;
  padding: 1.75rem 1rem 2.5rem;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

.back {
  display: inline-block;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  margin-bottom: 1rem;
  transition: color 0.2s ease;
}

.back:hover {
  color: var(--accent);
}

h1 {
  font-size: 1.6rem;
  margin: 0 0 0.4rem;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.35rem 1.4rem;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  text-align: left;
}

.label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
}

.input {
  padding: 0.6rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.input::placeholder {
  color: var(--muted);
  opacity: 0.8;
}

.err {
  margin: 0;
  color: var(--danger);
  font-size: 0.9rem;
}

.btn-block {
  width: 100%;
  margin-top: 0.25rem;
}
</style>
