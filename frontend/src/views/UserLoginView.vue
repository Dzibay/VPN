<script setup>
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'
import { setSession } from '../auth/session.js'

const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const error = ref(null)

async function submit() {
  submitting.value = true
  error.value = null
  try {
    const data = await fetchJson('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: email.value.trim(),
        password: password.value,
      }),
    })
    setSession(data.access_token, data.role)
    const r = route.query.redirect
    if (data.role === 'admin') {
      router.replace(
        typeof r === 'string' && r.startsWith('/admin') ? r : '/admin',
      )
    } else {
      router.replace(typeof r === 'string' && r ? r : '/cabinet')
    }
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <h1>Вход</h1>
      <p class="sub">
        Один вход для кабинета и для администратора (учётные данные из .env на
        сервере).
      </p>
    </header>

    <form class="card card-pad form" @submit.prevent="submit">
      <label class="field">
        <span class="label">Email</span>
        <input
          v-model="email"
          class="input"
          type="email"
          name="email"
          autocomplete="email"
          required
        />
      </label>
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
      <p class="extra">
        Нет аккаунта?
        <RouterLink to="/register">Регистрация</RouterLink>
      </p>
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

.err {
  margin: 0;
  color: var(--danger);
  font-size: 0.9rem;
}

.btn-block {
  width: 100%;
  margin-top: 0.25rem;
}

.extra {
  margin: 0;
  text-align: center;
  font-size: 0.9rem;
  color: var(--muted);
}

.extra a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.extra a:hover {
  text-decoration: underline;
}
</style>
