<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'
import { setStaffSession } from '../auth/staffSession.js'

const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref(null)

async function submit() {
  loading.value = true
  error.value = null
  try {
    const res = await apiFetch('/api/staff/auth/login', {
      method: 'POST',
      body: { email: email.value, password: password.value },
      unauthenticatedOk: true,
      withProject: false,
    })
    setStaffSession(res.access_token, res.profile)
    const redirect = route.query.redirect || '/dashboard'
    router.replace(redirect)
  } catch (e) {
    error.value = e.message || 'Ошибка входа'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="card stack" @submit.prevent="submit" style="max-width: 380px;">
      <h1 style="margin: 0 0 8px 0; font-size: 20px;">Вход персонала</h1>
      <label>
        <span>Email</span>
        <input v-model="email" type="email" required autocomplete="email" />
      </label>
      <label>
        <span>Пароль</span>
        <input v-model="password" type="password" required autocomplete="current-password" />
      </label>
      <button type="submit" class="primary" :disabled="loading">
        {{ loading ? 'Входим…' : 'Войти' }}
      </button>
      <p v-if="error" class="err">{{ error }}</p>
    </form>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: grid;
  place-items: center;
}
label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--text-muted); }
label span { padding-left: 4px; }
.err { color: var(--danger); margin: 0; font-size: 13px; }
</style>
